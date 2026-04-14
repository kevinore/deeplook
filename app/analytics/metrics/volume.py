"""
Message volume metrics — pure math.
"""
from collections import Counter
from datetime import date

from app.models.enums import MessageDirection
from app.models.normalized import NormalizedConversation, NormalizedMessage


def total_messages(messages: list[NormalizedMessage]) -> int:
    return len(messages)


def by_direction(messages: list[NormalizedMessage]) -> dict[str, int]:
    counts: dict[str, int] = {"inbound": 0, "outbound": 0, "system": 0}
    for m in messages:
        counts[m.direction.value] = counts.get(m.direction.value, 0) + 1
    return counts


def by_type(messages: list[NormalizedMessage]) -> dict[str, int]:
    counter = Counter(m.message_type.value for m in messages)
    return dict(counter)


def by_date(messages: list[NormalizedMessage]) -> dict[date, int]:
    counter: dict[date, int] = Counter(m.timestamp.date() for m in messages)  # type: ignore[assignment]
    return dict(sorted(counter.items()))


def messages_per_conversation(conversations: list[NormalizedConversation]) -> float:
    if not conversations:
        return 0.0
    totals = [len(c.messages) for c in conversations]
    return sum(totals) / len(totals)
