from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.db.models.enums import (
    IncidentStatus,
    Priority,
    Severity,
)
from app.modules.ai_ingestion.schemas import (
    DetectionEventIngestionRequest,
)

_CONFIDENCE_PRECISION = Decimal("0.0001")

_LABEL_SEPARATOR_PATTERN = re.compile(r"[\s\-]+")

_SEVERITY_RANK: dict[Severity, int] = {
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}

_PRIORITY_RANK: dict[Priority, int] = {
    Priority.LOW: 1,
    Priority.NORMAL: 2,
    Priority.HIGH: 3,
    Priority.URGENT: 4,
}

_DEFAULT_REUSABLE_STATUSES = frozenset(
    {
        IncidentStatus.NEW,
        IncidentStatus.CONFIRMED,
        IncidentStatus.ASSIGNED,
        IncidentStatus.INVESTIGATING,
        IncidentStatus.ESCALATED,
        IncidentStatus.REOPENED,
    }
)


@dataclass(frozen=True, slots=True)
class IncidentClassificationRule:
    aliases: frozenset[str]
    minimum_confidence: Decimal
    incident_type: str
    severity: Severity
    priority: Priority
    title: str


@dataclass(frozen=True, slots=True)
class IncidentClassificationDecision:
    should_create_incident: bool
    reason: str

    incident_type: str | None
    severity: Severity | None
    priority: Priority | None
    title: str | None
    description: str | None

    matched_label: str | None
    confidence: Decimal

    deduplication_window: timedelta
    reusable_statuses: frozenset[IncidentStatus]


_DEFAULT_RULES: tuple[
    IncidentClassificationRule,
    ...,
] = (
    # --- ADDED FOR TESTING THE PIPELINE ---
    IncidentClassificationRule(
        aliases=frozenset(
            {
                "person",
                "human",
                "individual",
            }
        ),
        minimum_confidence=Decimal("0.5000"),
        incident_type="PERSON_DETECTED",
        severity=Severity.LOW,
        priority=Priority.LOW,
        title="Person detected in monitored area",
    ),
    # --------------------------------------
    IncidentClassificationRule(
        aliases=frozenset(
            {
                "weapon",
                "firearm",
                "gun",
                "pistol",
                "rifle",
                "knife",
            }
        ),
        minimum_confidence=Decimal("0.6500"),
        incident_type="WEAPON_DETECTED",
        severity=Severity.CRITICAL,
        priority=Priority.URGENT,
        title="Weapon detected",
    ),
    IncidentClassificationRule(
        aliases=frozenset(
            {
                "fire",
                "flame",
                "flames",
            }
        ),
        minimum_confidence=Decimal("0.7000"),
        incident_type="FIRE_DETECTED",
        severity=Severity.CRITICAL,
        priority=Priority.URGENT,
        title="Fire detected",
    ),
    IncidentClassificationRule(
        aliases=frozenset(
            {
                "smoke",
            }
        ),
        minimum_confidence=Decimal("0.7500"),
        incident_type="SMOKE_DETECTED",
        severity=Severity.HIGH,
        priority=Priority.HIGH,
        title="Smoke detected",
    ),
    IncidentClassificationRule(
        aliases=frozenset(
            {
                "fight",
                "fighting",
                "violence",
                "violent_activity",
                "assault",
            }
        ),
        minimum_confidence=Decimal("0.7500"),
        incident_type="VIOLENCE_DETECTED",
        severity=Severity.HIGH,
        priority=Priority.HIGH,
        title="Violent activity detected",
    ),
    IncidentClassificationRule(
        aliases=frozenset(
            {
                "intrusion",
                "trespassing",
                "unauthorized_person",
                "restricted_area_entry",
            }
        ),
        minimum_confidence=Decimal("0.8000"),
        incident_type="INTRUSION_DETECTED",
        severity=Severity.HIGH,
        priority=Priority.HIGH,
        title="Possible intrusion detected",
    ),
    IncidentClassificationRule(
        aliases=frozenset(
            {
                "unattended_bag",
                "abandoned_object",
                "suspicious_package",
            }
        ),
        minimum_confidence=Decimal("0.8500"),
        incident_type="SUSPICIOUS_OBJECT_DETECTED",
        severity=Severity.MEDIUM,
        priority=Priority.HIGH,
        title="Suspicious unattended object detected",
    ),
)


def normalize_detection_label(
    label: str,
) -> str:
    normalized = label.strip().casefold()

    normalized = _LABEL_SEPARATOR_PATTERN.sub(
        "_",
        normalized,
    )

    return normalized.strip("_")


class IncidentClassificationPolicy:
    """Classify AI detections without database access."""

    def __init__(
        self,
        *,
        rules: tuple[
            IncidentClassificationRule,
            ...,
        ] = _DEFAULT_RULES,
        deduplication_window: timedelta = (timedelta(minutes=5)),
        reusable_statuses: frozenset[IncidentStatus] = _DEFAULT_REUSABLE_STATUSES,
    ) -> None:
        if not rules:
            raise ValueError("At least one classification rule is required")

        if deduplication_window.total_seconds() <= 0:
            raise ValueError("Deduplication window must be greater than zero")

        for rule in rules:
            if not (Decimal("0") <= rule.minimum_confidence <= Decimal("1")):
                raise ValueError("Rule confidence thresholds must be between zero and one")

        self._rules = rules
        self._deduplication_window = deduplication_window
        self._reusable_statuses = reusable_statuses

    @property
    def deduplication_window(
        self,
    ) -> timedelta:
        return self._deduplication_window

    @property
    def reusable_statuses(
        self,
    ) -> frozenset[IncidentStatus]:
        return self._reusable_statuses

    def classify(
        self,
        event: DetectionEventIngestionRequest,
    ) -> IncidentClassificationDecision:
        if not event.detections:
            return self._no_incident(
                reason="no_detections",
                confidence=Decimal("0.0000"),
            )

        highest_observed_confidence = max(
            self._normalize_confidence(detection.confidence) for detection in event.detections
        )

        candidates: list[
            tuple[
                IncidentClassificationRule,
                str,
                Decimal,
            ]
        ] = []

        supported_label_seen = False

        for detection in event.detections:
            normalized_label = normalize_detection_label(detection.label)

            rule = self._find_rule(normalized_label)

            if rule is None:
                continue

            supported_label_seen = True

            confidence = self._normalize_confidence(detection.confidence)

            if confidence < rule.minimum_confidence:
                continue

            candidates.append(
                (
                    rule,
                    normalized_label,
                    confidence,
                )
            )

        if not candidates:
            reason = (
                "confidence_below_threshold"
                if supported_label_seen
                else "unsupported_detection_label"
            )

            return self._no_incident(
                reason=reason,
                confidence=(highest_observed_confidence),
            )

        selected_rule, selected_label, confidence = max(
            candidates,
            key=lambda candidate: (
                _SEVERITY_RANK[candidate[0].severity],
                _PRIORITY_RANK[candidate[0].priority],
                candidate[2],
            ),
        )

        description = (
            f"AI detection '{selected_label}' "
            f"reached {confidence:.4f} confidence "
            f"for camera {event.camera_id}. "
            f"The configured threshold was "
            f"{selected_rule.minimum_confidence:.4f}."
        )

        return IncidentClassificationDecision(
            should_create_incident=True,
            reason="classification_rule_matched",
            incident_type=(selected_rule.incident_type),
            severity=selected_rule.severity,
            priority=selected_rule.priority,
            title=selected_rule.title,
            description=description,
            matched_label=selected_label,
            confidence=confidence,
            deduplication_window=(self._deduplication_window),
            reusable_statuses=(self._reusable_statuses),
        )

    def _find_rule(
        self,
        normalized_label: str,
    ) -> IncidentClassificationRule | None:
        for rule in self._rules:
            if normalized_label in rule.aliases:
                return rule

        return None

    def _no_incident(
        self,
        *,
        reason: str,
        confidence: Decimal,
    ) -> IncidentClassificationDecision:
        return IncidentClassificationDecision(
            should_create_incident=False,
            reason=reason,
            incident_type=None,
            severity=None,
            priority=None,
            title=None,
            description=None,
            matched_label=None,
            confidence=confidence,
            deduplication_window=(self._deduplication_window),
            reusable_statuses=(self._reusable_statuses),
        )

    @staticmethod
    def _normalize_confidence(
        confidence: float,
    ) -> Decimal:
        return Decimal(str(confidence)).quantize(
            _CONFIDENCE_PRECISION,
            rounding=ROUND_HALF_UP,
        )