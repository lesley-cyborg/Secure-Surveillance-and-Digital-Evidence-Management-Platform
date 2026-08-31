from __future__ import annotations

from app.db.models.enums import CustodyEventType

_API_APPENDABLE_EVENTS: frozenset[CustodyEventType] = frozenset(
    {
        CustodyEventType.VIEWED,
        CustodyEventType.EXPORTED,
        CustodyEventType.VERIFIED,
        CustodyEventType.RETURNED,
    }
)


def is_api_appendable(event_type: CustodyEventType) -> bool:
    """Return True if the event type may be appended via the public API."""
    return event_type in _API_APPENDABLE_EVENTS


def validate_api_event_type(event_type: CustodyEventType) -> None:
    """Raise ValueError if the event type is not allowed via the public API."""
    if not is_api_appendable(event_type):
        allowed_types = ", ".join(
            event.value
            for event in sorted(
                _API_APPENDABLE_EVENTS,
                key=lambda item: item.value,
            )
        )

        raise ValueError(
            f"Event type '{event_type.value}' may not be appended via the API. "
            f"Allowed types: {allowed_types}"
        )
