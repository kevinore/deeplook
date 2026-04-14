"""Tests for volume metrics."""
from datetime import datetime, timedelta

import pytest

from app.analytics.metrics.volume import by_date, by_direction, by_type, messages_per_conversation, total_messages
from app.models.enums import MessageDirection, MessageType
from app.models.normalized import NormalizedConversation, NormalizedMessage


def _msg(direction: str, msg_type: str = "text", day_offset: int = 0) -> NormalizedMessage:
    return NormalizedMessage(
        timestamp=datetime(2025, 1, 1) + timedelta(days=day_offset),
        direction=MessageDirection(direction),
        message_type=MessageType(msg_type),
        text_content="test",
    )


def test_total_messages():
    msgs = [_msg("inbound"), _msg("outbound"), _msg("inbound")]
    assert total_messages(msgs) == 3


def test_total_messages_empty():
    assert total_messages([]) == 0


def test_by_direction():
    msgs = [_msg("inbound"), _msg("outbound"), _msg("outbound"), _msg("inbound")]
    counts = by_direction(msgs)
    assert counts["inbound"] == 2
    assert counts["outbound"] == 2


def test_by_type():
    msgs = [_msg("inbound", "text"), _msg("outbound", "image"), _msg("inbound", "text")]
    counts = by_type(msgs)
    assert counts["text"] == 2
    assert counts["image"] == 1


def test_by_date():
    msgs = [_msg("inbound", day_offset=0), _msg("outbound", day_offset=0), _msg("inbound", day_offset=1)]
    counts = by_date(msgs)
    assert len(counts) == 2
    total = sum(counts.values())
    assert total == 3


def test_messages_per_conversation():
    c1 = NormalizedConversation(contact_phone="111", messages=[_msg("inbound"), _msg("outbound")], source="txt_upload")
    c2 = NormalizedConversation(contact_phone="222", messages=[_msg("inbound"), _msg("outbound"), _msg("inbound"), _msg("outbound")], source="txt_upload")
    avg = messages_per_conversation([c1, c2])
    assert avg == pytest.approx(3.0)


def test_messages_per_conversation_empty():
    assert messages_per_conversation([]) == 0.0
