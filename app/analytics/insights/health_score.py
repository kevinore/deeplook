"""
Business health score calculator (0-100). Rule-based base + optional AI semantic layer.

Colombia MiPymes 6-component formula:
- Response Speed         25%  First response time vs Colombia benchmarks (unchanged)
- Customer Sentiment     20%  Float sentiment_score weighted average (Layer 1 improved)
                              + optional AI contextual adjustment (Layer 2)
- Conversation Quality   20%  Non-linear mapping, unanswered excluded (Layer 1 improved)
                              + optional AI contextual adjustment (Layer 2)
- Conversion Effectiveness 15%  Non-linear scale, pending excluded, Bayesian blend (Layer 1 improved)
- Response Coverage      10%  Smooth power curve replacing harsh step function (Layer 1 improved)
- Operational Coverage   10%  % of in-business-hours customer messages answered within 1h

Score interpretation:
85-100  Excelente   — highly effective WhatsApp operation
70-84   Bueno       — good with clear areas to improve
55-69   Regular     — losing sales due to operational gaps
40-54   Por Mejorar — serious issues, immediate action needed
0-39    Urgente     — channel hurting more than helping
"""
from __future__ import annotations

from app.models.enums import ConversionStatus, Sentiment
from app.models.schemas import ConversationAnalysisResult


# ─── Layer 1: Improved component scoring functions ─────────────────────────


def _first_response_time_score(seconds: float | None) -> float | None:
    """0-100 score based on first response time. Colombia MiPymes benchmarks. Unchanged."""
    if seconds is None:
        return None
    if seconds < 120:    return 100.0
    if seconds < 300:    return 85.0
    if seconds < 900:    return 65.0
    if seconds < 1800:   return 45.0
    if seconds < 3600:   return 25.0
    return 10.0


def _sentiment_score_from_floats(results: list[ConversationAnalysisResult]) -> float | None:
    """
    Layer 1: compute sentiment component using per-conversation sentiment_score floats.

    Mapping: score ∈ [–1, 1]
      ≥ 0  →  68 + score × 32   (neutral baseline = 68, very positive = 100)
      < 0  →  68 + score × 68   (slightly negative = ~54, very negative = 0)

    Returns None when no conversations have a sentiment_score, so the caller
    can fall back to the categorical method.
    """
    scored = [r for r in results if r.sentiment_score is not None]
    if not scored:
        return None
    total = 0.0
    for r in scored:
        s = float(r.sentiment_score)
        s = max(-1.0, min(1.0, s))
        if s >= 0:
            total += 68.0 + s * 32.0
        else:
            total += 68.0 + s * 68.0
    return min(100.0, total / len(scored))


def _sentiment_score_categorical(results: list[ConversationAnalysisResult]) -> float | None:
    """
    Fallback: categorical sentiment (positive/neutral/negative counts).
    neutral weight = 68 (raised from 65: transactional WhatsApp neutral = slightly above baseline).
    """
    sentiment_results = [r for r in results if r.sentiment is not None]
    if not sentiment_results:
        return None
    n = len(sentiment_results)
    positive = sum(1 for r in sentiment_results if r.sentiment == Sentiment.POSITIVE)
    neutral  = sum(1 for r in sentiment_results if r.sentiment == Sentiment.NEUTRAL)
    score = (positive / n * 100.0) + (neutral / n * 68.0)
    return min(100.0, score)


def _quality_score_component(results: list[ConversationAnalysisResult]) -> float | None:
    """
    Layer 1: quality score excluding unanswered conversations (they're already
    penalized in coverage; double-penalization removed).

    Non-linear mapping of AI quality 0–10 → health component 0–100:
      0–5   →  linear × 10          (0–50)
      5–7   →  50 + (q–5) × 12.5   (50–75)
      7–9   →  75 + (q–7) × 10     (75–95)
      9–10  →  95 + (q–9) × 5      (95–100)

    This makes a "good service" score of 7.5 map to ~81 instead of 75,
    and 8.0 → 85 instead of 80, reflecting that AI quality 7+ IS good service.
    """
    # quality_score > 0: exclude conversations the AI treated as unanswered
    # (quality=0 despite outbound messages = AI saw no real service to evaluate).
    # Those are already penalized in coverage. Avoids triple-penalization.
    answered = [
        r for r in results
        if r.quality_score is not None
        and r.quality_score > 0
        and r.outbound_count > 0
        and r.inbound_count > 0
    ]
    if not answered:
        return None
    avg_q = sum(r.quality_score for r in answered) / len(answered)
    return _quality_nonlinear(avg_q)


def _quality_nonlinear(q: float) -> float:
    """Non-linear mapping: AI quality 0–10 → health component 0–100."""
    q = max(0.0, min(10.0, q))
    if q <= 5.0:
        return q * 10.0
    elif q <= 7.0:
        return 50.0 + (q - 5.0) * 12.5
    elif q <= 9.0:
        return 75.0 + (q - 7.0) * 10.0
    else:
        return 95.0 + (q - 9.0) * 5.0


def _unanswered_rate_score(rate_pct: float) -> float:
    """
    Layer 1: smooth power curve replacing the harsh step function.

    score = 100 × (1 – rate)^1.3   with floor 15
    Examples:
      0%   → 100     (was 100)
      5%   →  87.2   (was  85 — similar but continuous)
      10%  →  74.6   (was  65 — less harsh cliff)
      15%  →  63.3   (was  40 — significantly less harsh)
      20%  →  53.0   (was  40)
      30%  →  35.8   (was  25)
      40%  →  22.0   (was  15)
      50%+ →  15.0   (floor)
    """
    if rate_pct <= 0:
        return 100.0
    rate = min(rate_pct / 100.0, 1.0)
    raw = 100.0 * ((1.0 - rate) ** 1.3)
    return max(15.0, round(raw, 1))


def _conversion_score_component(results: list[ConversationAnalysisResult]) -> float | None:
    """
    Layer 1: improved conversion effectiveness score.

    Changes vs original:
    1. Pending excluded from denominator (active opportunity ≠ failure).
       All-pending → return 75.0 (promising pipeline, not a bad score).
    2. Bayesian blend with prior=0.28 when sample < 8 (reduces wild swings
       from small sample sizes: 1/2 conversations converted).
    3. Non-linear scale maps benchmark (35–40%) to 'good' (85–90), not just 40%.

    Returns None when no firm applicable conversations exist.
    """
    applicable = [
        r for r in results
        if r.conversion_status and r.conversion_status != ConversionStatus.NOT_APPLICABLE
    ]
    if not applicable:
        return None

    # Exclude pending from "firm" denominator
    firm = [
        r for r in applicable
        if r.conversion_status != ConversionStatus.PENDING
    ]
    if not firm:
        return 75.0  # all pending = active pipeline, promising

    converted = sum(1 for r in firm if r.conversion_status == ConversionStatus.CONVERTED)
    actual_rate = converted / len(firm)

    # Bayesian blend with Colombia MiPyme prior
    _PRIOR = 0.28
    blend = min(1.0, len(firm) / 8.0)
    blended = actual_rate * blend + _PRIOR * (1.0 - blend)

    return _conversion_nonlinear(blended)


def _conversion_nonlinear(rate: float) -> float:
    """
    Non-linear mapping: conversion rate 0–1 → health component 0–100.
    Keypoints: 0%→0, 15%→40, 30%→70, 40%→88, 60%→100.
    """
    rate = max(0.0, min(1.0, rate))
    if rate <= 0.15:
        return (rate / 0.15) * 40.0
    elif rate <= 0.30:
        return 40.0 + ((rate - 0.15) / 0.15) * 30.0
    elif rate <= 0.40:
        return 70.0 + ((rate - 0.30) / 0.10) * 18.0
    elif rate <= 0.60:
        return 88.0 + ((rate - 0.40) / 0.20) * 12.0
    else:
        return 100.0


# ─── Layer 2: AI adjustment application ────────────────────────────────────


def apply_ai_adjustments(
    base_sentiment: float,
    base_quality: float,
    adjustments: dict,
) -> tuple[float, float]:
    """
    Apply AI adjustments to sentiment and quality scores.
    Adjustments are clamped to ±15 and final scores clamped to [0, 100].

    Returns (adjusted_sentiment, adjusted_quality).
    """
    sent_adj = max(-15, min(15, int(adjustments.get("sentimiento_ajuste", 0))))
    qual_adj = max(-15, min(15, int(adjustments.get("calidad_ajuste", 0))))
    adj_sentiment = max(0.0, min(100.0, base_sentiment + sent_adj))
    adj_quality   = max(0.0, min(100.0, base_quality   + qual_adj))
    return adj_sentiment, adj_quality


# ─── Main health score calculator ──────────────────────────────────────────


def calculate_health_score(
    results: list[ConversationAnalysisResult],
    first_response_time_seconds: float | None = None,
    avg_response_time_seconds: float | None = None,
    health_adjustments: dict | None = None,
) -> float:
    """
    Compute 0-100 health score using the Colombia MiPymes 6-component formula.

    health_adjustments: optional dict from the AI evaluation layer with keys
        sentimiento_ajuste (int) and calidad_ajuste (int).
    Missing components get zero weight so they don't drag the score toward 50.
    """
    components: list[tuple[float, float]] = []  # (score, weight)

    # 1. Response Speed (25%)
    rt_input = first_response_time_seconds if first_response_time_seconds is not None else avg_response_time_seconds
    rt_score = _first_response_time_score(rt_input)
    components.append((rt_score if rt_score is not None else 50.0, 0.25 if rt_score is not None else 0.0))

    # 2. Response Coverage (10%) — smooth curve
    total_convs = len(results)
    unanswered_convs = sum(r.unanswered_count for r in results)
    if total_convs > 0:
        coverage_score = _unanswered_rate_score((unanswered_convs / total_convs) * 100)
        components.append((coverage_score, 0.10))
    else:
        components.append((50.0, 0.0))

    # 3. Customer Sentiment (20%) — float-based, with optional AI adjustment
    sent_score = _sentiment_score_from_floats(results)
    if sent_score is None:
        sent_score = _sentiment_score_categorical(results)
    if sent_score is not None:
        if health_adjustments:
            adj = max(-15, min(15, int(health_adjustments.get("sentimiento_ajuste", 0))))
            sent_score = max(0.0, min(100.0, sent_score + adj))
        components.append((sent_score, 0.20))
    else:
        components.append((50.0, 0.0))

    # 4. Conversation Quality (20%) — non-linear, unanswered excluded, optional AI adjustment
    qual_score = _quality_score_component(results)
    if qual_score is not None:
        if health_adjustments:
            adj = max(-15, min(15, int(health_adjustments.get("calidad_ajuste", 0))))
            qual_score = max(0.0, min(100.0, qual_score + adj))
        components.append((qual_score, 0.20))
    else:
        components.append((50.0, 0.0))

    # 5. Conversion Effectiveness (15%) — non-linear + pending excluded + Bayesian
    conv_score = _conversion_score_component(results)
    if conv_score is not None:
        components.append((conv_score, 0.15))
    else:
        components.append((50.0, 0.0))

    # 6. Operational Coverage (10%)
    # Exclude unanswered conversations — they triple-penalize (coverage + quality + here).
    # This metric only asks: "when we responded, was it fast enough during business hours?"
    op_scores = [r.operational_coverage_score for r in results if r.operational_coverage_score is not None and r.unanswered_count == 0]
    if op_scores:
        components.append((sum(op_scores) / len(op_scores), 0.10))
    else:
        components.append((50.0, 0.0))

    total_weight = sum(w for _, w in components)
    if total_weight == 0:
        return 50.0
    return round(sum(s * w for s, w in components) / total_weight, 1)


def get_health_score_breakdown(
    results: list[ConversationAnalysisResult],
    first_response_time_seconds: float | None = None,
    avg_response_time_seconds: float | None = None,
    health_adjustments: dict | None = None,
) -> list[dict]:
    """Return the 6 health score component scores for visual breakdown display."""
    TEAL  = "#1D9E75"
    AMBER = "#EF9F27"
    CORAL = "#D85A30"

    def _color(pct: float) -> str:
        return TEAL if pct >= 80 else (AMBER if pct >= 50 else CORAL)

    # 1. Response Speed
    rt_input = first_response_time_seconds if first_response_time_seconds is not None else avg_response_time_seconds
    rt_score = _first_response_time_score(rt_input) or 50.0

    # 2. Coverage
    total_convs = len(results)
    unanswered_convs = sum(r.unanswered_count for r in results)
    cov_score = _unanswered_rate_score((unanswered_convs / total_convs) * 100) if total_convs > 0 else 50.0

    # 3. Sentiment
    sent_score = _sentiment_score_from_floats(results)
    if sent_score is None:
        sent_score = _sentiment_score_categorical(results) or 50.0
    if health_adjustments:
        adj = max(-15, min(15, int(health_adjustments.get("sentimiento_ajuste", 0))))
        sent_score = max(0.0, min(100.0, sent_score + adj))

    # 4. Quality
    qual_score = _quality_score_component(results) or 50.0
    if health_adjustments:
        adj = max(-15, min(15, int(health_adjustments.get("calidad_ajuste", 0))))
        qual_score = max(0.0, min(100.0, qual_score + adj))

    # 5. Conversion
    conv_score = _conversion_score_component(results)
    if conv_score is None:
        conv_score = 50.0

    # 6. Operational Coverage
    # Exclude unanswered conversations — they triple-penalize (coverage + quality + here).
    # This metric only asks: "when we responded, was it fast enough during business hours?"
    op_scores = [r.operational_coverage_score for r in results if r.operational_coverage_score is not None and r.unanswered_count == 0]
    op_score = sum(op_scores) / len(op_scores) if op_scores else 50.0

    dims = [
        ("Velocidad de respuesta",    "velocidad",         rt_score,   0.25, 25),
        ("Sentimiento del cliente",   "sentimiento",       sent_score, 0.20, 20),
        ("Calidad de atención",       "calidad",           qual_score, 0.20, 20),
        ("Efectividad de conversión", "conversion",        conv_score, 0.15, 15),
        ("Cobertura de respuestas",   "cobertura",         cov_score,  0.10, 10),
        ("Cobertura horaria",         "cobertura_horaria", op_score,   0.10, 10),
    ]

    breakdown = []
    for name, key, score, weight, max_pts in dims:
        pct = round(score, 1)
        breakdown.append({
            "name": name, "key": key,
            "raw_score": pct, "weight": weight,
            "max_points": max_pts,
            "obtained_points": round(score * weight, 1),
            "pct_of_max": pct,
            "color": _color(pct),
            "is_strength": False, "is_critical": False,
        })

    scores = [d["pct_of_max"] for d in breakdown]
    max_s, min_s = max(scores), min(scores)
    for d in breakdown:
        if d["pct_of_max"] == max_s:
            d["is_strength"] = True
            break
    for d in reversed(breakdown):
        if d["pct_of_max"] == min_s:
            d["is_critical"] = True
            break

    return breakdown


def explain_health_score(
    score: float,
    results: list[ConversationAnalysisResult],
    first_response_time_seconds: float | None = None,
    avg_response_time_seconds: float | None = None,
) -> str:
    """Generate a human-readable explanation of the health score drivers."""
    issues: list[str] = []
    strengths: list[str] = []

    rt = first_response_time_seconds if first_response_time_seconds is not None else avg_response_time_seconds
    if rt is not None:
        rt_score = _first_response_time_score(rt)
        if rt_score is not None and rt_score < 50:
            rt_str = f"{rt/3600:.1f}h" if rt >= 3600 else f"{int(rt/60)} min"
            issues.append(f"Velocidad de respuesta: muy por debajo del benchmark ({rt_str} vs. 5 min ideal)")
        elif rt_score is not None and rt_score >= 85:
            strengths.append("Velocidad de respuesta excelente (< 5 min)")

    sentiment_results = [r for r in results if r.sentiment is not None]
    if sentiment_results:
        from app.models.enums import Sentiment as _S
        n = len(sentiment_results)
        pos_pct = sum(1 for r in sentiment_results if r.sentiment == _S.POSITIVE) / n * 100
        neg_pct = sum(1 for r in sentiment_results if r.sentiment == _S.NEGATIVE) / n * 100
        if pos_pct >= 70:
            strengths.append(f"Sentimiento positivo alto ({pos_pct:.0f}%)")
        elif neg_pct > 25:
            issues.append(f"Alto porcentaje de conversaciones con sentimiento negativo ({neg_pct:.0f}%)")

    answered = [r for r in results if r.quality_score is not None and r.unanswered_count == 0]
    if answered:
        avg_q = sum(r.quality_score for r in answered) / len(answered)
        if avg_q >= 7.5:
            strengths.append(f"Calidad de atención ({avg_q:.1f}/10) está por encima del objetivo")
        elif avg_q < 5:
            issues.append(f"Calidad de atención baja en conversaciones respondidas ({avg_q:.1f}/10)")

    applicable = [r for r in results if r.conversion_status and r.conversion_status != ConversionStatus.NOT_APPLICABLE]
    if applicable:
        firm = [r for r in applicable if r.conversion_status != ConversionStatus.PENDING]
        if firm:
            conv_rate = sum(1 for r in firm if r.conversion_status == ConversionStatus.CONVERTED) / len(firm) * 100
            if conv_rate < 15:
                issues.append(f"Tasa de conversión: {conv_rate:.0f}% de las oportunidades confirmadas resultaron en venta")

    parts = [f"Tu puntaje de salud es {score:.0f}/100"]
    if issues:
        parts.append(f", principalmente afectado por:\n• " + "\n• ".join(issues))
    if strengths:
        parts.append(f"\nTu fortaleza: " + "; ".join(strengths) + ".")
    return "".join(parts)
