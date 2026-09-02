from __future__ import annotations

from datetime import date

from app.schemas.vct_circuit import EventStatus

_COMPLETED = frozenset({"completed", "complete", "finished", "final", "over"})
_ONGOING = frozenset({"ongoing", "live", "in progress", "in-progress", "playing"})
_UPCOMING = frozenset({"upcoming", "tbd", "scheduled", "unplayed", "coming soon"})


def canonical_event_status(
    value: str | None,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    today: date | None = None,
) -> EventStatus | None:
    text = (value or "").strip().lower()
    if text in _COMPLETED:
        return EventStatus.COMPLETED
    if text in _ONGOING:
        return EventStatus.ONGOING
    if text in _UPCOMING:
        return EventStatus.UPCOMING
    if text in {item.value.lower() for item in EventStatus}:
        return EventStatus(text.upper())
    if today is None:
        return None
    if end_date is not None and end_date < today:
        return EventStatus.COMPLETED
    if start_date is not None and start_date > today:
        return EventStatus.UPCOMING
    if start_date is not None and end_date is not None:
        return EventStatus.ONGOING
    return None


def is_completed_match_status(value: str | None) -> bool:
    text = (value or "").strip().lower()
    if not text:
        return False
    if text in _COMPLETED:
        return True
    if text in _ONGOING or text in _UPCOMING:
        return False
    if "d" in text or "h" in text or ":" in text:
        return False
    return False
