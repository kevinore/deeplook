"""
Parse AI JSON response into typed Pydantic models.
"""
import json
import logging

from app.models.enums import ConversionStatus, Sentiment
from app.models.schemas import ConversationAnalysisResult, QualityBreakdown

logger = logging.getLogger(__name__)

_SENTIMENT_MAP = {
    "positive": Sentiment.POSITIVE,
    "neutral": Sentiment.NEUTRAL,
    "negative": Sentiment.NEGATIVE,
    "very positive": Sentiment.POSITIVE,
    "very negative": Sentiment.NEGATIVE,
    "mixed": Sentiment.NEUTRAL,
}

_CONVERSION_MAP = {
    "converted": ConversionStatus.CONVERTED,
    "lost": ConversionStatus.LOST,
    "pending": ConversionStatus.PENDING,
    "not_applicable": ConversionStatus.NOT_APPLICABLE,
    "not applicable": ConversionStatus.NOT_APPLICABLE,
    "n/a": ConversionStatus.NOT_APPLICABLE,
}

# Safety net: common English words that indicate the AI responded in English
_ENGLISH_INDICATORS = {
    "scheduling", "inquiry", "about", "appointment", "treatment",
    "service", "information", "question", "regarding", "availability",
    "pricing", "booking", "request", "follow", "purchase",
}


def _may_be_english(text: str) -> bool:
    words = set(text.lower().split())
    return bool(words & _ENGLISH_INDICATORS)


def _clamp(value: float | int | None, lo: float, hi: float, default: float) -> float:
    if value is None:
        return default
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return default


def parse_ai_response(raw_content: str, conversation_id: str) -> ConversationAnalysisResult:
    """
    Parse AI JSON string into ConversationAnalysisResult.

    Handles:
    - Missing fields → use defaults
    - Invalid field values → normalize to closest valid
    - Extra fields → ignored
    """
    try:
        # Strip markdown code fences if present
        cleaned = raw_content.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("AI response parse error for %s: %s | raw: %.200s", conversation_id, exc, raw_content)
        return ConversationAnalysisResult(conversation_id=conversation_id)

    sentiment_raw = str(data.get("sentiment", "neutral")).lower()
    sentiment = _SENTIMENT_MAP.get(sentiment_raw, Sentiment.NEUTRAL)

    conversion_raw = str(data.get("conversion_status", "not_applicable")).lower().replace("-", "_")
    conversion = _CONVERSION_MAP.get(conversion_raw, ConversionStatus.NOT_APPLICABLE)

    qb_raw = data.get("quality_breakdown") or {}
    quality_breakdown = QualityBreakdown(
        helpfulness=_clamp(qb_raw.get("helpfulness"), 0, 10, 5.0),
        tone=_clamp(qb_raw.get("tone"), 0, 10, 5.0),
        completeness=_clamp(qb_raw.get("completeness"), 0, 10, 5.0),
        speed_perception=_clamp(qb_raw.get("speed_perception"), 0, 10, 5.0),
    )

    primary_topic = str(data.get("primary_topic") or "")
    if primary_topic and _may_be_english(primary_topic):
        logger.warning(
            "Topic '%s' for conversation %s appears to be in English — check AI language instructions",
            primary_topic,
            conversation_id,
        )

    customer_questions = [str(q) for q in (data.get("customer_questions") or [])]

    return ConversationAnalysisResult(
        conversation_id=conversation_id,
        sentiment=sentiment,
        sentiment_score=_clamp(data.get("sentiment_score"), -1, 1, 0.0),
        sentiment_reason=str(data.get("sentiment_reason") or ""),
        primary_topic=primary_topic,
        secondary_topics=[str(t) for t in (data.get("secondary_topics") or [])],
        quality_score=_clamp(data.get("quality_score"), 0, 10, 5.0),
        quality_breakdown=quality_breakdown,
        conversion_status=conversion,
        conversion_reason=str(data.get("conversion_reason") or "") or None,
        summary=str(data.get("summary") or ""),
        key_points=[str(p) for p in (data.get("key_points") or [])],
        customer_questions=customer_questions,
    )
