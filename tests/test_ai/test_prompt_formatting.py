"""Tests for conversation formatting into AI-readable text."""
from datetime import datetime

import pytest

from app.analytics.ai.prompts.formatter import format_conversation
from app.models.enums import MessageDirection, MessageType
from app.models.normalized import NormalizedConversation, NormalizedMessage


def _msg(direction: str, text: str, minute: int = 0, msg_type: str = "text") -> NormalizedMessage:
    return NormalizedMessage(
        timestamp=datetime(2025, 1, 10, 10, minute),
        direction=MessageDirection(direction),
        message_type=MessageType(msg_type),
        text_content=text if msg_type == "text" else None,
    )


def test_format_labels_roles():
    conv = NormalizedConversation(
        contact_phone="111",
        messages=[
            _msg("inbound", "Hola, ¿tienen disponibilidad?", 0),
            _msg("outbound", "Sí, claro! ¿Para cuándo?", 5),
        ],
        source="txt_upload",
    )
    transcript = format_conversation(conv)
    assert "CUSTOMER:" in transcript
    assert "BUSINESS:" in transcript
    assert "Hola" in transcript
    assert "claro" in transcript


def test_format_no_names_or_phones():
    """Privacy: no sender names or phone numbers in the transcript."""
    conv = NormalizedConversation(
        contact_phone="+57 300 1234567",
        contact_name="María González",
        messages=[_msg("inbound", "Hola")],
        source="txt_upload",
    )
    transcript = format_conversation(conv)
    assert "María" not in transcript
    assert "+57 300" not in transcript


def test_format_media_messages_labeled():
    conv = NormalizedConversation(
        contact_phone="111",
        messages=[
            _msg("inbound", None, msg_type="image"),
            _msg("outbound", "Gracias por la foto!", 1),
        ],
        source="txt_upload",
    )
    transcript = format_conversation(conv)
    assert "[Image]" in transcript
    assert "Gracias" in transcript


def test_format_system_messages_excluded():
    conv = NormalizedConversation(
        contact_phone="111",
        messages=[
            NormalizedMessage(
                timestamp=datetime(2025, 1, 10, 10, 0),
                direction=MessageDirection.SYSTEM,
                message_type=MessageType.TEXT,
                text_content="Messages are end-to-end encrypted",
            ),
            _msg("inbound", "Hola", 1),
        ],
        source="txt_upload",
    )
    transcript = format_conversation(conv)
    assert "encrypted" not in transcript
    assert "CUSTOMER:" in transcript


def test_format_truncates_long_conversations():
    messages = [
        _msg("inbound" if i % 2 == 0 else "outbound", f"msg {i}", i)
        for i in range(150)
    ]
    conv = NormalizedConversation(contact_phone="111", messages=messages, source="txt_upload")
    transcript = format_conversation(conv)
    assert "truncated" in transcript.lower()
    # Should only have last 100 messages
    lines = [l for l in transcript.split("\n") if "CUSTOMER:" in l or "BUSINESS:" in l]
    assert len(lines) <= 100


def test_format_includes_timestamps():
    conv = NormalizedConversation(
        contact_phone="111",
        messages=[_msg("inbound", "Hola", 0)],
        source="txt_upload",
    )
    transcript = format_conversation(conv)
    assert "2025-01-10" in transcript
    assert "10:00" in transcript
