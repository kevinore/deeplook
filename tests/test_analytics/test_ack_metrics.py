"""Tests for ack-derived deterministic metrics."""
from datetime import datetime, timedelta, timezone

import pytest

from app.analytics.metrics import ack_metrics
from app.models.enums import MessageDirection, MessageType
from app.models.normalized import NormalizedMessage


def _msg(direction: str, ts: datetime, ack: int | None = None) -> NormalizedMessage:
    return NormalizedMessage(
        timestamp=ts,
        direction=MessageDirection(direction),
        message_type=MessageType.TEXT,
        text_content="x",
        ack=ack,
    )


# ─── delivery_rate / read_rate ────────────────────────────────────────────────


def test_rates_return_none_when_no_ack_info():
    base = datetime(2025, 1, 1, 10, 0)
    msgs = [
        _msg("inbound", base),
        _msg("outbound", base + timedelta(minutes=1), ack=None),
    ]
    assert ack_metrics.delivery_rate(msgs) is None
    assert ack_metrics.read_rate(msgs) is None


def test_delivery_rate_counts_server_or_higher():
    base = datetime(2025, 1, 1, 10, 0)
    msgs = [
        _msg("outbound", base, ack=0),         # PENDING — not delivered
        _msg("outbound", base + timedelta(minutes=1), ack=1),    # SERVER
        _msg("outbound", base + timedelta(minutes=2), ack=3),    # READ
        _msg("outbound", base + timedelta(minutes=3), ack=2),    # DEVICE
    ]
    # 3/4 delivered (>=1)
    assert ack_metrics.delivery_rate(msgs) == 75.0


def test_read_rate_counts_only_ack_3_or_4():
    base = datetime(2025, 1, 1, 10, 0)
    msgs = [
        _msg("outbound", base, ack=1),                               # SERVER — not read
        _msg("outbound", base + timedelta(minutes=1), ack=3),        # READ
        _msg("outbound", base + timedelta(minutes=2), ack=4),        # PLAYED
        _msg("outbound", base + timedelta(minutes=3), ack=2),        # DEVICE — not read
    ]
    # 2/4 read
    assert ack_metrics.read_rate(msgs) == 50.0


def test_read_rate_inbound_messages_excluded():
    base = datetime(2025, 1, 1, 10, 0)
    msgs = [
        _msg("inbound", base, ack=3),  # inbound ack is irrelevant
        _msg("outbound", base + timedelta(minutes=1), ack=3),
    ]
    assert ack_metrics.read_rate(msgs) == 100.0


# ─── ghosting detection ───────────────────────────────────────────────────────


def test_is_ghosted_true_when_last_outbound_read_and_more_than_24h_ago():
    base = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
    msgs = [
        _msg("inbound", base),
        _msg("outbound", base + timedelta(minutes=2), ack=3),  # business replied + read
    ]
    now = base + timedelta(days=2)  # 48h later
    assert ack_metrics.is_ghosted(msgs, now=now) is True


def test_is_ghosted_false_when_within_24h():
    base = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
    msgs = [
        _msg("inbound", base),
        _msg("outbound", base + timedelta(minutes=2), ack=3),
    ]
    now = base + timedelta(hours=12)
    assert ack_metrics.is_ghosted(msgs, now=now) is False


def test_is_ghosted_false_when_last_message_inbound():
    """Customer wrote last → not ghosted; this is "sin responder"."""
    base = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
    msgs = [
        _msg("outbound", base, ack=3),
        _msg("inbound", base + timedelta(hours=2)),
    ]
    now = base + timedelta(days=2)
    assert ack_metrics.is_ghosted(msgs, now=now) is False


def test_is_ghosted_false_when_ack_is_pending():
    """If our last message wasn't even read, the customer didn't ghost — they didn't see it."""
    base = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
    msgs = [
        _msg("inbound", base),
        _msg("outbound", base + timedelta(minutes=2), ack=1),  # SERVER, not READ
    ]
    now = base + timedelta(days=2)
    assert ack_metrics.is_ghosted(msgs, now=now) is False


# ─── last_business_msg_ack ────────────────────────────────────────────────────


def test_last_business_msg_ack_returns_most_recent():
    base = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
    msgs = [
        _msg("outbound", base, ack=1),
        _msg("outbound", base + timedelta(minutes=1), ack=3),
        _msg("inbound", base + timedelta(minutes=2)),
    ]
    assert ack_metrics.last_business_msg_ack(msgs) == 3


def test_last_business_msg_ack_none_when_no_outbound():
    base = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
    msgs = [_msg("inbound", base), _msg("inbound", base + timedelta(minutes=1))]
    assert ack_metrics.last_business_msg_ack(msgs) is None


# ─── operational coverage ─────────────────────────────────────────────────────


def test_operational_coverage_only_in_hours_messages_count():
    """A 4 AM customer message followed by a 9 AM reply should NOT be in the score's denominator."""
    msgs = [
        # 4 AM inbound (out of hours) → excluded
        _msg("inbound", datetime(2025, 1, 1, 4, 0)),
        _msg("outbound", datetime(2025, 1, 1, 4, 30)),
        # 10 AM inbound, replied at 10:15 (within 1h) → counts as answered
        _msg("inbound", datetime(2025, 1, 1, 10, 0)),
        _msg("outbound", datetime(2025, 1, 1, 10, 15)),
        # 14:00 inbound, replied at 16:00 (over 1h) → counts as missed
        _msg("inbound", datetime(2025, 1, 1, 14, 0)),
        _msg("outbound", datetime(2025, 1, 1, 16, 0)),
    ]
    score = ack_metrics.operational_coverage_score(msgs)
    assert score == 50.0  # 1 of 2 in-hours waits answered within 1h


def test_operational_coverage_returns_none_with_no_in_hours_inbound():
    msgs = [
        _msg("inbound", datetime(2025, 1, 1, 3, 0)),
        _msg("outbound", datetime(2025, 1, 1, 3, 30)),
    ]
    assert ack_metrics.operational_coverage_score(msgs) is None


def test_operational_coverage_unanswered_waits_count_against():
    msgs = [
        _msg("inbound", datetime(2025, 1, 1, 10, 0)),
        # No reply at all
    ]
    assert ack_metrics.operational_coverage_score(msgs) == 0.0


# ─── out_of_hours_rate ────────────────────────────────────────────────────────


def test_out_of_hours_rate_basic():
    msgs = [
        _msg("inbound", datetime(2025, 1, 1, 22, 0)),  # after hours
        _msg("inbound", datetime(2025, 1, 1, 4, 0)),   # after hours
        _msg("inbound", datetime(2025, 1, 1, 10, 0)),  # in hours
        _msg("outbound", datetime(2025, 1, 1, 10, 5)),  # outbound — ignored
    ]
    assert ack_metrics.out_of_hours_rate(msgs) == pytest.approx(66.7, abs=0.1)


def test_out_of_hours_rate_none_when_no_inbound():
    msgs = [_msg("outbound", datetime(2025, 1, 1, 10, 0), ack=3)]
    assert ack_metrics.out_of_hours_rate(msgs) is None
