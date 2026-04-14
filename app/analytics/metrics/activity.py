"""
Activity pattern metrics — pure math.
"""
from collections import Counter
from datetime import datetime

from app.models.normalized import NormalizedMessage

_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def by_hour(messages: list[NormalizedMessage]) -> dict[int, int]:
    counter = Counter(m.timestamp.hour for m in messages)
    return dict(counter)


def by_day_of_week(messages: list[NormalizedMessage]) -> dict[str, int]:
    counter: dict[str, int] = {}
    for m in messages:
        day_name = _DAY_NAMES[m.timestamp.weekday()]
        counter[day_name] = counter.get(day_name, 0) + 1
    return counter


def peak_hour(messages: list[NormalizedMessage]) -> int | None:
    if not messages:
        return None
    counts = by_hour(messages)
    return max(counts, key=counts.__getitem__)


def quiet_hours(messages: list[NormalizedMessage], threshold_ratio: float = 0.02) -> list[int]:
    """Hours with zero or near-zero (< threshold_ratio of peak) message activity."""
    if not messages:
        return list(range(24))
    counts = by_hour(messages)
    if not counts:
        return []
    peak = max(counts.values())
    threshold = max(1, int(peak * threshold_ratio))
    return sorted(h for h in range(24) if counts.get(h, 0) <= threshold)


def busiest_day(messages: list[NormalizedMessage]) -> str | None:
    if not messages:
        return None
    counts = by_day_of_week(messages)
    return max(counts, key=counts.__getitem__) if counts else None


def first_message_time(messages: list[NormalizedMessage]) -> datetime | None:
    if not messages:
        return None
    return min(m.timestamp for m in messages)


def last_message_time(messages: list[NormalizedMessage]) -> datetime | None:
    if not messages:
        return None
    return max(m.timestamp for m in messages)


def conversation_duration_minutes(messages: list[NormalizedMessage]) -> float | None:
    if len(messages) < 2:
        return None
    first = first_message_time(messages)
    last = last_message_time(messages)
    if first and last:
        return (last - first).total_seconds() / 60
    return None
