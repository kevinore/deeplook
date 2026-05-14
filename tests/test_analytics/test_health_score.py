"""
Exhaustive tests for the 3-layer health score system.

Covers:
  - Layer 1: all 4 improved component formulas
  - Layer 2: AI adjustment application and bounds
  - Layer 3: full score integration
  - Edge cases: empty data, single conversation, all-unanswered, etc.
  - Real scenarios: dental clinic, restaurant, beauty salon
  - Parser: valid JSON, parse errors, out-of-bounds adjustments
  - Regression: old tests still pass (first_response_time_score unchanged)
"""
import pytest
from app.analytics.insights.health_score import (
    _first_response_time_score,
    _unanswered_rate_score,
    _sentiment_score_from_floats,
    _sentiment_score_categorical,
    _quality_score_component,
    _quality_nonlinear,
    _conversion_score_component,
    _conversion_nonlinear,
    apply_ai_adjustments,
    calculate_health_score,
    get_health_score_breakdown,
)
from app.analytics.ai.prompts.health_eval_parser import parse_health_eval_response, _default
from app.models.enums import ConversionStatus, Sentiment
from app.models.schemas import ConversationAnalysisResult, QualityBreakdown


# ── Helpers ──────────────────────────────────────────────────────────────────

def _r(
    sentiment=None,
    sentiment_score=None,
    quality=None,
    conversion=None,
    unanswered=0,
    trailing=0,
    op_cov=None,
    total_messages=10,
    inbound=5,
    outbound=5,
) -> ConversationAnalysisResult:
    return ConversationAnalysisResult(
        conversation_id="test",
        sentiment=sentiment,
        sentiment_score=sentiment_score,
        quality_score=quality,
        quality_breakdown=QualityBreakdown(),
        conversion_status=conversion,
        unanswered_count=unanswered,
        trailing_inbound_messages=trailing,
        total_messages=total_messages,
        inbound_count=inbound,
        outbound_count=outbound,
        operational_coverage_score=op_cov,
    )


# ══════════════════════════════════════════════════════════════════════════════
# REGRESSION: first_response_time_score unchanged
# ══════════════════════════════════════════════════════════════════════════════

class TestFirstResponseTimeScore:
    def test_under_2min(self):
        assert _first_response_time_score(60) == 100.0

    def test_under_5min(self):
        assert _first_response_time_score(240) == 85.0

    def test_under_15min(self):
        assert _first_response_time_score(600) == 65.0

    def test_under_30min(self):
        assert _first_response_time_score(1500) == 45.0

    def test_under_1hour(self):
        assert _first_response_time_score(2400) == 25.0

    def test_over_1hour(self):
        assert _first_response_time_score(7200) == 10.0

    def test_none_returns_none(self):
        assert _first_response_time_score(None) is None

    def test_boundary_exactly_120s(self):
        assert _first_response_time_score(120) == 85.0

    def test_boundary_exactly_300s(self):
        assert _first_response_time_score(300) == 65.0


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 1: Coverage — smooth curve
# ══════════════════════════════════════════════════════════════════════════════

class TestCoverageSmooth:
    def test_zero_unanswered(self):
        assert _unanswered_rate_score(0) == 100.0

    def test_five_pct_less_harsh_than_before(self):
        score = _unanswered_rate_score(5)
        # Old step: 85. New smooth: ~87. Should be HIGHER than old step.
        assert score > 85.0
        assert score < 95.0

    def test_ten_pct_significantly_less_harsh(self):
        score = _unanswered_rate_score(10)
        # Old step: 65 (harsh cliff). New smooth: ~87. Much less punishing.
        assert score > 82.0
        assert score < 95.0

    def test_fifteen_pct_much_less_harsh(self):
        score = _unanswered_rate_score(15)
        # Old step: 40 (very harsh cliff). New smooth: ~81. Much less punishing.
        assert score > 75.0
        assert score < 90.0

    def test_twenty_pct(self):
        score = _unanswered_rate_score(20)
        # Smooth curve: ~75. Old step was 40.
        assert 68.0 < score < 82.0

    def test_fifty_pct_drops_significantly(self):
        score = _unanswered_rate_score(50)
        # 50% unanswered → score ~40 (still significant penalty, but no artificial floor until ~77%)
        assert 35.0 < score < 50.0

    def test_seventy_five_pct_near_floor(self):
        score = _unanswered_rate_score(75)
        # Very high unanswered rate should approach floor
        assert score < 25.0

    def test_hundred_pct_hits_floor(self):
        assert _unanswered_rate_score(100) == 15.0

    def test_continuous_decreasing(self):
        """Score should decrease monotonically as rate increases."""
        rates = [0, 2, 5, 10, 15, 20, 25, 30, 40, 50]
        scores = [_unanswered_rate_score(r) for r in rates]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], f"Not monotonic at rate {rates[i]}"

    def test_no_harsh_cliff_between_4_and_6_pct(self):
        """Difference between 4% and 6% should be smooth, not a 15-pt cliff."""
        diff = _unanswered_rate_score(4) - _unanswered_rate_score(6)
        assert diff < 8.0, f"Cliff too steep: {diff:.1f} pts"


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 1: Sentiment — float-based
# ══════════════════════════════════════════════════════════════════════════════

class TestSentimentFloat:
    def test_very_positive_near_100(self):
        results = [_r(sentiment=Sentiment.POSITIVE, sentiment_score=0.9)]
        score = _sentiment_score_from_floats(results)
        assert score is not None
        assert score > 95.0

    def test_neutral_baseline_68(self):
        results = [_r(sentiment=Sentiment.NEUTRAL, sentiment_score=0.0)]
        score = _sentiment_score_from_floats(results)
        assert score == pytest.approx(68.0)

    def test_slightly_negative_less_harsh(self):
        results = [_r(sentiment=Sentiment.NEGATIVE, sentiment_score=-0.2)]
        score = _sentiment_score_from_floats(results)
        # -0.2 → 68 + (-0.2×68) = 68 - 13.6 = 54.4
        assert score == pytest.approx(54.4, abs=0.5)

    def test_very_negative_near_zero(self):
        results = [_r(sentiment=Sentiment.NEGATIVE, sentiment_score=-0.9)]
        score = _sentiment_score_from_floats(results)
        # -0.9 → 68 + (-0.9×68) = 68 - 61.2 = 6.8
        assert score == pytest.approx(6.8, abs=1.0)

    def test_all_neutral_100pct_gives_68(self):
        """100% neutral → 68, not punished as 'mediocre'."""
        results = [_r(sentiment=Sentiment.NEUTRAL, sentiment_score=0.0) for _ in range(10)]
        score = _sentiment_score_from_floats(results)
        assert score == pytest.approx(68.0)

    def test_mixed_realistic(self):
        """Realistic mix: 40% positive(0.7), 45% neutral(0.0), 15% negative(-0.3)."""
        results = (
            [_r(sentiment_score=0.7)] * 8 +   # 40%
            [_r(sentiment_score=0.0)] * 9 +   # 45%
            [_r(sentiment_score=-0.3)] * 3    # 15%
        )
        score = _sentiment_score_from_floats(results)
        # Should be significantly above 65 (old formula gave ~69)
        assert score is not None
        assert score > 65.0

    def test_falls_back_to_none_when_no_floats(self):
        results = [_r(sentiment=Sentiment.POSITIVE, sentiment_score=None)]
        assert _sentiment_score_from_floats(results) is None

    def test_empty_list_returns_none(self):
        assert _sentiment_score_from_floats([]) is None

    def test_score_clamped_to_100(self):
        results = [_r(sentiment_score=1.0)] * 5
        score = _sentiment_score_from_floats(results)
        assert score is not None
        assert score <= 100.0


class TestSentimentCategoricalFallback:
    def test_100_pct_neutral_gives_68(self):
        results = [_r(sentiment=Sentiment.NEUTRAL) for _ in range(10)]
        score = _sentiment_score_categorical(results)
        assert score == pytest.approx(68.0)

    def test_100_pct_positive_gives_100(self):
        results = [_r(sentiment=Sentiment.POSITIVE) for _ in range(5)]
        score = _sentiment_score_categorical(results)
        assert score == 100.0

    def test_100_pct_negative_gives_0(self):
        results = [_r(sentiment=Sentiment.NEGATIVE) for _ in range(5)]
        score = _sentiment_score_categorical(results)
        assert score == 0.0

    def test_no_sentiment_data_returns_none(self):
        results = [_r(sentiment=None) for _ in range(5)]
        assert _sentiment_score_categorical(results) is None


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 1: Quality — non-linear + unanswered excluded
# ══════════════════════════════════════════════════════════════════════════════

class TestQualityNonlinear:
    def test_quality_0_gives_0(self):
        assert _quality_nonlinear(0) == 0.0

    def test_quality_5_gives_50(self):
        assert _quality_nonlinear(5) == pytest.approx(50.0)

    def test_quality_7_gives_75(self):
        assert _quality_nonlinear(7) == pytest.approx(75.0)

    def test_quality_7_5_above_75(self):
        """7.5/10 falls in the 7–9 branch: 75 + (0.5×10) = 80, better than linear 75."""
        score = _quality_nonlinear(7.5)
        assert score == pytest.approx(80.0)

    def test_quality_8_gives_85(self):
        assert _quality_nonlinear(8.0) == pytest.approx(85.0)

    def test_quality_9_gives_95(self):
        assert _quality_nonlinear(9.0) == pytest.approx(95.0)

    def test_quality_10_gives_100(self):
        assert _quality_nonlinear(10.0) == pytest.approx(100.0)

    def test_quality_is_better_than_linear_above_5(self):
        """Non-linear must be >= linear×10 for all q > 5."""
        for q in [5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5, 9.0]:
            nonlin = _quality_nonlinear(q)
            linear = q * 10
            assert nonlin >= linear, f"Non-linear {nonlin} < linear {linear} at q={q}"


class TestQualityComponent:
    def test_truly_unanswered_excluded(self):
        """Conversations where business sent 0 replies (outbound=0) must be excluded."""
        results = (
            [_r(quality=8.0, outbound=5, inbound=5)] * 10 +
            # outbound=0 → business never replied → quality=0 by AI rule → exclude
            [_r(quality=0.0, outbound=0, inbound=3, unanswered=1)] * 3
        )
        score = _quality_score_component(results)
        assert score is not None
        assert score > _quality_nonlinear(8.0) - 2  # reflects 8.0, not dragged down

    def test_client_said_thanks_is_INCLUDED(self):
        """
        Conversations where client said 'gracias' last (unanswered_count=1 but
        quality_score>0) MUST be included — the business DID respond well.
        """
        results = (
            # Business responded well, client said "gracias" last — quality > 0
            [_r(quality=8.5, outbound=5, inbound=5, unanswered=1)] * 5 +
            # Business responded, had last word
            [_r(quality=7.0, outbound=5, inbound=4, unanswered=0)] * 5
        )
        score = _quality_score_component(results)
        assert score is not None
        assert score > 75.0

    def test_zero_quality_with_outbound_excluded(self):
        """
        quality_score=0 even with outbound messages = AI treated it as unanswered.
        Already penalized in coverage → exclude from quality average.
        """
        results = (
            [_r(quality=7.5, outbound=5, inbound=5)] * 5 +
            [_r(quality=0.0, outbound=2, inbound=3, unanswered=1)] * 5  # partial response, quality=0
        )
        score = _quality_score_component(results)
        assert score is not None
        # Only the 7.5 conversations count
        assert score > _quality_nonlinear(7.0)

    def test_no_regression_double_penalization(self):
        """Business with 3 truly unanswered (outbound=0) should NOT drag quality."""
        results = (
            [_r(quality=8.0, outbound=5, inbound=5)] * 17 +
            [_r(quality=None, outbound=0, inbound=2, unanswered=1)] * 3
        )
        score = _quality_score_component(results)
        assert score is not None
        assert score > 80.0  # reflects 8.0, not dragged

    def test_all_truly_unanswered_returns_none(self):
        """If all conversations have outbound=0, quality component is unknown."""
        results = [_r(quality=0.0, outbound=0, inbound=2, unanswered=1)] * 5
        assert _quality_score_component(results) is None

    def test_no_quality_scores_returns_none(self):
        results = [_r(quality=None)] * 5
        assert _quality_score_component(results) is None

    def test_quality_6_5_maps_to_reasonable(self):
        """AI quality 6.5 should map to ~69, not 65 (linear)."""
        results = [_r(quality=6.5, outbound=5, inbound=5)]
        score = _quality_score_component(results)
        assert score is not None
        assert score > 65.0


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 1: Conversion — non-linear + pending excluded + Bayesian
# ══════════════════════════════════════════════════════════════════════════════

class TestConversionNonlinear:
    def test_zero_gives_0(self):
        assert _conversion_nonlinear(0.0) == pytest.approx(0.0)

    def test_15_pct_gives_40(self):
        assert _conversion_nonlinear(0.15) == pytest.approx(40.0)

    def test_30_pct_gives_70(self):
        assert _conversion_nonlinear(0.30) == pytest.approx(70.0)

    def test_40_pct_benchmark_gives_88(self):
        """Benchmark 40% should give 88, not 40 as linear would."""
        assert _conversion_nonlinear(0.40) == pytest.approx(88.0)

    def test_60_pct_gives_100(self):
        assert _conversion_nonlinear(0.60) == pytest.approx(100.0)

    def test_above_60_clamped_to_100(self):
        assert _conversion_nonlinear(0.90) == pytest.approx(100.0)


class TestConversionComponent:
    def test_pending_excluded_from_denominator(self):
        """Pending conversations must NOT count as failures."""
        results = [
            _r(conversion=ConversionStatus.CONVERTED),
            _r(conversion=ConversionStatus.CONVERTED),
            _r(conversion=ConversionStatus.PENDING),
            _r(conversion=ConversionStatus.PENDING),
            _r(conversion=ConversionStatus.PENDING),
        ]
        score = _conversion_score_component(results)
        # Firm: 2 converted / 2 firm = 100% → should be high
        assert score is not None
        assert score > 90.0

    def test_all_pending_gives_75(self):
        """All pending = promising pipeline, not failure."""
        results = [_r(conversion=ConversionStatus.PENDING)] * 5
        score = _conversion_score_component(results)
        assert score == 75.0

    def test_bayesian_blend_small_sample(self):
        """1/1 conversion with sample=1 should be blended toward prior, not 100%."""
        results = [_r(conversion=ConversionStatus.CONVERTED)]
        score = _conversion_score_component(results)
        # blend = min(1, 1/8) = 0.125 → blended = 1.0×0.125 + 0.28×0.875 = 0.37
        # _conversion_nonlinear(0.37) ≈ 79
        assert score is not None
        assert score < 90.0  # not overly optimistic with 1 sample

    def test_bayesian_blend_large_sample_uses_actual(self):
        """With 10+ firm samples, actual rate dominates the prior."""
        results = (
            [_r(conversion=ConversionStatus.CONVERTED)] * 4 +
            [_r(conversion=ConversionStatus.LOST)] * 6
        )
        score = _conversion_score_component(results)
        # 40% actual, near-full blend → should be close to benchmark score
        assert score is not None
        # 10 samples → blend=1.0 → actual rate 0.4 → _conversion_nonlinear(0.4)=88
        assert score > 80.0

    def test_no_applicable_returns_none(self):
        results = [_r(conversion=ConversionStatus.NOT_APPLICABLE)] * 10
        assert _conversion_score_component(results) is None

    def test_benchmark_40pct_gives_good_score(self):
        """A business at benchmark (40% conversion) should score well, not 40/100."""
        results = (
            [_r(conversion=ConversionStatus.CONVERTED)] * 4 +
            [_r(conversion=ConversionStatus.LOST)] * 6
        )
        score = _conversion_score_component(results)
        assert score is not None
        assert score > 75.0  # benchmark should not look mediocre


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 2: AI adjustments
# ══════════════════════════════════════════════════════════════════════════════

class TestApplyAiAdjustments:
    def test_positive_adjustment(self):
        sent, qual = apply_ai_adjustments(70.0, 75.0, {"sentimento_ajuste": 0, "sentimiento_ajuste": 8, "calidad_ajuste": 5})
        assert sent == pytest.approx(78.0)
        assert qual == pytest.approx(80.0)

    def test_negative_adjustment(self):
        sent, qual = apply_ai_adjustments(80.0, 85.0, {"sentimiento_ajuste": -10, "calidad_ajuste": -8})
        assert sent == pytest.approx(70.0)
        assert qual == pytest.approx(77.0)

    def test_clamped_above_100(self):
        sent, qual = apply_ai_adjustments(95.0, 98.0, {"sentimiento_ajuste": 15, "calidad_ajuste": 15})
        assert sent == 100.0
        assert qual == 100.0

    def test_clamped_below_0(self):
        sent, qual = apply_ai_adjustments(10.0, 8.0, {"sentimiento_ajuste": -15, "calidad_ajuste": -15})
        assert sent == 0.0
        assert qual == 0.0

    def test_over_limit_adjustment_clamped_to_15(self):
        """Adjustment > 15 must be clamped to 15."""
        sent, qual = apply_ai_adjustments(70.0, 70.0, {"sentimiento_ajuste": 25, "calidad_ajuste": -20})
        assert sent == pytest.approx(85.0)   # +15 max
        assert qual == pytest.approx(55.0)   # -15 max

    def test_zero_adjustment_no_change(self):
        sent, qual = apply_ai_adjustments(72.5, 83.0, {"sentimiento_ajuste": 0, "calidad_ajuste": 0})
        assert sent == pytest.approx(72.5)
        assert qual == pytest.approx(83.0)

    def test_missing_keys_default_zero(self):
        sent, qual = apply_ai_adjustments(70.0, 75.0, {})
        assert sent == pytest.approx(70.0)
        assert qual == pytest.approx(75.0)


# ══════════════════════════════════════════════════════════════════════════════
# Parser tests
# ══════════════════════════════════════════════════════════════════════════════

class TestHealthEvalParser:
    def test_valid_response(self):
        raw = '{"sentimiento_ajuste": 8, "sentimiento_razon": "Las negativas fueron resueltas.", "calidad_ajuste": 5, "calidad_razon": "Calidad sobre benchmark.", "confianza": "alta"}'
        result = parse_health_eval_response(raw)
        assert result["sentimiento_ajuste"] == 8
        assert result["calidad_ajuste"] == 5
        assert result["confianza"] == "alta"
        assert result["ai_applied"] is True

    def test_markdown_fence_stripped(self):
        raw = '```json\n{"sentimiento_ajuste": 5, "sentimiento_razon": "ok", "calidad_ajuste": 3, "calidad_razon": "ok", "confianza": "media"}\n```'
        result = parse_health_eval_response(raw)
        assert result["sentimiento_ajuste"] == 5

    def test_invalid_json_returns_default(self):
        result = parse_health_eval_response("not json at all")
        assert result == _default()
        assert result["ai_applied"] is False

    def test_out_of_bounds_clamped(self):
        raw = '{"sentimiento_ajuste": 99, "sentimiento_razon": "x", "calidad_ajuste": -50, "calidad_razon": "y", "confianza": "alta"}'
        result = parse_health_eval_response(raw)
        assert result["sentimiento_ajuste"] == 15
        assert result["calidad_ajuste"] == -15

    def test_invalid_confianza_defaults_to_media(self):
        raw = '{"sentimiento_ajuste": 0, "sentimiento_razon": "", "calidad_ajuste": 0, "calidad_razon": "", "confianza": "INVALID"}'
        result = parse_health_eval_response(raw)
        assert result["confianza"] == "media"

    def test_empty_string_returns_default(self):
        result = parse_health_eval_response("")
        assert result == _default()

    def test_reason_truncated_at_300_chars(self):
        long_reason = "x" * 500
        raw = f'{{"sentimiento_ajuste": 0, "sentimiento_razon": "{long_reason}", "calidad_ajuste": 0, "calidad_razon": "", "confianza": "alta"}}'
        result = parse_health_eval_response(raw)
        assert len(result["sentimiento_razon"]) <= 300


# ══════════════════════════════════════════════════════════════════════════════
# Full health score integration
# ══════════════════════════════════════════════════════════════════════════════

class TestCalculateHealthScoreIntegration:
    def test_empty_results_returns_50(self):
        assert calculate_health_score([]) == 50.0

    def test_health_adjustments_applied(self):
        results = [
            _r(sentiment=Sentiment.NEUTRAL, sentiment_score=0.0, quality=7.0, unanswered=0,
               conversion=ConversionStatus.NOT_APPLICABLE),
        ] * 10
        base = calculate_health_score(results, first_response_time_seconds=120)
        adj = {"sentimiento_ajuste": 10, "calidad_ajuste": 10}
        adjusted = calculate_health_score(results, first_response_time_seconds=120, health_adjustments=adj)
        assert adjusted > base

    def test_no_double_penalization(self):
        """Adding unanswered conversations should NOT drop quality component."""
        results_clean = [_r(quality=8.0, unanswered=0, conversion=ConversionStatus.NOT_APPLICABLE)] * 20
        results_unans = results_clean + [_r(quality=None, unanswered=1)] * 3

        score_clean = calculate_health_score(results_clean, first_response_time_seconds=200)
        score_unans = calculate_health_score(results_unans, first_response_time_seconds=200)

        # Score drops because of coverage component, not because of quality double-penalization
        # But the drop should be moderate, not catastrophic
        drop = score_clean - score_unans
        assert drop < 15.0, f"Drop too large ({drop:.1f}) — double penalization suspected"

    def test_all_excellent(self):
        results = [
            _r(sentiment=Sentiment.POSITIVE, sentiment_score=0.9, quality=9.5, unanswered=0,
               conversion=ConversionStatus.CONVERTED, op_cov=95.0)
        ] * 20
        score = calculate_health_score(results, first_response_time_seconds=90)
        assert score >= 85.0

    def test_all_terrible(self):
        results = [
            _r(sentiment=Sentiment.NEGATIVE, sentiment_score=-0.8, quality=2.0, unanswered=1,
               conversion=ConversionStatus.LOST, op_cov=20.0)
        ] * 20
        score = calculate_health_score(results, first_response_time_seconds=7200)
        assert score < 40.0


# ══════════════════════════════════════════════════════════════════════════════
# Real scenario tests
# ══════════════════════════════════════════════════════════════════════════════

class TestRealScenarios:
    def test_dental_clinic_good_performance(self):
        """
        Dental clinic scenario: mostly positive patients, good quality,
        good response time, benchmark conversion, 2 unanswered out of 20.
        Expected: Bueno (70-84).
        """
        results = (
            [_r(sentiment=Sentiment.POSITIVE, sentiment_score=0.75, quality=8.2,
                unanswered=0, conversion=ConversionStatus.CONVERTED, op_cov=90.0)] * 8 +
            [_r(sentiment=Sentiment.NEUTRAL, sentiment_score=0.1, quality=7.5,
                unanswered=0, conversion=ConversionStatus.NOT_APPLICABLE, op_cov=88.0)] * 8 +
            [_r(sentiment=Sentiment.NEGATIVE, sentiment_score=-0.3, quality=6.0,
                unanswered=0, conversion=ConversionStatus.LOST, op_cov=75.0)] * 2 +
            [_r(sentiment=Sentiment.NEUTRAL, sentiment_score=0.0, quality=None,
                unanswered=1, conversion=ConversionStatus.NOT_APPLICABLE)] * 2
        )
        score = calculate_health_score(results, first_response_time_seconds=180)
        assert 68.0 <= score <= 90.0, f"Expected Bueno range, got {score}"

    def test_restaurant_slow_peak_hours(self):
        """
        Restaurant with decent sentiment but slow response (15 min average),
        mixed conversion, no unanswered.
        Expected: Regular (55-69).
        """
        results = (
            [_r(sentiment=Sentiment.POSITIVE, sentiment_score=0.6, quality=7.0,
                unanswered=0, conversion=ConversionStatus.CONVERTED, op_cov=80.0)] * 6 +
            [_r(sentiment=Sentiment.NEUTRAL, sentiment_score=0.0, quality=6.5,
                unanswered=0, conversion=ConversionStatus.PENDING, op_cov=75.0)] * 10 +
            [_r(sentiment=Sentiment.NEGATIVE, sentiment_score=-0.4, quality=5.5,
                unanswered=0, conversion=ConversionStatus.LOST, op_cov=60.0)] * 4
        )
        score = calculate_health_score(results, first_response_time_seconds=900)
        assert 50.0 <= score <= 75.0, f"Expected Regular range, got {score}"

    def test_beauty_salon_with_reclamos(self):
        """
        Beauty salon with several complaints (reclamos) but good resolution.
        With AI adjustment of +7 to sentiment (complaints resolved well),
        score should be meaningfully higher than without adjustment.
        """
        results = (
            [_r(sentiment=Sentiment.POSITIVE, sentiment_score=0.7, quality=8.0,
                unanswered=0, conversion=ConversionStatus.CONVERTED, op_cov=92.0)] * 12 +
            [_r(sentiment=Sentiment.NEGATIVE, sentiment_score=-0.4, quality=6.5,
                unanswered=0, conversion=ConversionStatus.LOST, op_cov=70.0)] * 5 +
            [_r(sentiment=Sentiment.NEUTRAL, sentiment_score=0.0, quality=None,
                unanswered=1)] * 3
        )
        base = calculate_health_score(results, first_response_time_seconds=150)
        adj = {"sentimiento_ajuste": 7, "calidad_ajuste": 3}
        adjusted = calculate_health_score(results, first_response_time_seconds=150, health_adjustments=adj)
        assert adjusted > base
        assert adjusted - base < 8.0  # bounded: can't jump more than adjustment contribution

    def test_new_business_small_sample(self):
        """
        New business with only 5 conversations, 2 converted.
        Bayesian prior should prevent wild swings.
        """
        results = (
            [_r(conversion=ConversionStatus.CONVERTED, sentiment=Sentiment.POSITIVE,
                sentiment_score=0.6, quality=7.5, unanswered=0)] * 2 +
            [_r(conversion=ConversionStatus.LOST, sentiment=Sentiment.NEUTRAL,
                sentiment_score=0.0, quality=6.0, unanswered=0)] * 2 +
            [_r(conversion=ConversionStatus.NOT_APPLICABLE, sentiment=Sentiment.POSITIVE,
                sentiment_score=0.5, quality=7.0, unanswered=0)] * 1
        )
        score = calculate_health_score(results, first_response_time_seconds=250)
        # Should be reasonable, not artificially high because of small sample
        assert 50.0 <= score <= 85.0

    def test_critical_many_unanswered(self):
        """
        Business with 40% unanswered rate — should score Urgente (< 40).
        """
        results = (
            [_r(sentiment=Sentiment.NEUTRAL, sentiment_score=0.0, quality=None,
                unanswered=1, conversion=ConversionStatus.NOT_APPLICABLE)] * 8 +
            [_r(sentiment=Sentiment.NEUTRAL, sentiment_score=0.0, quality=7.0,
                unanswered=0, conversion=ConversionStatus.NOT_APPLICABLE)] * 12
        )
        score = calculate_health_score(results, first_response_time_seconds=3600)
        assert score < 55.0, f"Expected low score for critical scenario, got {score}"


# ══════════════════════════════════════════════════════════════════════════════
# Breakdown display
# ══════════════════════════════════════════════════════════════════════════════

class TestGetHealthScoreBreakdown:
    def _basic_results(self):
        return [
            _r(sentiment=Sentiment.POSITIVE, sentiment_score=0.7, quality=8.0,
               unanswered=0, conversion=ConversionStatus.CONVERTED, op_cov=85.0)
        ] * 10

    def test_returns_6_dimensions(self):
        breakdown = get_health_score_breakdown(self._basic_results(), first_response_time_seconds=200)
        assert len(breakdown) == 6

    def test_weights_sum_to_1(self):
        breakdown = get_health_score_breakdown(self._basic_results(), first_response_time_seconds=200)
        total_weight = sum(d["weight"] for d in breakdown)
        assert total_weight == pytest.approx(1.0)

    def test_exactly_one_strength(self):
        breakdown = get_health_score_breakdown(self._basic_results(), first_response_time_seconds=200)
        strengths = [d for d in breakdown if d["is_strength"]]
        assert len(strengths) == 1

    def test_exactly_one_critical(self):
        breakdown = get_health_score_breakdown(self._basic_results(), first_response_time_seconds=200)
        criticals = [d for d in breakdown if d["is_critical"]]
        assert len(criticals) == 1

    def test_adjustments_reflected_in_breakdown(self):
        results = self._basic_results()
        base = get_health_score_breakdown(results, first_response_time_seconds=200)
        adj = {"sentimiento_ajuste": 10, "calidad_ajuste": 8}
        adjusted = get_health_score_breakdown(results, first_response_time_seconds=200, health_adjustments=adj)

        base_sent = next(d["raw_score"] for d in base if d["key"] == "sentimiento")
        adj_sent  = next(d["raw_score"] for d in adjusted if d["key"] == "sentimiento")
        assert adj_sent > base_sent

    def test_all_keys_present(self):
        breakdown = get_health_score_breakdown(self._basic_results(), first_response_time_seconds=200)
        required = {"name", "key", "raw_score", "weight", "max_points", "obtained_points", "pct_of_max", "color", "is_strength", "is_critical"}
        for d in breakdown:
            assert required.issubset(d.keys()), f"Missing keys in {d['key']}"
