"""
Business health score calculator (0-100). Rule-based, no AI.

Colombia MiPymes 6-component formula:
- Response Speed         25%  First response time vs Colombia benchmarks
- Response Coverage      15%  % of CONVERSATIONS that ended unanswered (chat-level, not message-level)
- Customer Sentiment     20%  Weighted positive/neutral/negative split
- Conversation Quality   15%  Average quality score × 10
- Conversion Effectiveness 15%  Conversion rate as percentage
- Operational Coverage   10%  % of in-business-hours customer messages answered within 1 h
                              (computed deterministically from message timestamps; falls back to 50
                              when no in-hours messages were observed)

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
    """0-100 score based on first response time. Colombia MiPymes benchmarks."""
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
    """0-100 score based on percentage of conversations that ended unanswered."""
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
    Compute 0-100 health score using the Colombia MiPymes 6-component formula.
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

    # 2. Response Coverage (15%) — % of CONVERSATIONS that ended without a business reply
    # `unanswered_count` is now 0|1 per conversation, so the sum equals the
    # number of unanswered conversations and the denominator is len(results).
    total_convs = len(results)
    unanswered_convs = sum(r.unanswered_count for r in results)
    if total_convs > 0:
        unanswered_rate_pct = (unanswered_convs / total_convs) * 100
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

    # 6. Operational Coverage (10%) — % of in-hours customer messages answered within 1h.
    # Computed per-conversation in `ack_metrics.operational_coverage_score`; here we
    # average across results that produced a value. None ⇒ no in-hours samples in
    # that chat, so it doesn't vote.
    op_scores = [r.operational_coverage_score for r in results if r.operational_coverage_score is not None]
    if op_scores:
        op_score = sum(op_scores) / len(op_scores)
        components.append((op_score, 0.10))
    else:
        # No in-hours customer messages anywhere — give the component zero weight
        # rather than a misleading hardcoded 50.
        components.append((50.0, 0.0))

    total_weight = sum(w for _, w in components)
    if total_weight == 0:
        return 50.0

    weighted_sum = sum(score * w for score, w in components)
    return round(weighted_sum / total_weight, 1)


def get_health_score_breakdown(
    results: list[ConversationAnalysisResult],
    first_response_time_seconds: float | None = None,
    avg_response_time_seconds: float | None = None,
) -> list[dict]:
    """Return the 6 health score component scores for visual breakdown display."""
    TEAL = "#1D9E75"
    AMBER = "#EF9F27"
    CORAL = "#D85A30"

    def _color(pct: float) -> str:
        return TEAL if pct >= 80 else (AMBER if pct >= 50 else CORAL)

    # 1. Response Speed (25%)
    rt_input = first_response_time_seconds if first_response_time_seconds is not None else avg_response_time_seconds
    rt_score = _first_response_time_score(rt_input)
    if rt_score is None:
        rt_score = 50.0

    # 2. Response Coverage (15%) — chat-level
    total_convs = len(results)
    unanswered_convs = sum(r.unanswered_count for r in results)
    cov_score = _unanswered_rate_score((unanswered_convs / total_convs) * 100) if total_convs > 0 else 50.0

    # 3. Sentiment (20%)
    sentiment_results = [r for r in results if r.sentiment is not None]
    if sentiment_results:
        n = len(sentiment_results)
        positive = sum(1 for r in sentiment_results if r.sentiment == Sentiment.POSITIVE)
        neutral = sum(1 for r in sentiment_results if r.sentiment == Sentiment.NEUTRAL)
        sent_score = min(100.0, (positive / n * 100) + (neutral / n * 50))
    else:
        sent_score = 50.0

    # 4. Quality (15%)
    quality_results = [r for r in results if r.quality_score is not None]
    qual_score = (sum(r.quality_score for r in quality_results) / len(quality_results) * 10) if quality_results else 50.0

    # 5. Conversion (15%)
    applicable = [r for r in results if r.conversion_status and r.conversion_status != ConversionStatus.NOT_APPLICABLE]
    if applicable:
        converted = sum(1 for r in applicable if r.conversion_status == ConversionStatus.CONVERTED)
        conv_score = (converted / len(applicable)) * 100
    else:
        conv_score = 50.0

    # 6. Operational Coverage (10%) — average per-conversation score, falls back to 50
    op_scores = [r.operational_coverage_score for r in results if r.operational_coverage_score is not None]
    op_score = sum(op_scores) / len(op_scores) if op_scores else 50.0

    dims = [
        ("Velocidad de respuesta",    "velocidad",         rt_score,   0.25, 25),
        ("Cobertura de respuestas",   "cobertura",         cov_score,  0.15, 15),
        ("Sentimiento del cliente",   "sentimiento",       sent_score, 0.20, 20),
        ("Calidad de atención",       "calidad",           qual_score, 0.15, 15),
        ("Efectividad de conversión", "conversion",        conv_score, 0.15, 15),
        ("Cobertura horaria",         "cobertura_horaria", op_score,   0.10, 10),
    ]

    breakdown = []
    for name, key, score, weight, max_pts in dims:
        pct = round(score, 1)
        breakdown.append({
            "name": name,
            "key": key,
            "raw_score": round(score, 1),
            "weight": weight,
            "max_points": max_pts,
            "obtained_points": round(score * weight, 1),
            "pct_of_max": pct,
            "color": _color(pct),
            "is_strength": False,
            "is_critical": False,
        })

    # Mark best and worst
    scores = [d["pct_of_max"] for d in breakdown]
    max_score = max(scores)
    min_score = min(scores)
    for d in breakdown:
        if d["pct_of_max"] == max_score:
            d["is_strength"] = True
            break
    for d in reversed(breakdown):
        if d["pct_of_max"] == min_score:
            d["is_critical"] = True
            break

    return breakdown


def explain_health_score(
    score: float,
    results: list[ConversationAnalysisResult],
    first_response_time_seconds: float | None = None,
    avg_response_time_seconds: float | None = None,
) -> str:
    """
    Generate a human-readable explanation of what's driving the health score.
    Returns a string like:
    "Tu puntaje de salud es 52/100, principalmente afectado por:
    • Velocidad de respuesta: 6.6h vs 5 min ideal
    Tu fortaleza: Calidad de atención (8.0/10) está por encima del objetivo."
    """
    issues: list[str] = []
    strengths: list[str] = []

    # Response speed
    rt = first_response_time_seconds if first_response_time_seconds is not None else avg_response_time_seconds
    if rt is not None:
        rt_score = _first_response_time_score(rt)
        if rt_score is not None and rt_score < 50:
            if rt >= 3600:
                rt_str = f"{rt / 3600:.1f}h"
            else:
                rt_str = f"{int(rt / 60)} min"
            issues.append(f"Velocidad de respuesta: muy por debajo del benchmark ({rt_str} vs. 5 min ideal)")
        elif rt_score is not None and rt_score >= 85:
            strengths.append("Velocidad de respuesta excelente (< 5 min)")

    # Sentiment
    sentiment_results = [r for r in results if r.sentiment is not None]
    if sentiment_results:
        n = len(sentiment_results)
        positive = sum(1 for r in sentiment_results if r.sentiment == Sentiment.POSITIVE)
        pos_pct = positive / n * 100
        if pos_pct >= 70:
            strengths.append(f"Sentimiento positivo alto ({pos_pct:.0f}%)")
        elif pos_pct < 40:
            issues.append(f"Alto porcentaje de conversaciones con sentimiento bajo ({pos_pct:.0f}% positivo)")

    # Quality
    quality_results = [r for r in results if r.quality_score is not None]
    if quality_results:
        avg_quality = sum(r.quality_score for r in quality_results) / len(quality_results)
        if avg_quality >= 7.5:
            strengths.append(f"Calidad de atención ({avg_quality:.1f}/10) está por encima del objetivo")
        elif avg_quality < 5:
            issues.append(f"Calidad de atención baja ({avg_quality:.1f}/10)")

    # Conversion
    applicable = [
        r for r in results
        if r.conversion_status and r.conversion_status != ConversionStatus.NOT_APPLICABLE
    ]
    if applicable:
        converted = sum(1 for r in applicable if r.conversion_status == ConversionStatus.CONVERTED)
        conv_rate = converted / len(applicable) * 100
        if conv_rate < 15:
            issues.append(f"Tasa de conversión: {conv_rate:.0f}% de las conversaciones resultaron en venta")

    parts = [f"Tu puntaje de salud es {score:.0f}/100"]
    if issues:
        issue_lines = "\n• ".join(issues)
        parts.append(f", principalmente afectado por:\n• {issue_lines}")
    if strengths:
        strength_lines = "; ".join(strengths)
        parts.append(f"\nTu fortaleza: {strength_lines}.")

    return "".join(parts)
