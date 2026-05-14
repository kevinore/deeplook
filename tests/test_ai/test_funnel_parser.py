"""
Comprehensive tests for parse_funnel_response() and empty_funnel_ai().

Covers:
  • Happy path — all valid stages and lost_reason categories
  • JSON format edge cases: markdown fences, extra fields, whitespace
  • Consistency enforcement: stage=none ↔ intent=false
  • Safety: malformed JSON, empty string, missing fields → safe defaults
  • Numeric safety: negative offsets, floats, None, non-numeric values
  • Business rules: lost_reason only when stage=lost, detail truncation
"""
import json

import pytest

from app.analytics.ai.prompts.funnel_parser import (
    _safe_offset,
    empty_funnel_ai,
    parse_funnel_response,
)

CONV_ID = "test-conv-001"


# ─── helpers ─────────────────────────────────────────────────────────────────


def _json(**kwargs) -> str:
    return json.dumps(kwargs)


def _defaults() -> dict:
    return empty_funnel_ai()


# ══════════════════════════════════════════════════════════════════════════════
# empty_funnel_ai
# ══════════════════════════════════════════════════════════════════════════════


def test_empty_funnel_ai_safe_defaults():
    d = empty_funnel_ai()
    assert d["has_purchase_intent"] is False
    assert d["intent_stage"] == "none"
    assert d["intent_first_at_offset_seconds"] is None
    assert d["quote_requested_at_offset_seconds"] is None
    assert d["lost_reason"] is None
    assert d["lost_reason_detail"] is None


# ══════════════════════════════════════════════════════════════════════════════
# Happy-path: valid responses
# ══════════════════════════════════════════════════════════════════════════════


class TestValidResponses:

    def test_no_intent_response(self):
        raw = _json(
            has_purchase_intent=False,
            intent_stage="none",
            intent_first_at_offset_seconds=None,
            quote_requested_at_offset_seconds=None,
            lost_reason=None,
            lost_reason_detail=None,
        )
        result = parse_funnel_response(raw, CONV_ID)
        assert result["has_purchase_intent"] is False
        assert result["intent_stage"] == "none"
        assert result["lost_reason"] is None

    def test_exploring_stage(self):
        raw = _json(
            has_purchase_intent=True,
            intent_stage="exploring",
            intent_first_at_offset_seconds=120,
            quote_requested_at_offset_seconds=None,
            lost_reason=None,
            lost_reason_detail=None,
        )
        result = parse_funnel_response(raw, CONV_ID)
        assert result["has_purchase_intent"] is True
        assert result["intent_stage"] == "exploring"
        assert result["intent_first_at_offset_seconds"] == 120

    def test_quote_requested_stage(self):
        raw = _json(
            has_purchase_intent=True,
            intent_stage="quote_requested",
            intent_first_at_offset_seconds=60,
            quote_requested_at_offset_seconds=60,
            lost_reason=None,
            lost_reason_detail=None,
        )
        result = parse_funnel_response(raw, CONV_ID)
        assert result["intent_stage"] == "quote_requested"
        assert result["quote_requested_at_offset_seconds"] == 60

    def test_quoted_stage(self):
        raw = _json(has_purchase_intent=True, intent_stage="quoted",
                    intent_first_at_offset_seconds=0, quote_requested_at_offset_seconds=300,
                    lost_reason=None, lost_reason_detail=None)
        assert parse_funnel_response(raw, CONV_ID)["intent_stage"] == "quoted"

    def test_negotiating_stage(self):
        raw = _json(has_purchase_intent=True, intent_stage="negotiating",
                    intent_first_at_offset_seconds=0, quote_requested_at_offset_seconds=None,
                    lost_reason=None, lost_reason_detail=None)
        assert parse_funnel_response(raw, CONV_ID)["intent_stage"] == "negotiating"

    def test_converted_stage(self):
        raw = _json(has_purchase_intent=True, intent_stage="converted",
                    intent_first_at_offset_seconds=0, quote_requested_at_offset_seconds=None,
                    lost_reason=None, lost_reason_detail=None)
        result = parse_funnel_response(raw, CONV_ID)
        assert result["intent_stage"] == "converted"
        assert result["has_purchase_intent"] is True

    def test_pending_stage(self):
        raw = _json(has_purchase_intent=True, intent_stage="pending",
                    intent_first_at_offset_seconds=100, quote_requested_at_offset_seconds=None,
                    lost_reason=None, lost_reason_detail=None)
        assert parse_funnel_response(raw, CONV_ID)["intent_stage"] == "pending"

    def test_lost_stage_with_price_reason(self):
        raw = _json(
            has_purchase_intent=True,
            intent_stage="lost",
            intent_first_at_offset_seconds=0,
            quote_requested_at_offset_seconds=None,
            lost_reason="price",
            lost_reason_detail="El cliente dijo que el precio era muy alto.",
        )
        result = parse_funnel_response(raw, CONV_ID)
        assert result["intent_stage"] == "lost"
        assert result["lost_reason"] == "price"
        assert result["lost_reason_detail"] == "El cliente dijo que el precio era muy alto."

    def test_all_valid_lost_reason_categories(self):
        for reason in ("price", "competition", "timing", "no_reply", "changed_mind", "other"):
            raw = _json(has_purchase_intent=True, intent_stage="lost",
                        intent_first_at_offset_seconds=0, quote_requested_at_offset_seconds=None,
                        lost_reason=reason, lost_reason_detail="detalle específico aquí.")
            result = parse_funnel_response(raw, CONV_ID)
            assert result["lost_reason"] == reason, f"Expected {reason}"

    def test_all_valid_intent_stages_accepted(self):
        valid_stages = {
            "none": False,
            "exploring": True,
            "quote_requested": True,
            "quoted": True,
            "negotiating": True,
            "converted": True,
            "lost": True,
            "pending": True,
        }
        for stage, intent in valid_stages.items():
            if stage == "lost":
                raw = _json(has_purchase_intent=intent, intent_stage=stage,
                            intent_first_at_offset_seconds=0 if intent else None,
                            quote_requested_at_offset_seconds=None,
                            lost_reason="other", lost_reason_detail="motivo.")
            else:
                raw = _json(has_purchase_intent=intent, intent_stage=stage,
                            intent_first_at_offset_seconds=0 if intent else None,
                            quote_requested_at_offset_seconds=None,
                            lost_reason=None, lost_reason_detail=None)
            result = parse_funnel_response(raw, CONV_ID)
            assert result["intent_stage"] == stage, f"Stage {stage} not accepted"


# ══════════════════════════════════════════════════════════════════════════════
# Consistency enforcement
# ══════════════════════════════════════════════════════════════════════════════


class TestConsistencyEnforcement:

    def test_stage_none_forces_has_purchase_intent_false(self):
        """Even if has_purchase_intent=true, stage=none forces it to false."""
        raw = _json(has_purchase_intent=True, intent_stage="none",
                    intent_first_at_offset_seconds=100, quote_requested_at_offset_seconds=None,
                    lost_reason=None, lost_reason_detail=None)
        result = parse_funnel_response(raw, CONV_ID)
        assert result["has_purchase_intent"] is False
        assert result["intent_stage"] == "none"

    def test_intent_false_forces_stage_to_none(self):
        """Even if stage=exploring, has_purchase_intent=false forces stage to none."""
        raw = _json(has_purchase_intent=False, intent_stage="exploring",
                    intent_first_at_offset_seconds=None, quote_requested_at_offset_seconds=None,
                    lost_reason=None, lost_reason_detail=None)
        result = parse_funnel_response(raw, CONV_ID)
        assert result["intent_stage"] == "none"
        assert result["has_purchase_intent"] is False

    def test_lost_reason_cleared_when_stage_is_not_lost(self):
        """lost_reason must be null for any stage other than lost."""
        for stage in ("pending", "quoted", "converted", "negotiating"):
            raw = _json(has_purchase_intent=True, intent_stage=stage,
                        intent_first_at_offset_seconds=0, quote_requested_at_offset_seconds=None,
                        lost_reason="price", lost_reason_detail="reason")
            result = parse_funnel_response(raw, CONV_ID)
            assert result["lost_reason"] is None, f"lost_reason not cleared for stage={stage}"
            assert result["lost_reason_detail"] is None

    def test_lost_reason_detail_cleared_when_stage_is_not_lost(self):
        raw = _json(has_purchase_intent=True, intent_stage="pending",
                    intent_first_at_offset_seconds=0, quote_requested_at_offset_seconds=None,
                    lost_reason=None, lost_reason_detail="esto es un detalle que no debería estar")
        result = parse_funnel_response(raw, CONV_ID)
        assert result["lost_reason_detail"] is None

    def test_invalid_lost_reason_category_cleared(self):
        """Unknown lost_reason category → None."""
        raw = _json(has_purchase_intent=True, intent_stage="lost",
                    intent_first_at_offset_seconds=0, quote_requested_at_offset_seconds=None,
                    lost_reason="ghosts_and_vibes", lost_reason_detail="motivo.")
        result = parse_funnel_response(raw, CONV_ID)
        assert result["lost_reason"] is None

    def test_unknown_intent_stage_falls_back_to_none(self):
        """Unrecognized stage name → none + intent=false."""
        raw = _json(has_purchase_intent=True, intent_stage="buying_hard",
                    intent_first_at_offset_seconds=0, quote_requested_at_offset_seconds=None,
                    lost_reason=None, lost_reason_detail=None)
        result = parse_funnel_response(raw, CONV_ID)
        assert result["intent_stage"] == "none"
        assert result["has_purchase_intent"] is False

    def test_lost_reason_detail_truncated_at_300_chars(self):
        long_detail = "x" * 500
        raw = _json(has_purchase_intent=True, intent_stage="lost",
                    intent_first_at_offset_seconds=0, quote_requested_at_offset_seconds=None,
                    lost_reason="other", lost_reason_detail=long_detail)
        result = parse_funnel_response(raw, CONV_ID)
        assert result["lost_reason_detail"] is not None
        assert len(result["lost_reason_detail"]) == 300


# ══════════════════════════════════════════════════════════════════════════════
# JSON format edge cases
# ══════════════════════════════════════════════════════════════════════════════


class TestJSONFormatEdgeCases:

    def test_malformed_json_returns_safe_defaults(self):
        result = parse_funnel_response("not valid json {{{", CONV_ID)
        assert result == empty_funnel_ai()

    def test_empty_string_returns_safe_defaults(self):
        result = parse_funnel_response("", CONV_ID)
        assert result == empty_funnel_ai()

    def test_json_with_markdown_fence_stripped(self):
        raw = "```json\n" + _json(has_purchase_intent=False, intent_stage="none",
                                  intent_first_at_offset_seconds=None,
                                  quote_requested_at_offset_seconds=None,
                                  lost_reason=None, lost_reason_detail=None) + "\n```"
        result = parse_funnel_response(raw, CONV_ID)
        assert result["intent_stage"] == "none"

    def test_json_with_markdown_fence_no_closing(self):
        """Fence without closing ``` should still parse."""
        raw = "```\n" + _json(has_purchase_intent=True, intent_stage="exploring",
                               intent_first_at_offset_seconds=100,
                               quote_requested_at_offset_seconds=None,
                               lost_reason=None, lost_reason_detail=None)
        result = parse_funnel_response(raw, CONV_ID)
        assert result["intent_stage"] == "exploring"

    def test_extra_fields_ignored(self):
        raw = _json(has_purchase_intent=True, intent_stage="exploring",
                    intent_first_at_offset_seconds=50, quote_requested_at_offset_seconds=None,
                    lost_reason=None, lost_reason_detail=None,
                    unknown_field="should be ignored", another_extra=42)
        result = parse_funnel_response(raw, CONV_ID)
        assert result["intent_stage"] == "exploring"

    def test_all_fields_missing_returns_safe_defaults(self):
        result = parse_funnel_response("{}", CONV_ID)
        assert result == empty_funnel_ai()

    def test_whitespace_only_string_returns_defaults(self):
        result = parse_funnel_response("   \n\t  ", CONV_ID)
        assert result == empty_funnel_ai()

    def test_integer_true_coerced_for_has_purchase_intent(self):
        """Some models return 1 instead of true."""
        raw = _json(has_purchase_intent=1, intent_stage="exploring",
                    intent_first_at_offset_seconds=0, quote_requested_at_offset_seconds=None,
                    lost_reason=None, lost_reason_detail=None)
        result = parse_funnel_response(raw, CONV_ID)
        # bool(1) = True
        assert result["has_purchase_intent"] is True

    def test_null_intent_stage_falls_back_to_none_string(self):
        raw = _json(has_purchase_intent=False, intent_stage=None,
                    intent_first_at_offset_seconds=None, quote_requested_at_offset_seconds=None,
                    lost_reason=None, lost_reason_detail=None)
        result = parse_funnel_response(raw, CONV_ID)
        assert result["intent_stage"] == "none"


# ══════════════════════════════════════════════════════════════════════════════
# _safe_offset
# ══════════════════════════════════════════════════════════════════════════════


class TestSafeOffset:

    def test_valid_integer_returned_as_is(self):
        assert _safe_offset({"k": 300}, "k") == 300

    def test_zero_is_valid(self):
        assert _safe_offset({"k": 0}, "k") == 0

    def test_float_truncated_to_int(self):
        assert _safe_offset({"k": 123.7}, "k") == 123

    def test_negative_value_returns_none(self):
        assert _safe_offset({"k": -100}, "k") is None

    def test_none_value_returns_none(self):
        assert _safe_offset({"k": None}, "k") is None

    def test_missing_key_returns_none(self):
        assert _safe_offset({}, "missing") is None

    def test_string_integer_parsed(self):
        assert _safe_offset({"k": "500"}, "k") == 500

    def test_non_numeric_string_returns_none(self):
        assert _safe_offset({"k": "abc"}, "k") is None

    def test_large_valid_offset(self):
        assert _safe_offset({"k": 86400}, "k") == 86400  # 24h in seconds

    def test_very_small_positive_float(self):
        assert _safe_offset({"k": 0.9}, "k") == 0  # truncated to 0
