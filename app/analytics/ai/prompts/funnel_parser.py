"""
Parse funnel AI JSON response into typed fields.
Safe defaults on any parse failure — never raises.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

_INTENT_STAGE_VALID = frozenset({
    "none", "exploring", "quote_requested", "quoted",
    "negotiating", "converted", "lost", "pending",
})
_LOST_REASON_VALID = frozenset({
    "price", "competition", "timing", "no_reply", "changed_mind", "other",
})


def parse_funnel_response(raw_content: str, conversation_id: str) -> dict:
    """
    Parse the funnel AI call JSON response.

    Returns a dict with all 6 funnel AI fields.
    On any error returns safe defaults (no purchase intent, stage=none).
    """
    try:
        cleaned = raw_content.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning(
            "Funnel parse error for %s: %s | raw: %.300s",
            conversation_id, exc, raw_content,
        )
        return empty_funnel_ai()

    has_intent = bool(data.get("has_purchase_intent", False))

    stage_raw = str(data.get("intent_stage") or "none").lower().strip()
    intent_stage = stage_raw if stage_raw in _INTENT_STAGE_VALID else "none"

    # Enforce consistency: none ↔ no intent
    if intent_stage == "none":
        has_intent = False
    if not has_intent:
        intent_stage = "none"

    intent_first_offset = _safe_offset(data, "intent_first_at_offset_seconds")
    quote_requested_offset = _safe_offset(data, "quote_requested_at_offset_seconds")

    lost_reason_raw = str(data.get("lost_reason") or "").lower().strip()
    lost_reason: str | None = lost_reason_raw if lost_reason_raw in _LOST_REASON_VALID else None
    if intent_stage != "lost":
        lost_reason = None  # only meaningful when stage=lost

    detail_raw = str(data.get("lost_reason_detail") or "").strip()
    lost_reason_detail: str | None = (
        detail_raw[:300] if detail_raw and intent_stage == "lost" else None
    )

    return {
        "has_purchase_intent": has_intent,
        "intent_stage": intent_stage,
        "intent_first_at_offset_seconds": intent_first_offset,
        "quote_requested_at_offset_seconds": quote_requested_offset,
        "lost_reason": lost_reason,
        "lost_reason_detail": lost_reason_detail,
    }


def empty_funnel_ai() -> dict:
    return {
        "has_purchase_intent": False,
        "intent_stage": "none",
        "intent_first_at_offset_seconds": None,
        "quote_requested_at_offset_seconds": None,
        "lost_reason": None,
        "lost_reason_detail": None,
    }


def _safe_offset(data: dict, key: str) -> int | None:
    v = data.get(key)
    if v is None:
        return None
    try:
        iv = int(float(v))
        return iv if iv >= 0 else None
    except (TypeError, ValueError):
        return None
