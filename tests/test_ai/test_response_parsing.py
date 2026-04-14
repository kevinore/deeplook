"""Tests for AI response parsing."""
import json
import pytest

from app.analytics.ai.prompts.response_parser import parse_ai_response
from app.models.enums import ConversionStatus, Sentiment


def _valid_json() -> str:
    return json.dumps({
        "sentiment": "positive",
        "sentiment_score": 0.8,
        "sentiment_reason": "Customer seemed happy.",
        "primary_topic": "appointment booking",
        "secondary_topics": ["pricing"],
        "quality_score": 8.5,
        "quality_breakdown": {
            "helpfulness": 9.0, "tone": 8.0, "completeness": 8.5, "speed_perception": 8.5
        },
        "conversion_status": "converted",
        "conversion_reason": "Customer booked appointment.",
        "summary": "Customer booked an appointment.",
        "key_points": ["Fast response", "Professional tone"],
    })


def test_valid_response():
    result = parse_ai_response(_valid_json(), "conv-123")
    assert result.sentiment == Sentiment.POSITIVE
    assert result.sentiment_score == pytest.approx(0.8)
    assert result.primary_topic == "appointment booking"
    assert result.quality_score == pytest.approx(8.5)
    assert result.conversion_status == ConversionStatus.CONVERTED


def test_invalid_json_returns_defaults():
    result = parse_ai_response("not json at all", "conv-123")
    assert result.conversation_id == "conv-123"
    assert result.sentiment is None


def test_missing_fields_use_defaults():
    result = parse_ai_response(json.dumps({"sentiment": "neutral"}), "conv-x")
    assert result.sentiment == Sentiment.NEUTRAL
    assert result.quality_score == pytest.approx(5.0)
    assert result.conversion_status == ConversionStatus.NOT_APPLICABLE


def test_unknown_sentiment_normalizes():
    result = parse_ai_response(json.dumps({"sentiment": "very positive"}), "conv-x")
    assert result.sentiment == Sentiment.POSITIVE


def test_markdown_fence_stripped():
    content = "```json\n" + _valid_json() + "\n```"
    result = parse_ai_response(content, "conv-x")
    assert result.sentiment == Sentiment.POSITIVE


def test_extra_fields_ignored():
    data = json.loads(_valid_json())
    data["unknown_field"] = "should be ignored"
    result = parse_ai_response(json.dumps(data), "conv-x")
    assert result.sentiment == Sentiment.POSITIVE
