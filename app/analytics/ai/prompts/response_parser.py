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


def _normalize_topic(raw: str) -> str:
    """
    Normalize an open-vocabulary topic so distinct conversations agree.

    The prompt instructs the AI to follow conventions, but cheap text cleanup
    here makes the aggregation robust to small drift:
      • lowercase
      • strip whitespace and punctuation (¿ ? . , ! ¡ : ;)
      • collapse internal whitespace
    Returns "" for empty input — the caller drops empty topics.
    """
    if not raw:
        return ""
    s = raw.strip().lower()
    # Strip leading/trailing punctuation commonly used in Spanish prompts
    s = s.strip(" ¿?¡!.,;:\"'`«»“”")
    # Collapse internal whitespace
    s = " ".join(s.split())
    return s


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
    helpfulness = _clamp(qb_raw.get("helpfulness"), 0, 10, 5.0)
    tone = _clamp(qb_raw.get("tone"), 0, 10, 5.0)
    completeness = _clamp(qb_raw.get("completeness"), 0, 10, 5.0)
    # speed_perception is DEPRECATED — older models may still return it; we accept
    # it for backward compatibility but it doesn't affect quality_score.
    speed_perception = _clamp(qb_raw.get("speed_perception"), 0, 10, 5.0)
    quality_breakdown = QualityBreakdown(
        helpfulness=helpfulness,
        tone=tone,
        completeness=completeness,
        speed_perception=speed_perception,
    )

    primary_topic = _normalize_topic(str(data.get("primary_topic") or ""))
    if primary_topic and _may_be_english(primary_topic):
        logger.warning(
            "Topic '%s' for conversation %s appears to be in English — check AI language instructions",
            primary_topic,
            conversation_id,
        )

    customer_questions = [str(q).strip() for q in (data.get("customer_questions") or []) if str(q).strip()]

    # Quality score: prefer the AI's explicit quality_score when reasonable, but
    # always recompute from the 3 active dimensions and use that if the model
    # forgot to update its overall score (or still includes speed_perception in
    # its average). Three-dimension average is the new source of truth.
    explicit_score = data.get("quality_score")
    avg_three = (helpfulness + tone + completeness) / 3.0
    if explicit_score is None:
        quality_score = round(avg_three, 1)
    else:
        clamped = _clamp(explicit_score, 0, 10, avg_three)
        # If the AI's score deviates from the 3-dim average by more than 0.5,
        # trust the recomputed average — the model likely averaged 4 dims.
        quality_score = round(avg_three, 1) if abs(clamped - avg_three) > 0.5 else round(clamped, 1)

    # client_relationship — validated against allowed values
    _CR_VALID = {"new", "returning", "internal", "uncertain"}
    cr_raw = str(data.get("client_relationship") or "uncertain").lower().strip()
    client_relationship = cr_raw if cr_raw in _CR_VALID else "uncertain"
    cr_signals = [
        str(s).strip() for s in (data.get("client_relationship_signals") or [])
        if str(s).strip()
    ][:3]  # cap at 3 signals

    return ConversationAnalysisResult(
        conversation_id=conversation_id,
        sentiment=sentiment,
        sentiment_score=_clamp(data.get("sentiment_score"), -1, 1, 0.0),
        sentiment_reason=str(data.get("sentiment_reason") or ""),
        primary_topic=primary_topic,
        secondary_topics=[t for t in (_normalize_topic(str(s)) for s in (data.get("secondary_topics") or [])) if t],
        quality_score=quality_score,
        quality_breakdown=quality_breakdown,
        conversion_status=conversion,
        conversion_reason=str(data.get("conversion_reason") or "") or None,
        summary=str(data.get("summary") or ""),
        key_points=[str(p) for p in (data.get("key_points") or [])],
        customer_questions=customer_questions,
        client_relationship=client_relationship,
        client_relationship_signals=cr_signals,
        # client_relationship_source is set by engine.py after merging deterministic + AI
    )
