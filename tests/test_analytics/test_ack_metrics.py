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
    """
    Timestamps are naive UTC; Colombia = UTC-5.
    4 AM Colombia = 09:00 UTC (out of hours) → excluded from denominator.
    10 AM Colombia = 15:00 UTC (in hours) → answered within 1h → counts.
    2 PM Colombia = 19:00 UTC (in hours) → replied 2h later → missed.
    Expected: 1 answered / 2 in-hours = 50%.
    """
    msgs = [
        # 4 AM Colombia (09:00 UTC) — out of hours → excluded
        _msg("inbound",  datetime(2025, 1, 1, 9, 0)),
        _msg("outbound", datetime(2025, 1, 1, 9, 30)),
        # 10 AM Colombia (15:00 UTC) — in hours, replied at 15:15 UTC (15 min) → answered
        _msg("inbound",  datetime(2025, 1, 1, 15, 0)),
        _msg("outbound", datetime(2025, 1, 1, 15, 15)),
        # 2 PM Colombia (19:00 UTC) — in hours, replied at 21:00 UTC (2 h) → missed
        _msg("inbound",  datetime(2025, 1, 1, 19, 0)),
        _msg("outbound", datetime(2025, 1, 1, 21, 0)),
    ]
    score = ack_metrics.operational_coverage_score(msgs)
    assert score == 50.0  # 1 of 2 in-hours waits answered within 1h


def test_operational_coverage_returns_none_with_no_in_hours_inbound():
    # 3 AM Colombia = 08:00 UTC — out of hours → no in-hours denominator → None
    msgs = [
        _msg("inbound",  datetime(2025, 1, 1, 8, 0)),
        _msg("outbound", datetime(2025, 1, 1, 8, 30)),
    ]
    assert ack_metrics.operational_coverage_score(msgs) is None


def test_operational_coverage_unanswered_waits_count_against():
    # 10 AM Colombia = 15:00 UTC — in hours, no reply → 0/1 = 0%
    msgs = [
        _msg("inbound", datetime(2025, 1, 1, 15, 0)),
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
