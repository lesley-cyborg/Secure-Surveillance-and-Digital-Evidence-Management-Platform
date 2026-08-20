from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from cryptography.exceptions import (
    UnsupportedAlgorithm,
)
from cryptography.hazmat.primitives import (
    serialization,
)
from cryptography.hazmat.primitives.asymmetric import (
    rsa,
)
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db_session
from app.modules.evidence.ai_bridge import (
    AIDetectionEvidenceBridge,
)
from app.modules.evidence.content_access import (
    EvidenceContentAccessService,
)
from app.modules.evidence.key_wrapping import (
    EvidenceKeyWrapper,
    RSAOAEPKeyWrapper,
)
from app.modules.evidence.minio_storage import (
    MinioEvidenceObjectStorage,
)
from app.modules.evidence.service import (
    SecureEvidenceIngestionService,
)
from app.modules.evidence.signing import (
    ForensicSigner,
    RSAPSSSHA256Signer,
)
from app.modules.evidence.storage import (
    EvidenceObjectStorage,
)
from app.modules.evidence.transfer_decision_service import (
    EvidenceTransferDecisionService,
)
from app.modules.evidence.transfer_service import (
    EvidenceTransferInitiationService,
)
from app.modules.evidence.verification_http import (
    EvidenceVerificationHTTPService,
)
from app.modules.evidence.verification_orchestrator import (
    EvidenceVerificationOrchestrator,
)


class EvidenceDependencyConfigurationError(RuntimeError):
    """Evidence dependency configuration is invalid."""


DatabaseSession = Annotated[
    AsyncSession,
    Depends(get_db_session),
]


def _require_key_path(
    *,
    value: Path | None,
    setting_name: str,
) -> Path:
    if value is None:
        raise EvidenceDependencyConfigurationError(f"{setting_name} is not configured")

    path = value.expanduser()

    if not path.is_absolute():
        path = Path.cwd() / path

    path = path.resolve()

    if not path.is_file():
        raise EvidenceDependencyConfigurationError(
            f"{setting_name} does not point to a readable file: {path}"
        )

    return path


def _read_key_bytes(
    *,
    path: Path,
    setting_name: str,
) -> bytes:
    try:
        data = path.read_bytes()
    except OSError as exception:
        raise EvidenceDependencyConfigurationError(
            f"Unable to read {setting_name}: {path}"
        ) from exception

    if not data:
        raise EvidenceDependencyConfigurationError(f"{setting_name} is empty")

    return data


def _load_rsa_public_key(
    *,
    path: Path,
    setting_name: str,
) -> rsa.RSAPublicKey:
    pem = _read_key_bytes(
        path=path,
        setting_name=setting_name,
    )

    try:
        key = serialization.load_pem_public_key(pem)
    except (
        ValueError,
        TypeError,
        UnsupportedAlgorithm,
    ) as exception:
        raise EvidenceDependencyConfigurationError(
            f"{setting_name} does not contain a valid PEM public key"
        ) from exception

    if not isinstance(
        key,
        rsa.RSAPublicKey,
    ):
        raise EvidenceDependencyConfigurationError(f"{setting_name} must contain an RSA public key")

    return key


def _load_rsa_private_key(
    *,
    path: Path,
    setting_name: str,
    password: bytes | None,
) -> rsa.RSAPrivateKey:
    pem = _read_key_bytes(
        path=path,
        setting_name=setting_name,
    )

    try:
        key = serialization.load_pem_private_key(
            pem,
            password=password,
        )
    except (
        ValueError,
        TypeError,
        UnsupportedAlgorithm,
    ) as exception:
        raise EvidenceDependencyConfigurationError(
            f"{setting_name} does not contain a valid PEM private key or its password is incorrect"
        ) from exception

    if not isinstance(
        key,
        rsa.RSAPrivateKey,
    ):
        raise EvidenceDependencyConfigurationError(
            f"{setting_name} must contain an RSA private key"
        )

    return key


@lru_cache(maxsize=1)
def get_evidence_storage() -> EvidenceObjectStorage:
    settings = get_settings()

    return MinioEvidenceObjectStorage.from_settings(settings)


EvidenceObjectStorageAccess = Annotated[
    EvidenceObjectStorage,
    Depends(get_evidence_storage),
]


@lru_cache(maxsize=1)
def get_evidence_key_wrapper() -> EvidenceKeyWrapper:
    settings = get_settings()

    path = _require_key_path(
        value=(settings.evidence_wrapping_public_key_path),
        setting_name=("EVIDENCE_WRAPPING_PUBLIC_KEY_PATH"),
    )

    public_key = _load_rsa_public_key(
        path=path,
        setting_name=("EVIDENCE_WRAPPING_PUBLIC_KEY_PATH"),
    )

    return RSAOAEPKeyWrapper(
        public_key=public_key,
        key_reference=(settings.evidence_wrapping_key_reference),
        key_version=(settings.evidence_wrapping_key_version),
    )


EvidenceKeyWrapperAccess = Annotated[
    EvidenceKeyWrapper,
    Depends(get_evidence_key_wrapper),
]


@lru_cache(maxsize=1)
def get_evidence_verification_key_wrapper() -> EvidenceKeyWrapper:
    settings = get_settings()

    public_path = _require_key_path(
        value=(settings.evidence_wrapping_public_key_path),
        setting_name=("EVIDENCE_WRAPPING_PUBLIC_KEY_PATH"),
    )

    private_path = _require_key_path(
        value=(settings.evidence_wrapping_private_key_path),
        setting_name=("EVIDENCE_WRAPPING_PRIVATE_KEY_PATH"),
    )

    public_key = _load_rsa_public_key(
        path=public_path,
        setting_name=("EVIDENCE_WRAPPING_PUBLIC_KEY_PATH"),
    )

    password_secret = settings.evidence_wrapping_private_key_password

    password_text = password_secret.get_secret_value() if password_secret is not None else ""

    password = password_text.encode("utf-8") if password_text else None

    private_key = _load_rsa_private_key(
        path=private_path,
        setting_name=("EVIDENCE_WRAPPING_PRIVATE_KEY_PATH"),
        password=password,
    )

    return RSAOAEPKeyWrapper(
        public_key=public_key,
        private_key=private_key,
        key_reference=(settings.evidence_wrapping_key_reference),
        key_version=(settings.evidence_wrapping_key_version),
    )


EvidenceVerificationKeyWrapperAccess = Annotated[
    EvidenceKeyWrapper,
    Depends(get_evidence_verification_key_wrapper),
]


@lru_cache(maxsize=1)
def get_forensic_signer() -> ForensicSigner:
    settings = get_settings()

    path = _require_key_path(
        value=(settings.evidence_signing_private_key_path),
        setting_name=("EVIDENCE_SIGNING_PRIVATE_KEY_PATH"),
    )

    password_secret = settings.evidence_signing_private_key_password

    password_text = password_secret.get_secret_value() if password_secret is not None else ""

    password = password_text.encode("utf-8") if password_text else None

    private_key = _load_rsa_private_key(
        path=path,
        setting_name=("EVIDENCE_SIGNING_PRIVATE_KEY_PATH"),
        password=password,
    )

    public_key = private_key.public_key()

    return RSAPSSSHA256Signer(
        public_key=public_key,
        private_key=private_key,
        key_reference=(settings.evidence_signing_key_reference),
        key_version=(settings.evidence_signing_key_version),
    )


ForensicSignerAccess = Annotated[
    ForensicSigner,
    Depends(get_forensic_signer),
]


def get_secure_evidence_ingestion_service(
    session: DatabaseSession,
    storage: EvidenceObjectStorageAccess,
    key_wrapper: EvidenceKeyWrapperAccess,
    signer: ForensicSignerAccess,
) -> SecureEvidenceIngestionService:
    return SecureEvidenceIngestionService(
        session=session,
        storage=storage,
        key_wrapper=key_wrapper,
        signer=signer,
    )


SecureEvidenceIngestionServiceAccess = Annotated[
    SecureEvidenceIngestionService,
    Depends(get_secure_evidence_ingestion_service),
]


def get_ai_detection_evidence_bridge(
    session: DatabaseSession,
    ingestion: (SecureEvidenceIngestionServiceAccess),
) -> AIDetectionEvidenceBridge:
    return AIDetectionEvidenceBridge(
        session=session,
        ingestion=ingestion,
    )


AIDetectionEvidenceBridgeAccess = Annotated[
    AIDetectionEvidenceBridge,
    Depends(get_ai_detection_evidence_bridge),
]


def get_evidence_verification_orchestrator(
    session: DatabaseSession,
    storage: EvidenceObjectStorageAccess,
    key_wrapper: EvidenceVerificationKeyWrapperAccess,
    signer: ForensicSignerAccess,
) -> EvidenceVerificationOrchestrator:
    return EvidenceVerificationOrchestrator(
        session=session,
        storage=storage,
        key_wrapper=key_wrapper,
        signer=signer,
    )


EvidenceVerificationOrchestratorAccess = Annotated[
    EvidenceVerificationOrchestrator,
    Depends(get_evidence_verification_orchestrator),
]


def get_evidence_verification_http_service(
    session: DatabaseSession,
    orchestrator: EvidenceVerificationOrchestratorAccess,
) -> EvidenceVerificationHTTPService:
    return EvidenceVerificationHTTPService(
        session=session,
        orchestrator=orchestrator,
    )


EvidenceVerificationHTTPServiceAccess = Annotated[
    EvidenceVerificationHTTPService,
    Depends(get_evidence_verification_http_service),
]


def get_evidence_content_access_service(
    session: DatabaseSession,
    orchestrator: (EvidenceVerificationOrchestratorAccess),
    signer: ForensicSignerAccess,
) -> EvidenceContentAccessService:
    return EvidenceContentAccessService(
        session=session,
        orchestrator=orchestrator,
        signer=signer,
    )


EvidenceContentAccessServiceAccess = Annotated[
    EvidenceContentAccessService,
    Depends(get_evidence_content_access_service),
]


def get_evidence_transfer_initiation_service(
    session: DatabaseSession,
    signer: ForensicSignerAccess,
) -> EvidenceTransferInitiationService:
    return EvidenceTransferInitiationService(
        session=session,
        signer=signer,
    )


EvidenceTransferInitiationServiceAccess = Annotated[
    EvidenceTransferInitiationService,
    Depends(get_evidence_transfer_initiation_service),
]


def get_evidence_transfer_decision_service(
    session: DatabaseSession,
    signer: ForensicSignerAccess,
) -> EvidenceTransferDecisionService:
    return EvidenceTransferDecisionService(
        session=session,
        signer=signer,
    )


EvidenceTransferDecisionServiceAccess = Annotated[
    EvidenceTransferDecisionService,
    Depends(get_evidence_transfer_decision_service),
]
