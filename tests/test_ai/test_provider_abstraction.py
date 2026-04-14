"""Tests for AI provider abstraction using mock provider."""
import pytest

from app.analytics.ai.providers.mock_provider import MockProvider


@pytest.mark.asyncio
async def test_mock_provider_returns_valid_response():
    provider = MockProvider()
    response = await provider.analyze(
        system_prompt="Analyze this conversation.",
        user_prompt="[2025-01-01 10:00] CUSTOMER: Hello\n[2025-01-01 10:05] BUSINESS: Hi!",
    )
    assert response.content
    assert response.provider == "mock"
    assert response.cost_usd == 0.0
    assert response.tokens_input > 0


@pytest.mark.asyncio
async def test_mock_provider_deterministic():
    """Same input produces same output."""
    provider = MockProvider()
    prompt = "test conversation"
    r1 = await provider.analyze("sys", prompt)
    r2 = await provider.analyze("sys", prompt)
    assert r1.content == r2.content


@pytest.mark.asyncio
async def test_mock_provider_different_inputs():
    """Different inputs produce different outputs."""
    provider = MockProvider()
    r1 = await provider.analyze("sys", "conversation A about pricing")
    r2 = await provider.analyze("sys", "conversation B about complaints")
    # They may differ (hash-based)
    assert r1.provider == r2.provider == "mock"


def test_mock_estimate_cost():
    provider = MockProvider()
    assert provider.estimate_cost(1000, 500) == 0.0
