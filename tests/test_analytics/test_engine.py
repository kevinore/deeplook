"""Integration tests for AnalyticsEngine using the mock provider."""
from datetime import datetime, timedelta

import pytest

from app.analytics.engine import AnalyticsEngine
from app.analytics.ai.providers.mock_provider import MockProvider
from app.models.enums import MessageDirection, MessageType
from app.models.normalized import NormalizedConversation, NormalizedMessage


def _make_conversation(num_inbound: int = 3, num_outbound: int = 3) -> NormalizedConversation:
    messages = []
    base = datetime(2025, 1, 10, 9, 0)
    for i in range(num_inbound + num_outbound):
        direction = MessageDirection.INBOUND if i % 2 == 0 else MessageDirection.OUTBOUND
        messages.append(
            NormalizedMessage(
                timestamp=base + timedelta(minutes=i * 10),
                direction=direction,
                message_type=MessageType.TEXT,
                text_content=f"Message {i}",
            )
        )
    return NormalizedConversation(
        contact_phone="+57 300 0000000",
        contact_name="Test Customer",
        messages=messages,
        source="txt_upload",
    )


@pytest.mark.asyncio
async def test_analyze_conversation_returns_result():
    engine = AnalyticsEngine(ai_provider=MockProvider())
    conv = _make_conversation()
    result = await engine.analyze_conversation(conv, "conv-test-001")

    assert result.conversation_id == "conv-test-001"
    assert result.total_messages == 6
    assert result.ai_provider == "mock"
    assert result.health_score is not None
    assert 0 <= result.health_score <= 100


@pytest.mark.asyncio
async def test_analyze_conversation_metrics_populated():
    engine = AnalyticsEngine(ai_provider=MockProvider())
    conv = _make_conversation()
    result = await engine.analyze_conversation(conv, "conv-metrics-test")

    assert result.inbound_count > 0
    assert result.outbound_count > 0
    assert result.avg_response_time_seconds is not None
    assert result.duration_minutes is not None


@pytest.mark.asyncio
async def test_analyze_conversation_recommendations_generated():
    engine = AnalyticsEngine(ai_provider=MockProvider())
    conv = _make_conversation()
    result = await engine.analyze_conversation(conv, "conv-rec-test")

    assert isinstance(result.recommendations, list)
    assert len(result.recommendations) >= 1


@pytest.mark.asyncio
async def test_analyze_batch():
    engine = AnalyticsEngine(ai_provider=MockProvider())
    convs = [
        (_make_conversation(), "conv-001"),
        (_make_conversation(2, 5), "conv-002"),
        (_make_conversation(5, 2), "conv-003"),
    ]
    progress_calls = []

    def on_progress(processed, total):
        progress_calls.append((processed, total))

    results = await engine.analyze_batch(convs, on_progress=on_progress)

    assert len(results) == 3
    assert progress_calls[-1] == (3, 3)
    for r in results:
        assert r.conversation_id in ("conv-001", "conv-002", "conv-003")


@pytest.mark.asyncio
async def test_analyze_empty_conversation():
    engine = AnalyticsEngine(ai_provider=MockProvider())
    conv = NormalizedConversation(contact_phone="unknown", messages=[], source="txt_upload")
    result = await engine.analyze_conversation(conv, "conv-empty")

    assert result.conversation_id == "conv-empty"
    assert result.total_messages == 0
