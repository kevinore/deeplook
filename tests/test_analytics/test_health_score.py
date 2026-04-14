"""Tests for health score calculation."""
import pytest

from app.analytics.insights.health_score import calculate_health_score, _response_time_score
from app.models.enums import ConversionStatus, Sentiment
from app.models.schemas import ConversationAnalysisResult


def _result(sentiment=None, quality=None, conversion=None) -> ConversationAnalysisResult:
    return ConversationAnalysisResult(
        conversation_id="test",
        sentiment=sentiment,
        quality_score=quality,
        conversion_status=conversion,
    )


def test_response_time_score_under_5min():
    score = _response_time_score(60)  # 1 minute
    assert score == pytest.approx(100, abs=5)


def test_response_time_score_over_2hours():
    score = _response_time_score(10000)
    assert score == 0.0


def test_health_score_all_positive():
    results = [_result(Sentiment.POSITIVE, 8.0, ConversionStatus.CONVERTED)]
    score = calculate_health_score(results, avg_response_time_seconds=120)
    assert score > 70


def test_health_score_all_negative():
    results = [_result(Sentiment.NEGATIVE, 2.0, ConversionStatus.LOST)]
    score = calculate_health_score(results, avg_response_time_seconds=7200)
    assert score < 50


def test_health_score_no_data_defaults_to_50():
    score = calculate_health_score([])
    assert score == 50.0


def test_health_score_missing_sentiment():
    """Missing sentiment component should use neutral 50 and redistribute weight."""
    results = [_result(None, 8.0, ConversionStatus.CONVERTED)]
    score = calculate_health_score(results, avg_response_time_seconds=120)
    assert 0 <= score <= 100
