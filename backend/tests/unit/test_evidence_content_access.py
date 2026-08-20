from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import pytest
from app.db.models.enums import (
    AuditOutcome,
    CustodyEventType,
)
from app.modules.audit.actions import AuditAction
from app.modules.evidence.content_access import (
    EvidenceContentAccessCommand,
    EvidenceContentAccessService,
)
from app.modules.evidence.errors import (
    EvidenceRetrievalHashMismatchError,
    EvidenceRetrievalSignatureInvalidError,
    EvidenceRetrievalUnavailableError,
    EvidenceVerificationReferenceError,
)
from app.modules.evidence.signing import ForensicSigner
from app.modules.evidence.verification import (
    EvidenceRetrievalResult,
    EvidenceVerificationCommand,
)
from app.modules.evidence.verification_orchestrator import (
    EvidenceVerificationOrchestrator,
)
from sqlalchemy.ext.asyncio import AsyncSession


class StubSession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.rollback_count = 0

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1


class StubVerificationOrchestrator:
    def __init__(
        self,
        *,
        result: EvidenceRetrievalResult | None = None,
        exception: Exception | None = None,
    ) -> None:
        self.result = result
        self.exception = exception
        self.commands: list[EvidenceVerificationCommand] = []

    async def retrieve(
        self,
        *,
        command: EvidenceVerificationCommand,
    ) -> EvidenceRetrievalResult:
        self.commands.append(command)

        if self.exception is not None:
            raise self.exception

        if self.result is None:
            raise AssertionError("Stub retrieval result was not configured")

        return self.result


class StubEvidenceRepository:
    def __init__(
        self,
        *,
        evidence_id: UUID,
    ) -> None:
        self.evidence = SimpleNamespace(
            id=evidence_id,
        )

        self.calls = 0

    async def get_by_id_for_update(
        self,
        evidence_id: UUID,
    ) -> object | None:
        self.calls += 1

        if evidence_id != self.evidence.id:
            return None

        return self.evidence


class StubCustodyRepository:
    def __init__(self) -> None:
        self.previous = SimpleNamespace(
            id=uuid4(),
            record_hash="a" * 64,
        )

        self.created_id = uuid4()

        self.latest_calls: list[UUID] = []
        self.create_calls: list[dict[str, object]] = []

        self.create_exception: Exception | None = None

    async def get_latest_for_update(
        self,
        *,
        evidence_id: UUID,
    ) -> object | None:
        self.latest_calls.append(evidence_id)

        return self.previous

    async def create(
        self,
        **kwargs: object,
    ) -> object:
        self.create_calls.append(dict(kwargs))

        if self.create_exception is not None:
            raise self.create_exception

        return SimpleNamespace(
            id=self.created_id,
        )


class StubAuditRepository:
    def __init__(self) -> None:
        self.create_calls: list[dict[str, object]] = []

        self.create_exception: Exception | None = None

    async def create(
        self,
        **kwargs: object,
    ) -> object:
        self.create_calls.append(dict(kwargs))

        if self.create_exception is not None:
            raise self.create_exception

        return SimpleNamespace(
            id=uuid4(),
        )


class StubSignature:
    def to_json(self) -> str:
        return '{"algorithm":"TEST","signature":"stub"}'


class StubSigner:
    def __init__(self) -> None:
        self.payloads: list[bytes] = []

    def sign(
        self,
        payload: bytes,
    ) -> StubSignature:
        self.payloads.append(payload)

        return StubSignature()


@dataclass(slots=True)
class ContentAccessHarness:
    service: EvidenceContentAccessService

    session: StubSession

    orchestrator: StubVerificationOrchestrator
    evidence: StubEvidenceRepository
    custody: StubCustodyRepository
    audit: StubAuditRepository
    signer: StubSigner


def build_retrieval_result(
    *,
    evidence_id: UUID,
) -> EvidenceRetrievalResult:
    return EvidenceRetrievalResult(
        evidence_id=evidence_id,
        evidence_number="EVD-CONTENT-0001",
        original_filename="frame-001.jpg",
        mime_type="image/jpeg",
        content=b"verified-plaintext-evidence",
        original_sha256="b" * 64,
        verified_at=datetime.now(UTC),
    )


def build_command(
    *,
    evidence_id: UUID,
    actor_user_id: UUID | None = None,
) -> EvidenceContentAccessCommand:
    return EvidenceContentAccessCommand(
        evidence_id=evidence_id,
        actor_user_id=(actor_user_id or uuid4()),
        correlation_id=str(uuid4()),
        source_ip="127.0.0.1",
        user_agent="pytest",
        device_identifier="test-client",
    )


def build_harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    evidence_id: UUID,
    result: EvidenceRetrievalResult | None = None,
    exception: Exception | None = None,
) -> ContentAccessHarness:
    session = StubSession()

    orchestrator = StubVerificationOrchestrator(
        result=result,
        exception=exception,
    )

    signer = StubSigner()

    service = EvidenceContentAccessService(
        session=cast(
            AsyncSession,
            session,
        ),
        orchestrator=cast(
            EvidenceVerificationOrchestrator,
            orchestrator,
        ),
        signer=cast(
            ForensicSigner,
            signer,
        ),
    )

    evidence = StubEvidenceRepository(evidence_id=evidence_id)

    custody = StubCustodyRepository()
    audit = StubAuditRepository()

    monkeypatch.setattr(
        service,
        "evidence",
        evidence,
    )

    monkeypatch.setattr(
        service,
        "custody",
        custody,
    )

    monkeypatch.setattr(
        service,
        "audit",
        audit,
    )

    return ContentAccessHarness(
        service=service,
        session=session,
        orchestrator=orchestrator,
        evidence=evidence,
        custody=custody,
        audit=audit,
        signer=signer,
    )


@pytest.mark.asyncio
async def test_successful_retrieval_records_viewed_custody_and_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence_id = uuid4()
    actor_user_id = uuid4()

    retrieval = build_retrieval_result(evidence_id=evidence_id)

    harness = build_harness(
        monkeypatch,
        evidence_id=evidence_id,
        result=retrieval,
    )

    command = build_command(
        evidence_id=evidence_id,
        actor_user_id=actor_user_id,
    )

    result = await harness.service.retrieve(command=command)

    assert result == retrieval
    assert result.content == (b"verified-plaintext-evidence")

    assert harness.session.commit_count == 1
    assert harness.session.rollback_count == 0

    assert len(harness.orchestrator.commands) == 1

    verification_command = harness.orchestrator.commands[0]

    assert verification_command.evidence_id == evidence_id

    assert verification_command.verified_by_user_id == actor_user_id

    assert verification_command.correlation_id == command.correlation_id

    assert verification_command.idempotency_key is None

    assert harness.evidence.calls == 1

    assert harness.custody.latest_calls == [evidence_id]

    assert len(harness.custody.create_calls) == 1

    custody_call = harness.custody.create_calls[0]

    assert custody_call["evidence_id"] == evidence_id

    assert custody_call["actor_user_id"] == actor_user_id

    assert custody_call["event_type"] is CustodyEventType.VIEWED

    assert custody_call["previous_record_id"] == harness.custody.previous.id

    assert custody_call["record_hash"]

    assert len(harness.signer.payloads) == 1

    assert len(harness.audit.create_calls) == 1

    audit_call = harness.audit.create_calls[0]

    assert audit_call["action"] is AuditAction.EVIDENCE_CONTENT_VIEWED

    assert audit_call["outcome"] is AuditOutcome.SUCCESS

    assert audit_call["resource_id"] == evidence_id

    assert audit_call["actor_user_id"] == actor_user_id


@pytest.mark.asyncio
async def test_custody_persistence_failure_rolls_back_and_blocks_plaintext(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence_id = uuid4()

    retrieval = build_retrieval_result(evidence_id=evidence_id)

    harness = build_harness(
        monkeypatch,
        evidence_id=evidence_id,
        result=retrieval,
    )

    harness.custody.create_exception = RuntimeError("custody persistence failure")

    with pytest.raises(
        RuntimeError,
        match="custody persistence failure",
    ):
        await harness.service.retrieve(command=build_command(evidence_id=evidence_id))

    assert harness.session.commit_count == 0
    assert harness.session.rollback_count == 1

    assert len(harness.custody.create_calls) == 1

    assert harness.audit.create_calls == []


@pytest.mark.asyncio
async def test_audit_failure_rolls_back_and_blocks_plaintext(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence_id = uuid4()

    retrieval = build_retrieval_result(evidence_id=evidence_id)

    harness = build_harness(
        monkeypatch,
        evidence_id=evidence_id,
        result=retrieval,
    )

    harness.audit.create_exception = RuntimeError("audit persistence failure")

    with pytest.raises(
        RuntimeError,
        match="audit persistence failure",
    ):
        await harness.service.retrieve(command=build_command(evidence_id=evidence_id))

    assert harness.session.commit_count == 0
    assert harness.session.rollback_count == 1

    # The custody INSERT was attempted, but because
    # no commit occurred the transaction must be
    # rolled back by the service.
    assert len(harness.custody.create_calls) == 1

    assert len(harness.audit.create_calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "exception",
        "expected_reason",
    ),
    [
        (
            EvidenceVerificationReferenceError("Evidence does not exist."),
            "evidence_not_found",
        ),
        (
            EvidenceRetrievalUnavailableError("Evidence storage unavailable."),
            "evidence_unavailable",
        ),
        (
            EvidenceRetrievalHashMismatchError("Evidence hash mismatch."),
            "hash_mismatch",
        ),
        (
            EvidenceRetrievalSignatureInvalidError("Evidence signature invalid."),
            "signature_invalid",
        ),
    ],
)
async def test_forensic_failure_records_failure_audit_without_viewed_custody(
    monkeypatch: pytest.MonkeyPatch,
    exception: Exception,
    expected_reason: str,
) -> None:
    evidence_id = uuid4()

    harness = build_harness(
        monkeypatch,
        evidence_id=evidence_id,
        exception=exception,
    )

    command = build_command(evidence_id=evidence_id)

    with pytest.raises(type(exception)):
        await harness.service.retrieve(command=command)

    assert harness.session.commit_count == 1
    assert harness.session.rollback_count == 0

    assert harness.evidence.calls == 0

    assert harness.custody.latest_calls == []

    assert harness.custody.create_calls == []

    assert harness.signer.payloads == []

    assert len(harness.audit.create_calls) == 1

    audit_call = harness.audit.create_calls[0]

    assert audit_call["action"] is AuditAction.EVIDENCE_CONTENT_VIEWED

    assert audit_call["outcome"] is AuditOutcome.FAILURE

    assert audit_call["resource_id"] == evidence_id

    details = cast(
        dict[str, object],
        audit_call["details"],
    )

    assert details["reason"] == expected_reason
