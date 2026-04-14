"""Integration tests for the full txt parser."""
import asyncio
from pathlib import Path

import pytest

from app.ingestion.parsers.txt_parser import TxtParser

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.mark.asyncio
async def test_parse_spanish_chat():
    content = (FIXTURES / "sample_chat_spanish.txt").read_bytes()
    parser = TxtParser()
    batch = await parser.parse(
        content,
        client_id="test-client",
        business_identifiers=["Wellness By Diego Omar", "Valentina"],
        filename="sample_chat_spanish.txt",
    )
    assert len(batch.conversations) == 1
    conv = batch.conversations[0]
    assert len(conv.messages) > 5
    # Check outbound messages are detected
    outbound = [m for m in conv.messages if m.direction.value == "outbound"]
    inbound = [m for m in conv.messages if m.direction.value == "inbound"]
    assert len(outbound) > 0
    assert len(inbound) > 0


@pytest.mark.asyncio
async def test_parse_multiline_chat():
    content = (FIXTURES / "sample_chat_multiline.txt").read_bytes()
    parser = TxtParser()
    batch = await parser.parse(content, client_id="test-client", business_identifiers=["Negocio"])
    conv = batch.conversations[0]
    # The service description (multi-line) should be merged into one message
    long_msgs = [m for m in conv.messages if m.text_content and len(m.text_content) > 100]
    assert len(long_msgs) >= 1


@pytest.mark.asyncio
async def test_parse_media_chat():
    content = (FIXTURES / "sample_chat_media.txt").read_bytes()
    parser = TxtParser()
    batch = await parser.parse(content, client_id="test-client", business_identifiers=["Spa"])
    conv = batch.conversations[0]
    media_msgs = [m for m in conv.messages if m.message_type.value != "text"]
    assert len(media_msgs) >= 2  # image + audio + document


@pytest.mark.asyncio
async def test_parse_minimal_chat():
    content = (FIXTURES / "sample_chat_minimal.txt").read_bytes()
    parser = TxtParser()
    batch = await parser.parse(content, client_id="test-client", business_identifiers=["Negocio"])
    assert len(batch.conversations) == 1
    assert len(batch.conversations[0].messages) == 3


@pytest.mark.asyncio
async def test_parse_english_chat():
    content = (FIXTURES / "sample_chat_english.txt").read_bytes()
    parser = TxtParser()
    batch = await parser.parse(content, client_id="test-client", business_identifiers=["Beauty Studio"])
    conv = batch.conversations[0]
    assert len(conv.messages) > 5


@pytest.mark.asyncio
async def test_system_messages_filtered():
    """System messages (encryption notice) must not appear in parsed messages."""
    content = (FIXTURES / "sample_chat_spanish.txt").read_bytes()
    parser = TxtParser()
    batch = await parser.parse(content, client_id="test-client", business_identifiers=["Wellness By Diego Omar"])
    conv = batch.conversations[0]
    for msg in conv.messages:
        assert "cifrados" not in (msg.text_content or "")
