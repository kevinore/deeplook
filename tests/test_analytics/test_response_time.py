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


def test_unanswered_count_is_one_when_last_message_is_inbound():
    """`unanswered_count` is now 0 or 1 per conversation (chat-level), not message count."""
    msgs = [
        _msg("inbound", 0),
        _msg("outbound", 5),
        _msg("inbound", 10),
        _msg("inbound", 11),
        _msg("inbound", 12),  # multiple trailing inbounds, but it's still ONE chat unanswered
    ]
    assert rt.unanswered_count(msgs) == 1
    assert rt.is_unanswered(msgs) is True


def test_unanswered_count_is_zero_when_business_replied_last():
    msgs = [
        _msg("inbound", 0),
        _msg("inbound", 1),
        _msg("outbound", 5),  # business has the last word
    ]
    assert rt.unanswered_count(msgs) == 0
    assert rt.is_unanswered(msgs) is False


def test_trailing_inbound_messages_diagnostic():
    """`trailing_inbound_messages` returns the diagnostic count of consecutive customer msgs at end."""
    msgs = [
        _msg("inbound", 0),
        _msg("outbound", 5),
        _msg("inbound", 10),
        _msg("inbound", 11),
        _msg("inbound", 12),
    ]
    assert rt.trailing_inbound_messages(msgs) == 3
    msgs2 = [_msg("inbound", 0), _msg("outbound", 5)]
    assert rt.trailing_inbound_messages(msgs2) == 0


def test_no_messages_returns_none():
    assert rt.average([]) is None
    assert rt.median([]) is None
    assert rt.percentile_95([]) is None
    assert rt.unanswered_count([]) == 0


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


def test_percentile_of_values_uses_linear_interpolation():
    """Old impl `sorted(v)[int(0.95*n)]` returned the max for n<20 — fixed via interpolation."""
    # 10 values 1..10. p95 should be ~9.55, NOT 10 (the old buggy result).
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    p95 = rt.percentile_of_values(values, 95.0)
    assert p95 == pytest.approx(9.55, abs=0.01)


def test_percentile_of_values_single_value():
    assert rt.percentile_of_values([42.0], 95.0) == 42.0


def test_percentile_of_values_empty():
    assert rt.percentile_of_values([], 95.0) is None


def test_percentile_95_messages_uses_interpolation():
    """End-to-end: 10 conversations with response times 1..10s → p95 ~9.55s."""
    base = datetime(2025, 1, 1, 10, 0)
    msgs = []
    for i in range(1, 11):
        # Each pair: inbound at offset 0, outbound at offset i seconds → response time = i
        msgs.append(NormalizedMessage(timestamp=base + timedelta(seconds=i * 100), direction=MessageDirection.INBOUND, message_type=MessageType.TEXT))
        msgs.append(NormalizedMessage(timestamp=base + timedelta(seconds=i * 100 + i), direction=MessageDirection.OUTBOUND, message_type=MessageType.TEXT))
    p95 = rt.percentile_95(msgs)
    assert p95 == pytest.approx(9.55, abs=0.01)


def test_first_response_time_basic():
    """Customer asks at minute 0, business responds at minute 7 → FRT = 420s."""
    msgs = [_msg("inbound", 0), _msg("outbound", 7)]
    assert rt.first_response_time(msgs) == pytest.approx(420.0, abs=1)


def test_first_response_time_skips_business_greeting_before_customer():
    """Pre-customer business greetings are ignored — FRT starts at first INBOUND."""
    msgs = [
        _msg("outbound", 0),    # business greeting before customer message
        _msg("inbound", 5),     # customer arrives
        _msg("outbound", 8),    # 3-min response
    ]
    assert rt.first_response_time(msgs) == pytest.approx(180.0, abs=1)


def test_first_response_time_excludes_auto_reply():
    """An OUTBOUND fired < 10s after the customer's first message AND followed by
    a real human reply within 30 minutes is treated as an auto-reply."""
    base = datetime(2025, 1, 1, 10, 0)
    msgs = [
        NormalizedMessage(timestamp=base, direction=MessageDirection.INBOUND, message_type=MessageType.TEXT),
        # auto-reply in 2 seconds
        NormalizedMessage(timestamp=base + timedelta(seconds=2), direction=MessageDirection.OUTBOUND, message_type=MessageType.TEXT),
        # real human reply 8 minutes later
        NormalizedMessage(timestamp=base + timedelta(minutes=8), direction=MessageDirection.OUTBOUND, message_type=MessageType.TEXT),
    ]
    # FRT should be 8 minutes, NOT 2 seconds
    assert rt.first_response_time(msgs) == pytest.approx(480.0, abs=1)


def test_first_response_time_quick_reply_is_not_treated_as_auto_when_no_followup():
    """A quick reply with no follow-up within 30 minutes is the real reply (real fast humans exist!)."""
    base = datetime(2025, 1, 1, 10, 0)
    msgs = [
        NormalizedMessage(timestamp=base, direction=MessageDirection.INBOUND, message_type=MessageType.TEXT),
        NormalizedMessage(timestamp=base + timedelta(seconds=3), direction=MessageDirection.OUTBOUND, message_type=MessageType.TEXT),
        # next message is a NEW customer message, not a follow-up reply
        NormalizedMessage(timestamp=base + timedelta(minutes=10), direction=MessageDirection.INBOUND, message_type=MessageType.TEXT),
    ]
    assert rt.first_response_time(msgs) == pytest.approx(3.0, abs=1)


def test_first_response_time_returns_none_if_business_never_replies():
    msgs = [_msg("inbound", 0), _msg("inbound", 10)]
    assert rt.first_response_time(msgs) is None
