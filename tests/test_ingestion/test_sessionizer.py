"""Tests for the conversation sessionizer."""
from datetime import datetime, timedelta

from app.ingestion.sessionizer import (
    DEFAULT_SESSION_GAP_HOURS,
    filter_junk,
    is_junk_conversation,
    split_into_sessions,
)
from app.models.enums import MessageDirection, MessageType
from app.models.normalized import NormalizedConversation, NormalizedMessage


def _msg(direction: str, ts: datetime) -> NormalizedMessage:
    return NormalizedMessage(
        timestamp=ts,
        direction=MessageDirection(direction),
        message_type=MessageType.TEXT,
        text_content="x",
    )


def _conv(messages: list[NormalizedMessage]) -> NormalizedConversation:
    return NormalizedConversation(
        contact_phone="111",
        contact_name="Cliente",
        messages=messages,
        source="waha",
    )


def test_split_keeps_single_session_when_messages_close():
    base = datetime(2025, 1, 1, 10, 0)
    msgs = [
        _msg("inbound", base),
        _msg("outbound", base + timedelta(minutes=5)),
        _msg("inbound", base + timedelta(minutes=15)),
        _msg("outbound", base + timedelta(minutes=20)),
    ]
    sessions = split_into_sessions(_conv(msgs), gap_hours=6.0)
    assert len(sessions) == 1
    assert sessions[0].session_index == 0
    assert sessions[0].session_count == 1
    assert len(sessions[0].messages) == 4


def test_split_creates_multiple_sessions_on_large_gap():
    base = datetime(2025, 1, 1, 10, 0)
    msgs = [
        _msg("inbound", base),
        _msg("outbound", base + timedelta(minutes=5)),
        # 10-hour quiet gap → new session
        _msg("inbound", base + timedelta(hours=10)),
        _msg("outbound", base + timedelta(hours=10, minutes=5)),
        # another huge gap (3 days) → new session
        _msg("inbound", base + timedelta(days=3)),
        _msg("outbound", base + timedelta(days=3, minutes=5)),
    ]
    sessions = split_into_sessions(_conv(msgs), gap_hours=6.0)
    assert len(sessions) == 3
    for i, s in enumerate(sessions):
        assert s.session_index == i
        assert s.session_count == 3
        assert len(s.messages) == 2


def test_split_preserves_chat_metadata():
    base = datetime(2025, 1, 1, 10, 0)
    msgs = [_msg("inbound", base), _msg("outbound", base + timedelta(hours=24))]
    conv = NormalizedConversation(
        contact_phone="111",
        contact_name="Cliente",
        messages=msgs,
        source="waha",
        wa_chat_id="111@c.us",
        wa_unread_count=3,
        wa_is_muted=True,
    )
    sessions = split_into_sessions(conv, gap_hours=6.0)
    assert len(sessions) == 2
    for s in sessions:
        assert s.wa_chat_id == "111@c.us"
        assert s.wa_unread_count == 3
        assert s.wa_is_muted is True


def test_split_gap_zero_returns_unchanged():
    base = datetime(2025, 1, 1, 10, 0)
    msgs = [
        _msg("inbound", base),
        _msg("outbound", base + timedelta(days=10)),  # huge gap, but gap_hours=0
    ]
    sessions = split_into_sessions(_conv(msgs), gap_hours=0)
    assert len(sessions) == 1
    assert len(sessions[0].messages) == 2


def test_split_single_message_keeps_intact():
    base = datetime(2025, 1, 1, 10, 0)
    sessions = split_into_sessions(_conv([_msg("inbound", base)]))
    assert len(sessions) == 1
    assert sessions[0].session_count == 1


def test_is_junk_for_short_conversation():
    base = datetime(2025, 1, 1, 10, 0)
    assert is_junk_conversation(_conv([_msg("inbound", base)])) is True
    assert is_junk_conversation(_conv([_msg("inbound", base), _msg("outbound", base)])) is False


def test_is_junk_does_not_filter_unanswered():
    """A chat with only inbound messages must NOT be junk — that's the 'sin responder' case."""
    base = datetime(2025, 1, 1, 10, 0)
    msgs = [
        _msg("inbound", base),
        _msg("inbound", base + timedelta(minutes=2)),
        _msg("inbound", base + timedelta(minutes=5)),
    ]
    assert is_junk_conversation(_conv(msgs)) is False


def test_filter_junk_drops_singletons():
    base = datetime(2025, 1, 1, 10, 0)
    convs = [
        _conv([_msg("inbound", base)]),
        _conv([_msg("inbound", base), _msg("outbound", base)]),
    ]
    kept = filter_junk(convs)
    assert len(kept) == 1
    assert len(kept[0].messages) == 2


def test_default_gap_hours_is_six():
    assert DEFAULT_SESSION_GAP_HOURS == 6.0
