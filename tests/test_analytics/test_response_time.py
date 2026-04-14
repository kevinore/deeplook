"""Tests for response time calculations."""
from datetime import datetime, timedelta

import pytest

from app.analytics.metrics import response_time as rt
from app.models.enums import MessageDirection, MessageType
from app.models.normalized import NormalizedMessage


def _msg(direction: str, minutes_offset: int) -> NormalizedMessage:
    return NormalizedMessage(
        timestamp=datetime(2025, 1, 1, 10, 0) + timedelta(minutes=minutes_offset),
        direction=MessageDirection(direction),
        message_type=MessageType.TEXT,
        text_content="test",
    )


def test_average_response_time():
    msgs = [
        _msg("inbound", 0),
        _msg("outbound", 5),   # 5 min response
        _msg("inbound", 10),
        _msg("outbound", 25),  # 15 min response
    ]
    avg = rt.average(msgs)
    assert avg == pytest.approx(600, abs=1)  # (300 + 900) / 2 = 600 seconds


def test_median_response_time():
    msgs = [
        _msg("inbound", 0),
        _msg("outbound", 2),   # 2 min
        _msg("inbound", 5),
        _msg("outbound", 8),   # 3 min
        _msg("inbound", 10),
        _msg("outbound", 20),  # 10 min
    ]
    med = rt.median(msgs)
    assert med == pytest.approx(180, abs=1)  # median of [120, 180, 600]


def test_unanswered_count():
    # Last message is inbound — unanswered
    msgs = [
        _msg("inbound", 0),
        _msg("outbound", 5),
        _msg("inbound", 10),
        _msg("inbound", 11),  # second consecutive — unanswered
    ]
    assert rt.unanswered_count(msgs) == 2


def test_no_messages_returns_none():
    assert rt.average([]) is None
    assert rt.median([]) is None
    assert rt.percentile_95([]) is None


def test_consecutive_inbound_does_not_reset_timer():
    msgs = [
        _msg("inbound", 0),
        _msg("inbound", 3),   # consecutive inbound — should NOT reset timer
        _msg("outbound", 10), # response is measured from first inbound at min 0
    ]
    avg = rt.average(msgs)
    assert avg == pytest.approx(600, abs=1)  # 10 minutes from first inbound


def test_identical_timestamps_zero_response():
    base = datetime(2025, 1, 1, 10, 0)
    msgs = [
        NormalizedMessage(timestamp=base, direction=MessageDirection.INBOUND, message_type=MessageType.TEXT),
        NormalizedMessage(timestamp=base, direction=MessageDirection.OUTBOUND, message_type=MessageType.TEXT),
    ]
    avg = rt.average(msgs)
    assert avg == 0.0
