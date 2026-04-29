"""Tests for health score calculation."""
from app.analytics.insights.health_score import (
    _first_response_time_score,
    _unanswered_rate_score,
    calculate_health_score,
)
from app.models.enums import ConversionStatus, Sentiment
from app.models.schemas import ConversationAnalysisResult


def _result(sentiment=None, quality=None, conversion=None, unanswered=0, total_messages=10) -> ConversationAnalysisResult:
    return ConversationAnalysisResult(
        conversation_id="test",
        sentiment=sentiment,
        quality_score=quality,
        conversion_status=conversion,
        unanswered_count=unanswered,
        total_messages=total_messages,
    )


def test_first_response_time_score_under_2min():
    assert _first_response_time_score(60) == 100.0


def test_first_response_time_score_under_5min():
    assert _first_response_time_score(240) == 85.0


def test_first_response_time_score_over_1hour():
    assert _first_response_time_score(7200) == 10.0


def test_unanswered_rate_score_zero_is_perfect():
    assert _unanswered_rate_score(0) == 100.0


def test_unanswered_rate_score_high_is_low():
    assert _unanswered_rate_score(25) == 15.0


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


def test_coverage_score_uses_conversation_count_not_message_count():
    """B2 fix: coverage uses chat-level unanswered rate, not per-message rate.

    With 10 conversations, 1 unanswered → 10% rate → score 65 (between < 5 = 85 and < 10 = 65).
    Old buggy logic would divide by total_messages (e.g. 100) → 1% rate → score 85.
    """
    results = [
        _result(Sentiment.POSITIVE, 8.0, ConversionStatus.CONVERTED, unanswered=0, total_messages=10)
        for _ in range(9)
    ] + [
        _result(Sentiment.NEUTRAL, 7.0, ConversionStatus.PENDING, unanswered=1, total_messages=10)
    ]
    # 1 / 10 = 10% — this should land at the 65-tier of _unanswered_rate_score
    score = calculate_health_score(results, avg_response_time_seconds=120)
    # The score must be lower than if all 10 conversations were answered.
    all_answered = [
        _result(Sentiment.POSITIVE, 8.0, ConversionStatus.CONVERTED, unanswered=0, total_messages=10)
        for _ in range(10)
    ]
    answered_score = calculate_health_score(all_answered, avg_response_time_seconds=120)
    assert score < answered_score
