"""
Business health score calculator (0-100). Rule-based, no AI.

LATAM-optimized 6-component formula:
- Response Speed        25%  First response time vs LATAM benchmarks
- Response Coverage     15%  Unanswered message rate
- Customer Sentiment    20%  Weighted positive/neutral/negative split
- Conversation Quality  15%  Average quality score × 10
- Conversion Effectiveness 15%  Conversion rate as percentage
- Operational Coverage  10%  Default 50 (can't detect from .txt exports)

Score interpretation:
85-100  Excelente — highly effective WhatsApp operation
70-84   Bueno     — good with clear areas to improve
55-69   Regular   — losing sales due to operational gaps
40-54   Deficiente — serious issues, immediate action needed
0-39    Crítico   — channel hurting more than helping
"""
from app.models.enums import ConversionStatus, Sentiment
from app.models.schemas import ConversationAnalysisResult


def _first_response_time_score(seconds: float | None) -> float | None:
    """0-100 score based on first response time. LATAM benchmarks from §7 of metrics framework."""
    if seconds is None:
        return None
    if seconds < 120:    # < 2 min — Excellent
        return 100.0
    if seconds < 300:    # < 5 min — Good
        return 85.0
    if seconds < 900:    # < 15 min — Acceptable
        return 65.0
    if seconds < 1800:   # < 30 min — Poor
        return 45.0
    if seconds < 3600:   # < 1 hour — Critical
        return 25.0
    return 10.0          # > 1 hour — Critical


def _unanswered_rate_score(rate_pct: float) -> float:
    """0-100 score based on percentage of unanswered messages."""
    if rate_pct == 0:
        return 100.0
    if rate_pct < 5:
        return 85.0
    if rate_pct < 10:
        return 65.0
    if rate_pct < 20:
        return 40.0
    return 15.0


def calculate_health_score(
    results: list[ConversationAnalysisResult],
    first_response_time_seconds: float | None = None,
    avg_response_time_seconds: float | None = None,  # fallback if first RT unavailable
) -> float:
    """
    Compute 0-100 health score using the LATAM-optimized 6-component formula.
    Missing components get zero weight so they don't drag the score toward 50.
    """
    components: list[tuple[float, float]] = []  # (score, weight)

    # 1. Response Speed (25%) — first response time, falling back to avg response time
    rt_input = first_response_time_seconds if first_response_time_seconds is not None else avg_response_time_seconds
    rt_score = _first_response_time_score(rt_input)
    if rt_score is not None:
        components.append((rt_score, 0.25))
    else:
        components.append((50.0, 0.0))

    # 2. Response Coverage (15%) — percentage of messages that went unanswered
    total_msgs = sum(r.total_messages for r in results)
    total_unanswered = sum(r.unanswered_count for r in results)
    if total_msgs > 0:
        unanswered_rate_pct = (total_unanswered / total_msgs) * 100
        coverage_score = _unanswered_rate_score(unanswered_rate_pct)
        components.append((coverage_score, 0.15))
    else:
        components.append((50.0, 0.0))

    # 3. Customer Sentiment (20%) — (positive%×100) + (neutral%×50) + (negative%×0)
    sentiment_results = [r for r in results if r.sentiment is not None]
    if sentiment_results:
        n = len(sentiment_results)
        positive = sum(1 for r in sentiment_results if r.sentiment == Sentiment.POSITIVE)
        neutral = sum(1 for r in sentiment_results if r.sentiment == Sentiment.NEUTRAL)
        sentiment_score = (positive / n * 100) + (neutral / n * 50)
        components.append((sentiment_score, 0.20))
    else:
        components.append((50.0, 0.0))

    # 4. Conversation Quality (15%) — avg quality_score × 10 (converts 0-10 to 0-100)
    quality_results = [r for r in results if r.quality_score is not None]
    if quality_results:
        avg_quality = sum(r.quality_score for r in quality_results) / len(quality_results)
        components.append((avg_quality * 10, 0.15))
    else:
        components.append((50.0, 0.0))

    # 5. Conversion Effectiveness (15%) — converted / applicable × 100
    applicable = [
        r for r in results
        if r.conversion_status and r.conversion_status != ConversionStatus.NOT_APPLICABLE
    ]
    if applicable:
        converted = sum(1 for r in applicable if r.conversion_status == ConversionStatus.CONVERTED)
        conversion_score = (converted / len(applicable)) * 100
        components.append((conversion_score, 0.15))
    else:
        components.append((50.0, 0.0))

    # 6. Operational Coverage (10%) — default 50, can't detect from .txt exports
    components.append((50.0, 0.10))

    total_weight = sum(w for _, w in components)
    if total_weight == 0:
        return 50.0

    weighted_sum = sum(score * w for score, w in components)
    return round(weighted_sum / total_weight, 1)
