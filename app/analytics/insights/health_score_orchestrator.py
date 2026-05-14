"""
Orchestrates the full 3-layer health score pipeline:
  Layer 1 — Improved deterministic formulas (in health_score.py)
  Layer 2 — Contextual AI evaluation (one call per report)
  Layer 3 — Final aggregation with bounded AI adjustments

Called from router.py and analysis_worker.py before PDF generation.
Cost is returned so the caller can update job totals.
"""
from __future__ import annotations

import logging

from app.analytics.ai.provider import AIProvider
from app.analytics.ai.prompts.health_eval_prompt import (
    HEALTH_EVAL_SYSTEM_PROMPT,
    build_health_eval_prompt,
)
from app.analytics.ai.prompts.health_eval_parser import parse_health_eval_response, _default
from app.analytics.insights.health_score import (
    calculate_health_score,
    _sentiment_score_from_floats,
    _sentiment_score_categorical,
    _quality_score_component,
)
from app.models.schemas import ConversationAnalysisResult

logger = logging.getLogger(__name__)


async def evaluate_health_context(
    results: list[ConversationAnalysisResult],
    ai_provider: AIProvider,
    business_name: str,
    business_type: str | None,
    first_response_time_seconds: float | None = None,
    avg_response_time_seconds: float | None = None,
) -> tuple[dict, float, int, int]:
    """
    Run the Layer 2 AI evaluation and return:
      (adjustments_dict, cost_usd, tokens_input, tokens_output)

    On failure returns default (zero adjustments) with zero costs so the
    deterministic base score is used unchanged.
    """
    # Compute base scores to pass context to AI
    base_sent = _sentiment_score_from_floats(results)
    if base_sent is None:
        base_sent = _sentiment_score_categorical(results) or 50.0
    base_qual = _quality_score_component(results) or 50.0

    try:
        user_prompt = build_health_eval_prompt(
            results=results,
            business_name=business_name,
            business_type=business_type,
            base_sentiment_score=base_sent,
            base_quality_score=base_qual,
            total_conversations=len(results),
        )
        response = await ai_provider.analyze(
            system_prompt=HEALTH_EVAL_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.1,
            max_tokens=400,
        )
        adjustments = parse_health_eval_response(response.content)
        logger.info(
            "Health eval AI: sent_adj=%+d qual_adj=%+d confidence=%s (business=%s)",
            adjustments["sentimiento_ajuste"],
            adjustments["calidad_ajuste"],
            adjustments["confianza"],
            business_name,
        )
        return adjustments, response.cost_usd, response.tokens_input, response.tokens_output

    except Exception as exc:
        logger.warning("Health eval AI call failed for business=%s: %s", business_name, exc)
        return _default(), 0.0, 0, 0
