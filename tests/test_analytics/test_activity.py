"""Tests for activity pattern metrics."""
from datetime import datetime, timedelta

import pytest

from app.analytics.metrics.activity import (
    busiest_day,
    by_day_of_week,
    by_hour,
    conversation_duration_minutes,
    first_message_time,
    last_message_time,
    peak_hour,
    quiet_hours,
)
from app.models.enums import MessageDirection, MessageType
from app.models.normalized import NormalizedMessage


def _msg(hour: int = 10, day_offset: int = 0, weekday_date: datetime = None) -> NormalizedMessage:
    base = weekday_date or datetime(2025, 1, 6)  # Monday
    ts = base.replace(hour=hour) + timedelta(days=day_offset)
    return NormalizedMessage(
        timestamp=ts,
        direction=MessageDirection.INBOUND,
        message_type=MessageType.TEXT,
        text_content="test",
    )


def test_by_hour():
    msgs = [_msg(10), _msg(10), _msg(14), _msg(10)]
    counts = by_hour(msgs)
    assert counts[10] == 3
    assert counts[14] == 1


def test_peak_hour():
    msgs = [_msg(10), _msg(10), _msg(14)]
    assert peak_hour(msgs) == 10


def test_peak_hour_empty():
    assert peak_hour([]) is None


def test_by_day_of_week():
    # Jan 6 2025 = Monday
    monday = datetime(2025, 1, 6)
    tuesday = datetime(2025, 1, 7)
    msgs = [
        _msg(weekday_date=monday),
        _msg(weekday_date=monday),
        _msg(weekday_date=tuesday),
    ]
    counts = by_day_of_week(msgs)
    assert counts["Monday"] == 2
    assert counts["Tuesday"] == 1


def test_busiest_day():
    monday = datetime(2025, 1, 6)
    wednesday = datetime(2025, 1, 8)
    msgs = [_msg(weekday_date=wednesday)] * 3 + [_msg(weekday_date=monday)]
    assert busiest_day(msgs) == "Wednesday"


def test_first_last_message_time():
    msgs = [_msg(9), _msg(10), _msg(14)]
    first = first_message_time(msgs)
    last = last_message_time(msgs)
    assert first.hour == 9
    assert last.hour == 14


def test_conversation_duration_minutes():
    msgs = [_msg(10), _msg(11)]  # 1 hour apart
    duration = conversation_duration_minutes(msgs)
    assert duration == pytest.approx(60.0)


def test_conversation_duration_single_message():
    assert conversation_duration_minutes([_msg(10)]) is None


def test_quiet_hours():
    # Only hour 10 has messages — all others should be quiet
    msgs = [_msg(10), _msg(10)]
    quiet = quiet_hours(msgs)
    assert 10 not in quiet
    assert 0 in quiet
    assert 23 in quiet
