from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from app.db.models.enums import (
    IncidentStatus,
    Priority,
    Severity,
)
from app.modules.ai_ingestion.schemas import (
    DetectionEventIngestionRequest,
)
from app.modules.incidents.classification import (
    IncidentClassificationPolicy,
)


def create_event(
    detections: list[dict[str, object]],
) -> DetectionEventIngestionRequest:
    now = datetime.now(UTC)

    return DetectionEventIngestionRequest.model_validate(
        {
            "schema_version": "1.0",
            "event_type": ("camera.detection.completed"),
            "event_id": str(uuid4()),
            "camera_id": "CAM-CLASSIFY-001",
            "frame": {
                "sequence_number": 100,
                "captured_at": now,
                "received_at": now,
            },
            "model": {
                "name": "classification-test",
                "version": "1.0.0",
                "device": "cpu",
            },
            "detections": detections,
            "detection_count": len(detections),
            "inference": {
                "duration_ms": 10.5,
                "processed_at": now,
            },
        }
    )


def create_detection(
    *,
    label: str,
    confidence: float,
) -> dict[str, object]:
    return {
        "class_id": 1,
        "label": label,
        "confidence": confidence,
        "bounding_box": {
            "x_min": 0.1,
            "y_min": 0.1,
            "x_max": 0.8,
            "y_max": 0.8,
        },
    }


def test_zero_detections_create_no_incident() -> None:
    policy = IncidentClassificationPolicy()

    decision = policy.classify(create_event([]))

    assert decision.should_create_incident is False
    assert decision.reason == "no_detections"
    assert decision.confidence == Decimal("0.0000")


def test_unsupported_person_detection_is_ignored() -> None:
    policy = IncidentClassificationPolicy()

    event = create_event(
        [
            create_detection(
                label="person",
                confidence=0.99,
            )
        ]
    )

    decision = policy.classify(event)

    assert decision.should_create_incident is False
    assert decision.reason == ("unsupported_detection_label")


def test_supported_label_below_threshold_is_ignored() -> None:
    policy = IncidentClassificationPolicy()

    event = create_event(
        [
            create_detection(
                label="fire",
                confidence=0.6999,
            )
        ]
    )

    decision = policy.classify(event)

    assert decision.should_create_incident is False
    assert decision.reason == ("confidence_below_threshold")
    assert decision.confidence == Decimal("0.6999")


def test_threshold_is_inclusive() -> None:
    policy = IncidentClassificationPolicy()

    event = create_event(
        [
            create_detection(
                label="fire",
                confidence=0.70,
            )
        ]
    )

    decision = policy.classify(event)

    assert decision.should_create_incident is True
    assert decision.incident_type == "FIRE_DETECTED"
    assert decision.severity is Severity.CRITICAL
    assert decision.priority is Priority.URGENT
    assert decision.confidence == Decimal("0.7000")


def test_detection_label_is_normalized() -> None:
    policy = IncidentClassificationPolicy()

    event = create_event(
        [
            create_detection(
                label="Unattended Bag",
                confidence=0.91,
            )
        ]
    )

    decision = policy.classify(event)

    assert decision.should_create_incident is True
    assert decision.matched_label == ("unattended_bag")
    assert decision.incident_type == ("SUSPICIOUS_OBJECT_DETECTED")


def test_highest_severity_candidate_wins() -> None:
    policy = IncidentClassificationPolicy()

    event = create_event(
        [
            create_detection(
                label="smoke",
                confidence=0.99,
            ),
            create_detection(
                label="knife",
                confidence=0.66,
            ),
        ]
    )

    decision = policy.classify(event)

    assert decision.incident_type == "WEAPON_DETECTED"
    assert decision.severity is Severity.CRITICAL
    assert decision.priority is Priority.URGENT


def test_confidence_breaks_equal_risk_tie() -> None:
    policy = IncidentClassificationPolicy()

    event = create_event(
        [
            create_detection(
                label="weapon",
                confidence=0.72,
            ),
            create_detection(
                label="fire",
                confidence=0.88,
            ),
        ]
    )

    decision = policy.classify(event)

    assert decision.incident_type == "FIRE_DETECTED"
    assert decision.confidence == Decimal("0.8800")


def test_reuse_contract_excludes_terminal_statuses() -> None:
    policy = IncidentClassificationPolicy()

    reusable = policy.reusable_statuses

    assert IncidentStatus.NEW in reusable
    assert IncidentStatus.INVESTIGATING in reusable
    assert IncidentStatus.REOPENED in reusable

    assert IncidentStatus.RESOLVED not in reusable
    assert IncidentStatus.CLOSED not in reusable
    assert IncidentStatus.FALSE_POSITIVE not in reusable

    assert policy.deduplication_window.total_seconds() == 300
