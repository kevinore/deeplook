"""
Orchestrates the action plan generation:
  1. Compute metrics from results
  2. Detect signals (deterministic)
  3. Call AI to write the text
  4. Fall back to deterministic cards on AI failure
"""
from __future__ import annotations

import logging
import statistics
from collections import Counter
from datetime import datetime

from app.analytics.insights.action_plan_engine import ActionSignal, detect_signals
from app.analytics.ai.prompts.action_plan_prompt import (
    ACTION_PLAN_SYSTEM_PROMPT,
    build_action_plan_prompt,
)
from app.analytics.ai.prompts.action_plan_parser import parse_action_plan_response
from app.analytics.ai.provider import AIProvider
from app.models.enums import ConversionStatus, Sentiment
from app.models.schemas import ConversationAnalysisResult

logger = logging.getLogger(__name__)

_URGENCY_LABEL = {
    "urgente":     "🔴 Urgente",
    "esta_semana": "🟡 Esta semana",
    "este_mes":    "🟢 Este mes",
}
_URGENCY_COLOR = {
    "urgente":     "red",
    "esta_semana": "amber",
    "este_mes":    "green",
}


def _fmt_s(s: float) -> str:
    if s < 60:
        return f"{int(s)}s"
    if s < 3600:
        return f"{int(s/60)} min"
    return f"{s/3600:.1f}h"


def compute_action_plan_metrics(
    results: list[ConversationAnalysisResult],
    health_score: float = 0.0,
    by_hour_data: dict[int, float] | None = None,
) -> dict:
    """
    Compute the metrics dict expected by detect_signals().
    Called from router.py and analysis_worker.py before building the PDF.
    """
    total = len(results) or 1
    now = datetime.utcnow()

    # Response times
    frt_vals = [r.first_response_time_seconds for r in results if r.first_response_time_seconds is not None]
    median_first_rt = statistics.median(frt_vals) if frt_vals else None

    # Unanswered (deduplicated by phone)
    _latest: dict[str, ConversationAnalysisResult] = {}
    for r in results:
        if r.wa_is_muted or r.wa_is_archived:
            continue
        key = r.contact_phone or r.conversation_id
        _latest[key] = r
    total_unanswered = sum(1 for r in _latest.values() if r.unanswered_count)

    # Conversion
    applicable = [r for r in results if r.conversion_status and r.conversion_status != ConversionStatus.NOT_APPLICABLE]
    converted = sum(1 for r in applicable if r.conversion_status == ConversionStatus.CONVERTED)
    conversion_rate = round(converted / len(applicable) * 100) if applicable else 0

    # Sentiment
    with_sentiment = [r for r in results if r.sentiment is not None]
    neg_pct = round(sum(1 for r in with_sentiment if r.sentiment == Sentiment.NEGATIVE) / len(with_sentiment) * 100) if with_sentiment else 0
    pos_pct = round(sum(1 for r in with_sentiment if r.sentiment == Sentiment.POSITIVE) / len(with_sentiment) * 100) if with_sentiment else 0

    # Quality
    quality_results = [r for r in results if r.quality_score is not None]
    avg_quality = statistics.mean(r.quality_score for r in quality_results) if quality_results else None

    # Operational coverage
    op_cov = [r.operational_coverage_score for r in results if r.operational_coverage_score is not None]
    avg_op_cov = round(statistics.mean(op_cov), 1) if op_cov else None

    # Funnel
    intent_convs = [r for r in results if r.has_purchase_intent]
    intent_count = len(intent_convs)
    quoted_convs = [r for r in intent_convs if r.quote_sent_at is not None]
    quoted_count = len(quoted_convs)
    funnel_lost = [r for r in intent_convs if r.intent_stage == "lost"]
    funnel_pending = [r for r in intent_convs if r.intent_stage in ("pending", "quoted", "negotiating")]

    quote_coverage_rate = round(quoted_count / intent_count * 100) if intent_count else None

    # QRT won vs lost
    qrt_won = [r.quote_response_time_seconds for r in intent_convs if r.intent_stage == "converted" and r.quote_response_time_seconds]
    qrt_lost = [r.quote_response_time_seconds for r in intent_convs if r.intent_stage == "lost" and r.quote_response_time_seconds]
    median_qrt_converted = statistics.median(qrt_won) if qrt_won else None
    median_qrt_lost_val = statistics.median(qrt_lost) if qrt_lost else None
    qrt_speed_ratio = (
        round(median_qrt_lost_val / median_qrt_converted, 1)
        if median_qrt_converted and median_qrt_lost_val and median_qrt_converted > 0
        else None
    )

    # Follow-up
    with_followup = [r for r in quoted_convs if (r.post_quote_followup_count or 0) > 0]
    fup_delay_vals = [r.followup_delay_hours for r in with_followup if r.followup_delay_hours is not None]
    median_followup_delay = statistics.median(fup_delay_vals) if fup_delay_vals else None

    # FRT new vs returning
    new_frt = [r.first_response_time_seconds for r in results if r.client_relationship == "new" and r.first_response_time_seconds]
    ret_frt = [r.first_response_time_seconds for r in results if r.client_relationship == "returning" and r.first_response_time_seconds]
    med_new = statistics.median(new_frt) if new_frt else None
    med_ret = statistics.median(ret_frt) if ret_frt else None
    frt_multiplier = round(med_new / med_ret, 1) if med_new and med_ret and med_ret > 0 else None

    return {
        "total_conversations": total,
        "health_score": health_score,
        "median_first_rt": median_first_rt,
        "total_unanswered": total_unanswered,
        "conversion_rate": conversion_rate,
        "applicable_count": len(applicable),
        "negative_pct": neg_pct,
        "positive_pct": pos_pct,
        "avg_quality": avg_quality,
        "avg_operational_coverage": avg_op_cov,
        "by_hour_data": by_hour_data or {},
        # Funnel
        "intent_count": intent_count,
        "quoted_count": quoted_count,
        "funnel_lost_count": len(funnel_lost),
        "funnel_lost_convs": funnel_lost,
        "funnel_pending_count": len(funnel_pending),
        "quote_coverage_rate": quote_coverage_rate,
        "median_qrt_converted": median_qrt_converted,
        "median_qrt_lost": median_qrt_lost_val,
        "median_qrt_converted_str": _fmt_s(median_qrt_converted) if median_qrt_converted else "N/D",
        "median_qrt_lost_str": _fmt_s(median_qrt_lost_val) if median_qrt_lost_val else "N/D",
        "qrt_speed_ratio": qrt_speed_ratio,
        "median_followup_delay_hours": median_followup_delay,
        # Follow-up coverage
        "with_followup_count": len(with_followup),
        # New vs returning
        "frt_multiplier": frt_multiplier,
        "new_client_count": len(new_frt),
        "returning_client_count": len(ret_frt),
        "median_frt_new_clients_str": _fmt_s(med_new) if med_new else "N/D",
        "median_frt_returning_clients_str": _fmt_s(med_ret) if med_ret else "N/D",
    }


def _signals_to_fallback_cards(signals: list[ActionSignal]) -> list[dict]:
    """Build action cards from signal fallback text when AI is unavailable."""
    cards = []
    urgency_by_severity = [
        (7.0, "urgente"),
        (4.0, "esta_semana"),
        (0.0, "este_mes"),
    ]
    for i, sig in enumerate(signals[:3], 1):
        urgency = "este_mes"
        for threshold, label in urgency_by_severity:
            if sig.severity >= threshold:
                urgency = label
                break
        cards.append({
            "number": i,
            "title": sig.fallback_title,
            "urgency": urgency,
            "urgency_label": _URGENCY_LABEL[urgency],
            "urgency_color": _URGENCY_COLOR[urgency],
            "que_esta_pasando": f"Problema detectado en el área de {sig.category}.",
            "por_que_importa": "Resolver esto puede mejorar tu tasa de conversión y satisfacción del cliente.",
            "steps": sig.fallback_steps,
            "impact": "Mejora progresiva en el puntaje de salud del canal.",
        })
    return cards


async def generate_action_plan(
    results: list[ConversationAnalysisResult],
    ai_provider: AIProvider,
    business_name: str,
    business_type: str | None,
    health_score: float,
    by_hour_data: dict[int, float] | None = None,
) -> tuple[list[dict], float, int, int]:
    """
    Full action plan pipeline:
      1. Compute metrics
      2. Detect signals
      3. Call AI for text
      4. Fall back to deterministic cards on failure

    Returns (cards, cost_usd, tokens_input, tokens_output).
    On fallback or no signals: cards may be empty and cost/tokens are 0.
    """
    metrics = compute_action_plan_metrics(
        results,
        health_score=health_score,
        by_hour_data=by_hour_data,
    )

    signals = detect_signals(results, metrics)
    if not signals:
        logger.info("No action signals detected for business=%s", business_name)
        return [], 0.0, 0, 0

    # Build AI prompt
    user_prompt = build_action_plan_prompt(
        signals=signals,
        business_name=business_name,
        business_type=business_type,
        health_score=health_score,
        total_conversations=metrics["total_conversations"],
    )

    # AI call
    try:
        response = await ai_provider.analyze(
            system_prompt=ACTION_PLAN_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.4,
            max_tokens=2000,
        )
        cards = parse_action_plan_response(response.content)
        if cards:
            logger.info(
                "AI action plan generated OK for business=%s (%d cards)",
                business_name, len(cards),
            )
            return cards, response.cost_usd, response.tokens_input, response.tokens_output
        logger.warning("AI action plan parse returned empty — using fallback (business=%s)", business_name)
        return _signals_to_fallback_cards(signals), response.cost_usd, response.tokens_input, response.tokens_output
    except Exception as exc:
        logger.error("AI action plan call failed for business=%s: %s", business_name, exc)

    # Fallback: build cards from signal metadata (no AI cost)
    return _signals_to_fallback_cards(signals), 0.0, 0, 0
