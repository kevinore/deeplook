"""
Response time calculations — pure math, no AI, no external calls.
"""
import statistics
from collections import defaultdict
from datetime import datetime

from app.models.enums import MessageDirection
from app.models.normalized import NormalizedMessage


def _collect_response_times(messages: list[NormalizedMessage]) -> list[float]:
    """
    Collect response times in seconds.

    Logic: iterate chronologically. When INBOUND is found, start timer.
    The next OUTBOUND closes it. Consecutive INBOUNDs don't reset the timer.
    Consecutive OUTBOUNDs (follow-ups) are ignored.
    """
    sorted_msgs = sorted(messages, key=lambda m: m.timestamp)
    response_times: list[float] = []
    waiting_since: datetime | None = None

    for msg in sorted_msgs:
        if msg.direction == MessageDirection.INBOUND and waiting_since is None:
            waiting_since = msg.timestamp
        elif msg.direction == MessageDirection.OUTBOUND and waiting_since is not None:
            delta = (msg.timestamp - waiting_since).total_seconds()
            response_times.append(max(0.0, delta))
            waiting_since = None

    return response_times


def average(messages: list[NormalizedMessage]) -> float | None:
    times = _collect_response_times(messages)
    return statistics.mean(times) if times else None


def median(messages: list[NormalizedMessage]) -> float | None:
    times = _collect_response_times(messages)
    return statistics.median(times) if times else None


def percentile_95(messages: list[NormalizedMessage]) -> float | None:
    times = _collect_response_times(messages)
    if not times:
        return None
    sorted_times = sorted(times)
    idx = int(0.95 * len(sorted_times))
    return sorted_times[min(idx, len(sorted_times) - 1)]


def max_response_time(messages: list[NormalizedMessage]) -> float | None:
    times = _collect_response_times(messages)
    return max(times) if times else None


def unanswered_count(messages: list[NormalizedMessage]) -> int:
    """Count customer messages that never got a business reply (conversation ended with customer msg)."""
    sorted_msgs = sorted(messages, key=lambda m: m.timestamp)
    count = 0
    waiting = False
    for msg in sorted_msgs:
        if msg.direction == MessageDirection.INBOUND:
            waiting = True
        elif msg.direction == MessageDirection.OUTBOUND:
            waiting = False
    # If last message was inbound, it went unanswered
    if waiting:
        # Count consecutive trailing INBOUND messages
        for msg in reversed(sorted_msgs):
            if msg.direction == MessageDirection.INBOUND:
                count += 1
            else:
                break
    return count


def first_response_time(messages: list[NormalizedMessage]) -> float | None:
    """
    First response time: seconds from the customer's first message to the business's first reply.

    If the conversation opens with business messages (welcome/greeting), those are skipped —
    measurement starts from the first INBOUND message. Returns None if the business never replies.
    """
    sorted_msgs = sorted(messages, key=lambda m: m.timestamp)
    first_inbound_time: datetime | None = None

    for msg in sorted_msgs:
        if msg.direction == MessageDirection.INBOUND and first_inbound_time is None:
            first_inbound_time = msg.timestamp
        elif msg.direction == MessageDirection.OUTBOUND and first_inbound_time is not None:
            delta = (msg.timestamp - first_inbound_time).total_seconds()
            return max(0.0, delta)

    return None  # Business never replied


def by_hour(messages: list[NormalizedMessage]) -> dict[int, float]:
    """Average response time grouped by hour of day (0-23)."""
    sorted_msgs = sorted(messages, key=lambda m: m.timestamp)
    hour_times: dict[int, list[float]] = defaultdict(list)
    waiting_since: datetime | None = None
    hour_of_wait: int | None = None

    for msg in sorted_msgs:
        if msg.direction == MessageDirection.INBOUND and waiting_since is None:
            waiting_since = msg.timestamp
            hour_of_wait = msg.timestamp.hour
        elif msg.direction == MessageDirection.OUTBOUND and waiting_since is not None:
            delta = (msg.timestamp - waiting_since).total_seconds()
            if hour_of_wait is not None:
                hour_times[hour_of_wait].append(max(0.0, delta))
            waiting_since = None
            hour_of_wait = None

    return {h: statistics.mean(times) for h, times in hour_times.items()}
