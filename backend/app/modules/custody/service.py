from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import AuditOutcome, CustodyEventType
from app.db.models.evidence import CustodyRecord
from app.modules.audit.actions import AuditAction
from app.modules.audit.repository import AuditRepository
from app.modules.auth.repository import UserRepository
from app.modules.custody.errors import (
    CustodyActorNotFoundError,
    CustodyEvidenceNotFoundError,
    CustodyIdempotencyConflictError,
)
from app.modules.custody.integrity import build_custody_integrity
from app.modules.custody.policy import validate_api_event_type
from app.modules.custody.repository import CustodyRepository
from app.modules.evidence.repository import EvidenceRepository
from app.modules.evidence.signing import ForensicSigner

_IDEMPOTENCY_SCOPE = "custody_event"


@dataclass(frozen=True, slots=True)
class AppendCustodyEventCommand:
    """Input required to append one custody event."""

    evidence_id: UUID
    actor_user_id: UUID
    event_type: CustodyEventType
    purpose: str
    idempotency_key: str
    correlation_id: str
    source_ip: str | None = None
    user_agent: str | None = None
    device_identifier: str | None = None
    event_metadata: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class AppendCustodyEventResult:
    """Result of creating or replaying a custody event."""

    custody_record: CustodyRecord
    replayed: bool


@dataclass(frozen=True, slots=True)
class ListCustodyEventsCommand:
    """Input required to retrieve custody history."""

    evidence_id: UUID
    actor_user_id: UUID
    correlation_id: str
    page: int = 1
    page_size: int = 25
    source_ip: str | None = None
    user_agent: str | None = None


@dataclass(frozen=True, slots=True)
class ListCustodyEventsResult:
    """Paginated custody history."""

    items: list[CustodyRecord]
    total: int


class CustodyService:
    """
    Application service for the append-only chain of custody.

    Responsibilities:

    - validate the requested custody event;
    - verify that evidence exists;
    - verify that the actor exists;
    - serialize concurrent writes for one evidence item;
    - enforce idempotency;
    - establish the previous-record chain;
    - generate the forensic record hash;
    - digitally sign the canonical custody payload;
    - persist the custody record;
    - persist the corresponding audit event;
    - own the transaction boundary.

    Repositories flush but never commit.
    """

    def __init__(
        self,
        *,
        session: AsyncSession,
        signer: ForensicSigner,
    ) -> None:
        self.session = session
        self.signer = signer

        self.evidence = EvidenceRepository(session)
        self.custody = CustodyRepository(session)
        self.audit = AuditRepository(session)
        self.user = UserRepository(session)

    async def append_event(
        self,
        *,
        command: AppendCustodyEventCommand,
    ) -> AppendCustodyEventResult:
        """
        Append one immutable custody event.

        The evidence row is locked before examining the custody chain.
        This serializes concurrent custody writes even when the evidence
        item currently has no custody records.
        """

        occurred_at = datetime.now(UTC)

        # ---------------------------------------------------------
        # 1. Validate the event against the public custody policy.
        # ---------------------------------------------------------

        validate_api_event_type(command.event_type)

        # ---------------------------------------------------------
        # 2. Lock and validate the evidence row.
        #
        # This is the concurrency anchor for the entire operation.
        # ---------------------------------------------------------

        evidence = await self.evidence.get_by_id_for_update(
            command.evidence_id,
        )

        if evidence is None:
            raise CustodyEvidenceNotFoundError("Evidence does not exist.")

        # ---------------------------------------------------------
        # 3. Validate the actor.
        # ---------------------------------------------------------

        actor = await self.user.get_by_id(
            command.actor_user_id,
        )

        if actor is None:
            raise CustodyActorNotFoundError(
                "Custody actor does not exist.",
            )

        # ---------------------------------------------------------
        # 4. Idempotency lookup.
        #
        # The database additionally enforces:
        #
        # evidence_id + idempotency_scope + idempotency_key
        # as a unique lifecycle identity.
        # ---------------------------------------------------------

        existing = await self.custody.get_by_idempotency(
            evidence_id=evidence.id,
            idempotency_scope=_IDEMPOTENCY_SCOPE,
            idempotency_key=command.idempotency_key,
        )

        if existing is not None:
            if not self._is_same_request(
                existing=existing,
                command=command,
            ):
                raise CustodyIdempotencyConflictError(
                    "Idempotency key was already used for another custody event."
                )

            return AppendCustodyEventResult(
                custody_record=existing,
                replayed=True,
            )

        # ---------------------------------------------------------
        # 5. Obtain the previous custody record.
        #
        # Evidence is already locked, so another custody operation
        # for the same evidence cannot advance the chain concurrently.
        # ---------------------------------------------------------

        previous = await self.custody.get_latest_for_update(
            evidence_id=evidence.id,
        )

        previous_record_id = previous.id if previous is not None else None

        previous_record_hash = previous.record_hash if previous is not None else None

        # ---------------------------------------------------------
        # 6. Normalize event metadata.
        # ---------------------------------------------------------

        metadata: dict[str, object] = dict(command.event_metadata or {})

        metadata.setdefault(
            "correlation_id",
            command.correlation_id,
        )

        # ---------------------------------------------------------
        # 7. Build the canonical forensic integrity artifact.
        # ---------------------------------------------------------

        custody_integrity = build_custody_integrity(
            evidence_id=evidence.id,
            actor_user_id=command.actor_user_id,
            from_user_id=None,
            to_user_id=None,
            previous_record_id=previous_record_id,
            previous_record_hash=previous_record_hash,
            transfer_id=None,
            event_type=command.event_type,
            purpose=command.purpose,
            source_ip=command.source_ip,
            device_identifier=command.device_identifier,
            event_metadata=metadata,
            occurred_at=occurred_at,
        )

        # ---------------------------------------------------------
        # 8. Digitally sign canonical custody bytes.
        # ---------------------------------------------------------

        custody_signature = self.signer.sign(
            custody_integrity.canonical_bytes,
        )

        # ---------------------------------------------------------
        # 9. Persist immutable custody record.
        # ---------------------------------------------------------

        custody_record = await self.custody.create(
            evidence_id=evidence.id,
            idempotency_scope=_IDEMPOTENCY_SCOPE,
            idempotency_key=command.idempotency_key,
            actor_user_id=command.actor_user_id,
            from_user_id=None,
            to_user_id=None,
            previous_record_id=previous_record_id,
            transfer_id=None,
            event_type=command.event_type,
            purpose=command.purpose,
            source_ip=command.source_ip,
            device_identifier=command.device_identifier,
            event_metadata=metadata,
            record_hash=custody_integrity.record_hash,
            digital_signature=custody_signature.to_json(),
            occurred_at=occurred_at,
        )

        # ---------------------------------------------------------
        # 10. Persist forensic audit event.
        # ---------------------------------------------------------

        await self.audit.create(
            action=AuditAction.CUSTODY_EVENT_CREATED,
            resource_type="evidence",
            resource_id=evidence.id,
            outcome=AuditOutcome.SUCCESS,
            correlation_id=command.correlation_id,
            occurred_at=occurred_at,
            actor_user_id=command.actor_user_id,
            source_ip=command.source_ip,
            user_agent=command.user_agent,
            details={
                "custody_record_id": str(custody_record.id),
                "event_type": command.event_type.value,
                "purpose": command.purpose,
                "record_hash": custody_integrity.record_hash,
                "idempotency_scope": _IDEMPOTENCY_SCOPE,
                "idempotency_key": command.idempotency_key,
                "previous_record_id": (
                    str(previous_record_id) if previous_record_id is not None else None
                ),
            },
        )

        # ---------------------------------------------------------
        # 11. Atomic transaction boundary.
        #
        # Custody record + audit record succeed or fail together.
        # ---------------------------------------------------------

        await self.session.commit()

        return AppendCustodyEventResult(
            custody_record=custody_record,
            replayed=False,
        )

    async def list_events(
        self,
        *,
        command: ListCustodyEventsCommand,
    ) -> ListCustodyEventsResult:
        """Return paginated custody history for an evidence item."""

        evidence = await self.evidence.get_by_id(
            command.evidence_id,
        )

        if evidence is None:
            raise CustodyEvidenceNotFoundError("Evidence does not exist.")

        records, total = await self.custody.list(
            evidence_id=evidence.id,
            page=command.page,
            page_size=command.page_size,
        )

        occurred_at = datetime.now(UTC)

        await self.audit.create(
            action=AuditAction.CUSTODY_HISTORY_VIEWED,
            resource_type="evidence",
            resource_id=evidence.id,
            outcome=AuditOutcome.SUCCESS,
            correlation_id=command.correlation_id,
            occurred_at=occurred_at,
            actor_user_id=command.actor_user_id,
            source_ip=command.source_ip,
            user_agent=command.user_agent,
            details={
                "page": command.page,
                "page_size": command.page_size,
                "total": total,
            },
        )

        await self.session.commit()

        return ListCustodyEventsResult(
            items=records,
            total=total,
        )

    @staticmethod
    def _is_same_request(
        *,
        existing: CustodyRecord,
        command: AppendCustodyEventCommand,
    ) -> bool:
        """
        Determine whether an idempotent replay represents the
        same logical request.

        Correlation ID is intentionally excluded from idempotency
        identity because retries may legitimately have different
        correlation IDs.
        """

        existing_metadata = dict(existing.event_metadata or {})
        requested_metadata = dict(command.event_metadata or {})

        existing_metadata.pop("correlation_id", None)
        requested_metadata.pop("correlation_id", None)

        return (
            existing.event_type == command.event_type
            and existing.purpose == command.purpose
            and existing.actor_user_id == command.actor_user_id
            and existing.source_ip == command.source_ip
            and existing.device_identifier == command.device_identifier
            and existing_metadata == requested_metadata
        )
