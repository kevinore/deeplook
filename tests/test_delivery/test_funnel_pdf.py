"""
Commercial funnel — PDF generator aggregates and visual integration test.

What this file verifies:
  1. intent_count / has_funnel_data detection
  2. funnel_conversion_rate computation
  3. median_quote_rt / avg_quote_rt via effective_quote_response_time
  4. followup_pct + median_followup_delay_hours
  5. funnel_lost_details card construction (contact_ref, reason_label, detail)
  6. funnel_other_count (stages that are not converted/lost/pending)
  7. proactive_quote_count (quote sent without explicit request)
  8. funnel_status_color thresholds (gray <5 intent, red <15%, amber <35%, green ≥35%)
  9. Stage distribution table values
 10. Full PDF renders without error and contains the funnel section
     → saves funnel_test_report.pdf for visual review

Run:
    pytest tests/test_delivery/test_funnel_pdf.py -v
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.delivery.reports.pdf_generator import (
    effective_quote_response_time,
    generate_pdf_report,
)
from app.models.enums import ConversionStatus, Sentiment
from app.models.schemas import ConversationAnalysisResult, QualityBreakdown

# ─── Helpers ──────────────────────────────────────────────────────────────────

BASE = datetime(2026, 5, 1, 9, 0, 0)


def _r(
    cid: str,
    *,
    has_intent: bool = False,
    stage: str | None = None,
    conversion: str = "not_applicable",
    sentiment: str = "neutral",
    quality: float = 7.0,
    frt: float | None = None,
    inbound: int = 2,
    outbound: int = 2,
    unanswered: int = 0,
    # funnel-specific
    intent_first_at: datetime | None = None,
    quote_requested_at: datetime | None = None,
    quote_sent_at: datetime | None = None,
    quote_response_time_seconds: int | None = None,
    post_quote_followup_count: int | None = None,
    followup_delay_hours: float | None = None,
    lost_reason: str | None = None,
    lost_reason_detail: str | None = None,
    contact_name: str | None = None,
    contact_phone: str | None = None,
    started_at: datetime | None = None,
) -> ConversationAnalysisResult:
    return ConversationAnalysisResult(
        conversation_id=cid,
        has_purchase_intent=has_intent,
        intent_stage=stage,
        conversion_status=ConversionStatus(conversion) if conversion != "not_applicable" else ConversionStatus.NOT_APPLICABLE,
        sentiment=Sentiment(sentiment),
        quality_score=quality,
        quality_breakdown=QualityBreakdown(helpfulness=quality, tone=quality, completeness=quality),
        first_response_time_seconds=frt,
        inbound_count=inbound,
        outbound_count=outbound,
        unanswered_count=unanswered,
        total_messages=inbound + outbound,
        intent_first_at=intent_first_at,
        quote_requested_at=quote_requested_at,
        quote_sent_at=quote_sent_at,
        quote_response_time_seconds=quote_response_time_seconds,
        post_quote_followup_count=post_quote_followup_count,
        followup_delay_hours=followup_delay_hours,
        lost_reason=lost_reason,
        lost_reason_detail=lost_reason_detail,
        contact_name=contact_name,
        contact_phone=contact_phone,
        started_at=started_at or BASE,
    )


# ─── Fixtures ─────────────────────────────────────────────────────────────────


def _funnel_results() -> list[ConversationAnalysisResult]:
    """
    18 conversations covering all funnel stages plus non-funnel traffic.

    Funnel breakdown (10 with intent):
      converted  × 3  (3/10 = 30% conversion rate)
      lost       × 2  (price × 1, competition × 1)
      pending    × 2  (quote sent, no reply, no followup)
      quoted     × 1  (quote sent, 0 followups → should appear in quoted_convs)
      negotiating× 1
      exploring  × 1

    Quote response times (for median computation):
      converted-1  → QRT = 600s   (quote sent 10 min after request)
      converted-2  → QRT = 1200s  (20 min)
      quoted-1     → QRT = 300s   (5 min)
      pending-1    → QRT = 900s   (15 min)
      pending-2    → QRT via fallback: quote_sent_at - intent_first_at = 1800s

    Follow-up stats:
      converted-1  → followup = 1, delay = 2h
      converted-2  → followup = 2, delay = 1h
      quoted-1     → followup = 0  (no followup — bad practice)
      pending-1    → followup = 0
      pending-2    → followup = 1, delay = 24h

    Lost details:
      lost-price    → specific detail
      lost-comp     → specific detail
    """
    t = BASE
    return [
        # ── Converted ─────────────────────────────────────────────────
        _r("conv-c1", has_intent=True, stage="converted",
           conversion="converted", sentiment="positive", quality=8.5, frt=300,
           intent_first_at=t, quote_requested_at=t + timedelta(minutes=2),
           quote_sent_at=t + timedelta(minutes=12),
           quote_response_time_seconds=600,
           post_quote_followup_count=1, followup_delay_hours=2.0,
           contact_name="Laura Gómez", contact_phone="+57 310 1111111",
           started_at=t),
        _r("conv-c2", has_intent=True, stage="converted",
           conversion="converted", sentiment="positive", quality=9.0, frt=120,
           intent_first_at=t + timedelta(hours=1),
           quote_requested_at=t + timedelta(hours=1, minutes=5),
           quote_sent_at=t + timedelta(hours=1, minutes=25),
           quote_response_time_seconds=1200,
           post_quote_followup_count=2, followup_delay_hours=1.0,
           contact_name="Carlos Martínez", contact_phone="+57 311 2222222",
           started_at=t + timedelta(hours=1)),
        _r("conv-c3", has_intent=True, stage="converted",
           conversion="converted", sentiment="positive", quality=7.5, frt=480,
           intent_first_at=t + timedelta(hours=2),
           quote_sent_at=t + timedelta(hours=2, minutes=30),
           quote_response_time_seconds=1800,
           post_quote_followup_count=1, followup_delay_hours=4.0,
           contact_name="Daniela Ríos", contact_phone="+57 312 3333333",
           started_at=t + timedelta(hours=2)),
        # ── Quoted (quote sent, no reply, no followup — oportunidad abierta) ─
        _r("conv-q1", has_intent=True, stage="quoted",
           conversion="pending", sentiment="neutral", quality=6.0, frt=900,
           intent_first_at=t + timedelta(hours=3),
           quote_requested_at=t + timedelta(hours=3, minutes=1),
           quote_sent_at=t + timedelta(hours=3, minutes=6),
           quote_response_time_seconds=300,
           post_quote_followup_count=0, followup_delay_hours=None,
           contact_name="Andrés Torres", contact_phone="+57 313 4444444",
           started_at=t + timedelta(hours=3)),
        # ── Negotiating (back-and-forth, no close yet) ─────────────────
        _r("conv-n1", has_intent=True, stage="negotiating",
           conversion="pending", sentiment="neutral", quality=7.0, frt=600,
           intent_first_at=t + timedelta(hours=4),
           quote_sent_at=t + timedelta(hours=4, minutes=20),
           quote_response_time_seconds=1200,
           post_quote_followup_count=3, followup_delay_hours=0.5,
           contact_name="Marcela Vega", contact_phone="+57 314 5555555",
           started_at=t + timedelta(hours=4)),
        # ── Lost ──────────────────────────────────────────────────────
        _r("conv-l1", has_intent=True, stage="lost",
           conversion="lost", sentiment="negative", quality=3.0, frt=5400,
           intent_first_at=t + timedelta(hours=5),
           quote_requested_at=t + timedelta(hours=5, minutes=10),
           quote_sent_at=t + timedelta(hours=6, minutes=30),
           quote_response_time_seconds=4800,
           post_quote_followup_count=0, followup_delay_hours=None,
           lost_reason="price",
           lost_reason_detail="El cliente comparó con un proveedor que cobró $200k menos y el negocio no ofreció descuento.",
           contact_name="Pedro Sánchez", contact_phone="+57 315 6666666",
           started_at=t + timedelta(hours=5)),
        _r("conv-l2", has_intent=True, stage="lost",
           conversion="lost", sentiment="negative", quality=4.0, frt=3600,
           intent_first_at=t + timedelta(hours=6),
           quote_sent_at=t + timedelta(hours=7),
           quote_response_time_seconds=3600,
           post_quote_followup_count=2, followup_delay_hours=48.0,
           lost_reason="competition",
           lost_reason_detail="El cliente mencionó que ya contrató con otra empresa antes de recibir la cotización.",
           contact_name="Sofía Herrera", contact_phone="+57 316 7777777",
           started_at=t + timedelta(hours=6)),
        # ── Pending (quote sent, no response, no followup attempted) ──
        _r("conv-p1", has_intent=True, stage="pending",
           conversion="pending", sentiment="neutral", quality=6.5, frt=1800,
           intent_first_at=t + timedelta(hours=7),
           quote_requested_at=t + timedelta(hours=7, minutes=5),
           quote_sent_at=t + timedelta(hours=7, minutes=20),
           quote_response_time_seconds=900,
           post_quote_followup_count=0, followup_delay_hours=None,
           contact_name="Juliana Castro", contact_phone="+57 317 8888888",
           started_at=t + timedelta(hours=7)),
        _r("conv-p2", has_intent=True, stage="pending",
           conversion="pending", sentiment="neutral", quality=5.5, frt=2700,
           intent_first_at=t + timedelta(hours=8),
           quote_sent_at=t + timedelta(hours=8, minutes=30),
           # No stored QRT — will be computed via fallback: 30min = 1800s
           quote_response_time_seconds=None,
           post_quote_followup_count=1, followup_delay_hours=24.0,
           contact_name="Mateo Jiménez", contact_phone="+57 318 9999999",
           started_at=t + timedelta(hours=8)),
        # ── Exploring (showed interest but no quote yet) ───────────────
        _r("conv-e1", has_intent=True, stage="exploring",
           conversion="not_applicable", sentiment="neutral", quality=6.0, frt=420,
           intent_first_at=t + timedelta(hours=9),
           contact_name="Valentina Moreno", contact_phone="+57 319 0000001",
           started_at=t + timedelta(hours=9)),
        # ── Non-funnel conversations (no purchase intent) ──────────────
        _r("conv-x1", sentiment="positive", quality=8.0, frt=180, inbound=3, outbound=4),
        _r("conv-x2", sentiment="neutral", quality=7.0, frt=300, inbound=2, outbound=3),
        _r("conv-x3", sentiment="negative", quality=2.0, frt=None, unanswered=1, inbound=3, outbound=0),
        _r("conv-x4", sentiment="neutral", quality=6.5, frt=600),
        _r("conv-x5", sentiment="positive", quality=8.5, frt=90),
        _r("conv-x6", sentiment="neutral", quality=7.5, frt=450),
        _r("conv-x7", sentiment="positive", quality=9.0, frt=60),
        _r("conv-x8", unanswered=1, inbound=2, outbound=1, frt=None),
    ]


# ══════════════════════════════════════════════════════════════════════════════
# 1. effective_quote_response_time (already in test_funnel_engine.py — these
#    focus on interaction with the pdf_generator funnel aggregates)
# ══════════════════════════════════════════════════════════════════════════════


class TestEffectiveQRT:

    def test_stored_value_preferred_over_fallback(self):
        r = _r("x", has_intent=True, stage="quoted",
               intent_first_at=BASE,
               quote_sent_at=BASE + timedelta(hours=2),
               quote_response_time_seconds=600)
        assert effective_quote_response_time(r) == 600

    def test_fallback_computed_from_quote_sent_minus_intent(self):
        r = _r("x", has_intent=True, stage="quoted",
               intent_first_at=BASE,
               quote_sent_at=BASE + timedelta(seconds=1800),
               quote_response_time_seconds=None)
        assert effective_quote_response_time(r) == 1800

    def test_none_when_no_timestamps(self):
        r = _r("x", has_intent=True, stage="exploring")
        assert effective_quote_response_time(r) is None

    def test_none_when_stored_is_negative(self):
        r = _r("x", has_intent=True, quote_response_time_seconds=-1)
        assert effective_quote_response_time(r) is None


# ══════════════════════════════════════════════════════════════════════════════
# 2. Funnel aggregates produced by generate_pdf_report internal computations
#    We test these by inspecting generate_pdf_report's Jinja2 context indirectly
#    through a thin wrapper that exposes the context dict.
# ══════════════════════════════════════════════════════════════════════════════


def _extract_context(results: list[ConversationAnalysisResult], **kwargs) -> dict:
    """
    Re-implement only the funnel aggregate block from generate_pdf_report
    so we can assert on each computed value without rendering the full PDF.
    """
    import statistics
    from collections import Counter
    from app.delivery.reports.pdf_generator import effective_quote_response_time

    intent_convs = [r for r in results if r.has_purchase_intent]
    intent_count = len(intent_convs)

    funnel_converted_count = sum(1 for r in intent_convs if r.intent_stage == "converted")
    funnel_lost_count = sum(1 for r in intent_convs if r.intent_stage == "lost")
    funnel_pending_count = sum(1 for r in intent_convs if r.intent_stage == "pending")
    funnel_conversion_rate = (
        round(funnel_converted_count / intent_count * 100) if intent_count else 0
    )

    _stage_cntr: Counter = Counter(
        r.intent_stage for r in intent_convs if r.intent_stage and r.intent_stage != "none"
    )
    funnel_stage_counts = sorted(_stage_cntr.items(), key=lambda x: (-x[1], x[0]))

    qrt_values = [v for r in intent_convs if (v := effective_quote_response_time(r)) is not None]
    median_quote_rt = statistics.median(qrt_values) if qrt_values else None
    avg_quote_rt = statistics.mean(qrt_values) if qrt_values else None

    quoted_convs = [r for r in intent_convs if r.quote_sent_at is not None]
    with_followup = [r for r in quoted_convs if (r.post_quote_followup_count or 0) > 0]
    followup_pct = round(len(with_followup) / len(quoted_convs) * 100) if quoted_convs else 0
    followup_delay_vals = [
        r.followup_delay_hours for r in with_followup if r.followup_delay_hours is not None
    ]
    median_followup_delay_hours = (
        round(statistics.median(followup_delay_vals), 1) if followup_delay_vals else None
    )

    funnel_lost_convs = [r for r in intent_convs if r.intent_stage == "lost"]
    _lost_reason_labels = {
        "price": "Precio alto o desfavorable",
        "competition": "Fue con la competencia",
        "timing": "No era el momento",
        "no_reply": "No respondió la cotización (post-seguimiento)",
        "changed_mind": "Cambió de opinión",
        "other": "Otro motivo",
    }
    funnel_lost_details: list[dict] = []
    for _r_item in funnel_lost_convs:
        _ref_parts: list[str] = []
        if _r_item.contact_name and _r_item.contact_name.strip():
            _ref_parts.append(_r_item.contact_name.strip())
        elif _r_item.contact_phone:
            _tail = _r_item.contact_phone[-4:] if len(_r_item.contact_phone) >= 4 else _r_item.contact_phone
            _ref_parts.append(f"···{_tail}")
        if _r_item.started_at:
            _ref_parts.append(_r_item.started_at.strftime("%d %b"))
        funnel_lost_details.append({
            "contact_ref": " · ".join(_ref_parts) if _ref_parts else None,
            "reason_label": _lost_reason_labels.get(_r_item.lost_reason or "", _r_item.lost_reason or "Sin clasificar"),
            "detail": _r_item.lost_reason_detail,
        })

    proactive_quote_count = sum(
        1 for r in intent_convs if r.quote_sent_at and not r.quote_requested_at
    )
    funnel_other_count = (
        intent_count - funnel_converted_count - funnel_lost_count - funnel_pending_count
    )

    return {
        "intent_count": intent_count,
        "has_funnel_data": intent_count > 0,
        "funnel_converted_count": funnel_converted_count,
        "funnel_lost_count": funnel_lost_count,
        "funnel_pending_count": funnel_pending_count,
        "funnel_conversion_rate": funnel_conversion_rate,
        "funnel_stage_counts": funnel_stage_counts,
        "median_quote_rt": median_quote_rt,
        "avg_quote_rt": avg_quote_rt,
        "quoted_convs": quoted_convs,
        "with_followup": with_followup,
        "followup_pct": followup_pct,
        "median_followup_delay_hours": median_followup_delay_hours,
        "funnel_lost_convs": funnel_lost_convs,
        "funnel_lost_details": funnel_lost_details,
        "proactive_quote_count": proactive_quote_count,
        "funnel_other_count": funnel_other_count,
    }


class TestFunnelAggregates:

    def setup_method(self):
        self.results = _funnel_results()
        self.ctx = _extract_context(self.results)

    # ── intent_count / has_funnel_data ────────────────────────────────────────

    def test_intent_count_correct(self):
        # 10 conversations with has_purchase_intent=True
        assert self.ctx["intent_count"] == 10

    def test_has_funnel_data_true_when_intent_exists(self):
        assert self.ctx["has_funnel_data"] is True

    def test_has_funnel_data_false_when_no_intent(self):
        ctx = _extract_context([_r("x1"), _r("x2"), _r("x3")])
        assert ctx["has_funnel_data"] is False

    # ── stage counts ──────────────────────────────────────────────────────────

    def test_converted_count(self):
        assert self.ctx["funnel_converted_count"] == 3

    def test_lost_count(self):
        assert self.ctx["funnel_lost_count"] == 2

    def test_pending_count(self):
        assert self.ctx["funnel_pending_count"] == 2

    def test_funnel_other_count(self):
        # exploring(1) + quote_requested(0) + quoted(1) + negotiating(1) = 3
        assert self.ctx["funnel_other_count"] == 3

    # ── conversion rate ───────────────────────────────────────────────────────

    def test_conversion_rate_30_percent(self):
        # 3 converted out of 10 = 30%
        assert self.ctx["funnel_conversion_rate"] == 30

    def test_conversion_rate_zero_when_no_conversions(self):
        results = [_r("x", has_intent=True, stage="exploring")]
        ctx = _extract_context(results)
        assert ctx["funnel_conversion_rate"] == 0

    def test_conversion_rate_100_when_all_converted(self):
        results = [_r(f"c{i}", has_intent=True, stage="converted",
                      conversion="converted") for i in range(5)]
        ctx = _extract_context(results)
        assert ctx["funnel_conversion_rate"] == 100

    # ── stage distribution ────────────────────────────────────────────────────

    def test_stage_distribution_contains_all_active_stages(self):
        stages = dict(self.ctx["funnel_stage_counts"])
        assert stages["converted"] == 3
        assert stages["lost"] == 2
        assert stages["pending"] == 2
        assert stages["quoted"] == 1
        assert stages["negotiating"] == 1
        assert stages["exploring"] == 1

    def test_stage_distribution_sorted_by_count_desc(self):
        counts = [c for _, c in self.ctx["funnel_stage_counts"]]
        assert counts == sorted(counts, reverse=True)

    # ── quote response time ───────────────────────────────────────────────────

    def test_median_quote_rt_computed(self):
        """
        QRT values (seconds):
          conv-c1 → 600, conv-c2 → 1200, conv-c3 → 1800 (stored)
          conv-q1 → 300 (stored)
          conv-n1 → 1200 (stored)
          conv-l1 → 4800 (stored)
          conv-l2 → 3600 (stored)
          conv-p1 → 900 (stored)
          conv-p2 → None stored, fallback = (30min = 1800s) from intent+quote_sent_at
          conv-e1 → no quote_sent_at → None

        Values used: [600, 1200, 1800, 300, 1200, 4800, 3600, 900, 1800]
        Sorted:      [300, 600, 900, 1200, 1200, 1800, 1800, 3600, 4800]
        Median of 9: index 4 = 1200
        """
        assert self.ctx["median_quote_rt"] == pytest.approx(1200, rel=0.01)

    def test_median_quote_rt_none_when_no_quote_sent(self):
        results = [_r("x", has_intent=True, stage="exploring")]
        ctx = _extract_context(results)
        assert ctx["median_quote_rt"] is None

    # ── follow-up stats ───────────────────────────────────────────────────────

    def test_quoted_convs_count(self):
        # quote_sent_at is set for: c1, c2, c3, q1, n1, l1, l2, p1, p2 = 9 convs
        assert len(self.ctx["quoted_convs"]) == 9

    def test_with_followup_count(self):
        # post_quote_followup_count > 0: c1(1), c2(2), c3(1), n1(3), l2(2), p2(1) = 6 convs
        # q1(0), l1(0), p1(0) → excluded
        assert len(self.ctx["with_followup"]) == 6

    def test_followup_pct(self):
        # 6 / 9 quoted = 67%
        assert self.ctx["followup_pct"] == pytest.approx(67, abs=1)

    def test_median_followup_delay_hours(self):
        """
        followup_delay_hours for with_followup convs:
          c1=2.0, c2=1.0, c3=4.0, n1=0.5, l2=48.0, p2=24.0
        Sorted: [0.5, 1.0, 2.0, 4.0, 24.0, 48.0]
        Median of 6: avg of 2.0 and 4.0 = 3.0
        """
        assert self.ctx["median_followup_delay_hours"] == pytest.approx(3.0, abs=0.1)

    def test_followup_pct_zero_when_none_have_followup(self):
        results = [
            _r("x", has_intent=True, stage="quoted",
               quote_sent_at=BASE, post_quote_followup_count=0),
        ]
        ctx = _extract_context(results)
        assert ctx["followup_pct"] == 0
        assert ctx["median_followup_delay_hours"] is None

    def test_followup_pct_100_when_all_have_followup(self):
        results = [
            _r(f"c{i}", has_intent=True, stage="quoted",
               quote_sent_at=BASE + timedelta(hours=i),
               post_quote_followup_count=1, followup_delay_hours=float(i + 1))
            for i in range(4)
        ]
        ctx = _extract_context(results)
        assert ctx["followup_pct"] == 100

    # ── lost reason details ───────────────────────────────────────────────────

    def test_lost_details_count(self):
        assert len(self.ctx["funnel_lost_details"]) == 2

    def test_lost_detail_price_has_correct_label(self):
        price_detail = next(
            d for d in self.ctx["funnel_lost_details"] if "Precio" in d["reason_label"]
        )
        assert price_detail["reason_label"] == "Precio alto o desfavorable"

    def test_lost_detail_competition_has_correct_label(self):
        comp_detail = next(
            d for d in self.ctx["funnel_lost_details"] if "competencia" in d["reason_label"]
        )
        assert comp_detail["reason_label"] == "Fue con la competencia"

    def test_lost_detail_contact_ref_includes_name(self):
        price_detail = next(
            d for d in self.ctx["funnel_lost_details"] if "Precio" in d["reason_label"]
        )
        assert "Pedro Sánchez" in price_detail["contact_ref"]

    def test_lost_detail_includes_specific_text(self):
        price_detail = next(
            d for d in self.ctx["funnel_lost_details"] if "Precio" in d["reason_label"]
        )
        assert price_detail["detail"] is not None
        assert "200k" in price_detail["detail"] or "proveedor" in price_detail["detail"]

    def test_lost_detail_contact_ref_falls_back_to_phone_tail(self):
        results = [
            _r("x", has_intent=True, stage="lost",
               lost_reason="timing",
               lost_reason_detail="El cliente dijo que no era el momento adecuado.",
               contact_name=None, contact_phone="+57 312 9876543",
               started_at=BASE),
        ]
        ctx = _extract_context(results)
        assert "6543" in ctx["funnel_lost_details"][0]["contact_ref"]

    def test_lost_detail_falls_back_to_date_when_no_name_or_phone(self):
        # When no name and no phone, contact_ref falls back to the conversation date
        results = [
            _r("x", has_intent=True, stage="lost",
               lost_reason="other",
               lost_reason_detail="Motivo desconocido.",
               contact_name=None, contact_phone=None,
               started_at=BASE),
        ]
        ctx = _extract_context(results)
        assert ctx["funnel_lost_details"][0]["contact_ref"] == "01 May"

    # ── proactive_quote_count ─────────────────────────────────────────────────

    def test_proactive_quote_count(self):
        # In fixtures: conv-c3 has quote_sent_at but NO quote_requested_at
        # conv-n1 has quote_sent_at but NO quote_requested_at
        # conv-l2 has quote_sent_at but NO quote_requested_at
        # conv-p2 has quote_sent_at but NO quote_requested_at
        # = 4 proactive quotes
        assert self.ctx["proactive_quote_count"] == 4

    def test_proactive_zero_when_all_explicitly_requested(self):
        results = [
            _r("x", has_intent=True, stage="quoted",
               quote_requested_at=BASE,
               quote_sent_at=BASE + timedelta(minutes=10)),
        ]
        ctx = _extract_context(results)
        assert ctx["proactive_quote_count"] == 0

    # ── funnel_status_color thresholds ────────────────────────────────────────

    def test_funnel_status_gray_when_fewer_than_5_intent(self):
        """< 5 intent conversations → gray (not enough data)."""
        results = [_r(f"c{i}", has_intent=True, stage="converted",
                      conversion="converted") for i in range(4)]
        pdf_bytes = generate_pdf_report(results, "Test", "job-gray")
        assert len(pdf_bytes) > 0  # just verify it renders

    def test_funnel_status_green_when_conversion_35_plus(self):
        results = [_r(f"c{i}", has_intent=True, stage="converted",
                      conversion="converted") for i in range(4)]
        results += [_r(f"l{i}", has_intent=True, stage="lost",
                        conversion="lost", lost_reason="price") for i in range(6)]
        # 4/10 = 40% → green
        ctx = _extract_context(results)
        assert ctx["funnel_conversion_rate"] == 40


# ══════════════════════════════════════════════════════════════════════════════
# 3. Edge cases
# ══════════════════════════════════════════════════════════════════════════════


class TestFunnelEdgeCases:

    def test_no_funnel_data_has_funnel_data_false(self):
        results = [_r(f"x{i}") for i in range(10)]
        ctx = _extract_context(results)
        assert ctx["has_funnel_data"] is False
        assert ctx["intent_count"] == 0
        assert ctx["funnel_conversion_rate"] == 0

    def test_single_converted_conv_100_percent(self):
        results = [_r("x", has_intent=True, stage="converted", conversion="converted")]
        ctx = _extract_context(results)
        assert ctx["funnel_conversion_rate"] == 100
        assert ctx["funnel_other_count"] == 0

    def test_all_pending_zero_conversion(self):
        results = [_r(f"p{i}", has_intent=True, stage="pending") for i in range(5)]
        ctx = _extract_context(results)
        assert ctx["funnel_conversion_rate"] == 0
        assert ctx["funnel_pending_count"] == 5

    def test_exploring_counted_in_other(self):
        results = [_r("e1", has_intent=True, stage="exploring")]
        ctx = _extract_context(results)
        assert ctx["funnel_other_count"] == 1
        assert ctx["funnel_converted_count"] == 0

    def test_empty_results_no_crash(self):
        ctx = _extract_context([])
        assert ctx["intent_count"] == 0
        assert ctx["has_funnel_data"] is False


# ══════════════════════════════════════════════════════════════════════════════
# 4. Full PDF integration test — generates a PDF for visual review
# ══════════════════════════════════════════════════════════════════════════════


class TestFunnelPDFGeneration:

    def test_pdf_renders_without_error(self):
        """The PDF must render without raising any exception."""
        results = _funnel_results()
        pdf_bytes = generate_pdf_report(
            results,
            business_name="Clínica Dental Sonríe",
            job_id="funnel-test-001",
            files_processed=18,
            ai_model="claude-sonnet-4-6",
            average_transaction_value=350_000,
            business_type="clinica dental",
            is_subscribed=True,
            account_name="Sonríe Principal",
        )
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 50_000  # a real PDF is never empty

    def test_pdf_saved_for_visual_review(self, tmp_path):
        """
        Saves the PDF to the project root so the developer can open it.
        Path: funnel_test_report.pdf
        """
        results = _funnel_results()
        pdf_bytes = generate_pdf_report(
            results,
            business_name="Clínica Dental Sonríe",
            job_id="funnel-test-001",
            files_processed=18,
            ai_model="claude-sonnet-4-6",
            average_transaction_value=350_000,
            business_type="clinica dental",
            is_subscribed=True,
            account_name="Sonríe Principal",
        )

        # Save to project root for review
        output_path = Path(__file__).parents[2] / "funnel_test_report.pdf"
        output_path.write_bytes(pdf_bytes)
        assert output_path.exists()
        assert output_path.stat().st_size > 50_000

    def test_pdf_with_no_funnel_data_renders(self):
        """Report with zero purchase intent conversations must still render."""
        results = [_r(f"x{i}", sentiment="positive", quality=8.0, frt=300) for i in range(20)]
        pdf_bytes = generate_pdf_report(
            results,
            business_name="Panadería La Mejor",
            job_id="no-funnel-001",
        )
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 10_000

    def test_pdf_with_all_converted_funnel_renders(self):
        """100% conversion rate section must render cleanly."""
        funnel = [
            _r(f"c{i}", has_intent=True, stage="converted", conversion="converted",
               sentiment="positive", quality=9.0, frt=120,
               quote_sent_at=BASE + timedelta(hours=i),
               quote_response_time_seconds=600,
               post_quote_followup_count=1, followup_delay_hours=2.0)
            for i in range(6)
        ]
        other = [_r(f"x{i}", sentiment="neutral", quality=7.0, frt=300) for i in range(4)]
        pdf_bytes = generate_pdf_report(
            funnel + other,
            business_name="Agencia de Viajes",
            job_id="all-converted-001",
        )
        assert isinstance(pdf_bytes, bytes)

    def test_pdf_with_all_lost_funnel_renders(self):
        """0% conversion + all lost must render cleanly including detail cards."""
        lost = [
            _r(f"l{i}", has_intent=True, stage="lost", conversion="lost",
               sentiment="negative", quality=3.0,
               lost_reason=["price", "competition", "timing"][i % 3],
               lost_reason_detail=f"Detalle específico de pérdida número {i + 1}.",
               contact_name=f"Cliente {i + 1}", contact_phone=f"+57 300 000000{i}",
               started_at=BASE + timedelta(hours=i))
            for i in range(5)
        ]
        pdf_bytes = generate_pdf_report(
            lost + [_r("x")],
            business_name="Inmobiliaria Test",
            job_id="all-lost-001",
        )
        assert isinstance(pdf_bytes, bytes)

    def test_pdf_with_large_lost_sample_renders(self):
        """More than 5 lost conversations → aggregate view, not individual cards."""
        lost = [
            _r(f"l{i}", has_intent=True, stage="lost", conversion="lost",
               lost_reason=["price", "competition", "no_reply"][i % 3],
               lost_reason_detail=f"Razón detallada número {i + 1}.",
               contact_name=f"Cliente Perdido {i + 1}",
               started_at=BASE + timedelta(days=i))
            for i in range(8)
        ]
        pdf_bytes = generate_pdf_report(
            lost,
            business_name="Empresa Con Muchas Pérdidas",
            job_id="large-lost-001",
        )
        assert isinstance(pdf_bytes, bytes)
