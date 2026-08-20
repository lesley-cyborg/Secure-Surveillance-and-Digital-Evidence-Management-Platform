from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from app.modules.evidence.signing import (
    DigitalSignatureEnvelope,
    RSAPSSSHA256Signer,
    build_evidence_signature_payload,
)
from cryptography.hazmat.primitives.asymmetric import (
    rsa,
)

_INCIDENT = UUID("11111111-1111-1111-1111-111111111111")


@pytest.fixture(scope="module")
def signer() -> RSAPSSSHA256Signer:
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=4096,
    )

    return RSAPSSSHA256Signer(
        public_key=private_key.public_key(),
        private_key=private_key,
        key_reference="test://signing/v1",
        key_version=1,
    )


def payload() -> bytes:
    timestamp = datetime(
        2026,
        8,
        9,
        10,
        0,
        tzinfo=UTC,
    )

    return build_evidence_signature_payload(
        evidence_number=("EVD-20260809-100000-ABCDEF123456"),
        incident_id=_INCIDENT,
        source_detection_id=None,
        storage_bucket="evidence",
        storage_object_key="test.sspe",
        storage_version_id="version-1",
        original_sha256="a" * 64,
        encrypted_sha256="b" * 64,
        manifest_sha256="c" * 64,
        captured_at=timestamp,
        ingested_at=timestamp,
    )


def test_signature_round_trip(
    signer: RSAPSSSHA256Signer,
) -> None:
    data = payload()

    signature = signer.sign(data)

    assert signer.verify(
        data,
        signature,
    )


def test_payload_mutation_invalidates_signature(
    signer: RSAPSSSHA256Signer,
) -> None:
    signature = signer.sign(payload())

    assert not signer.verify(
        payload() + b"x",
        signature,
    )


def test_signature_envelope_round_trip(
    signer: RSAPSSSHA256Signer,
) -> None:
    signature = signer.sign(payload())

    restored = DigitalSignatureEnvelope.from_json(signature.to_json())

    assert restored == signature


def test_wrong_key_rejects_signature(
    signer: RSAPSSSHA256Signer,
) -> None:
    signature = signer.sign(payload())

    other_private = rsa.generate_private_key(
        public_exponent=65537,
        key_size=4096,
    )

    other = RSAPSSSHA256Signer(
        public_key=(other_private.public_key()),
        private_key=other_private,
        key_reference="test://signing/v1",
    )

    assert not other.verify(
        payload(),
        signature,
    )


def test_2048_bit_signing_key_is_rejected() -> None:
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    with pytest.raises(
        ValueError,
        match="4096",
    ):
        RSAPSSSHA256Signer(
            public_key=(private_key.public_key()),
            private_key=private_key,
            key_reference=("test://invalid"),
        )


def test_storage_identity_changes_signed_payload() -> None:
    timestamp = datetime.now(UTC)

    first = build_evidence_signature_payload(
        evidence_number="EVD-TEST",
        incident_id=_INCIDENT,
        source_detection_id=None,
        storage_bucket="evidence",
        storage_object_key="a.sspe",
        storage_version_id="1",
        original_sha256="a" * 64,
        encrypted_sha256="b" * 64,
        manifest_sha256="c" * 64,
        captured_at=timestamp,
        ingested_at=timestamp,
    )

    second = build_evidence_signature_payload(
        evidence_number="EVD-TEST",
        incident_id=_INCIDENT,
        source_detection_id=None,
        storage_bucket="evidence",
        storage_object_key="b.sspe",
        storage_version_id="1",
        original_sha256="a" * 64,
        encrypted_sha256="b" * 64,
        manifest_sha256="c" * 64,
        captured_at=timestamp,
        ingested_at=timestamp,
    )

    assert first != second
