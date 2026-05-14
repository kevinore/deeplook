"""
Comprehensive tests for the commercial funnel — detect_funnel_signals() and finalize_funnel().

Covers:
  • detect_funnel_signals: media types, price patterns, inbound exclusion, offset calc
  • finalize_funnel: all 4 quote_sent_at resolution layers, quote_response_time, followups,
    timestamp conversion, edge cases (empty conv, negative delta, no signals, proactive)
"""
from datetime import datetime, timedelta

import pytest

from app.analytics.metrics.funnel import detect_funnel_signals, finalize_funnel
from app.models.enums import MessageDirection, MessageType
from app.models.normalized import NormalizedConversation, NormalizedMessage


# ─── helpers ─────────────────────────────────────────────────────────────────


def _msg(
    direction: MessageDirection,
    offset_minutes: float = 0,
    msg_type: MessageType = MessageType.TEXT,
    text: str | None = None,
    base: datetime | None = None,
) -> NormalizedMessage:
    base = base or datetime(2025, 6, 1, 10, 0, 0)
    return NormalizedMessage(
        timestamp=base + timedelta(minutes=offset_minutes),
        direction=direction,
        message_type=msg_type,
        text_content=text,
    )


IN = MessageDirection.INBOUND
OUT = MessageDirection.OUTBOUND
BASE = datetime(2025, 6, 1, 10, 0, 0)


def _conv(*messages: NormalizedMessage) -> NormalizedConversation:
    return NormalizedConversation(contact_phone="+57 300 0000000", messages=list(messages), source="waha")


# ══════════════════════════════════════════════════════════════════════════════
# detect_funnel_signals
# ══════════════════════════════════════════════════════════════════════════════


class TestDetectFunnelSignals:

    def test_empty_conversation_returns_none_conv_start(self):
        signals = detect_funnel_signals(_conv())
        assert signals["conv_start"] is None
        assert signals["outbound_media_events"] == []
        assert signals["outbound_price_events"] == []

    def test_text_only_outbound_produces_no_signals(self):
        conv = _conv(
            _msg(IN, 0, text="necesito cotizar"),
            _msg(OUT, 5, text="hola, bienvenido"),
        )
        signals = detect_funnel_signals(conv)
        assert signals["outbound_media_events"] == []
        assert signals["outbound_price_events"] == []

    def test_outbound_document_detected(self):
        conv = _conv(
            _msg(IN, 0, text="me manda la propuesta"),
            _msg(OUT, 10, msg_type=MessageType.DOCUMENT),
        )
        signals = detect_funnel_signals(conv)
        assert len(signals["outbound_media_events"]) == 1
        assert signals["outbound_media_events"][0]["type"] == "document"

    def test_outbound_image_detected(self):
        conv = _conv(
            _msg(IN, 0, text="foto del producto"),
            _msg(OUT, 5, msg_type=MessageType.IMAGE),
        )
        signals = detect_funnel_signals(conv)
        assert len(signals["outbound_media_events"]) == 1
        assert signals["outbound_media_events"][0]["type"] == "image"

    def test_outbound_audio_detected(self):
        conv = _conv(
            _msg(IN, 0),
            _msg(OUT, 3, msg_type=MessageType.AUDIO),
        )
        signals = detect_funnel_signals(conv)
        assert len(signals["outbound_media_events"]) == 1
        assert signals["outbound_media_events"][0]["type"] == "audio"

    def test_inbound_media_not_detected(self):
        """Client sends a document — should NOT appear in outbound_media_events."""
        conv = _conv(
            _msg(IN, 0, msg_type=MessageType.DOCUMENT),
            _msg(OUT, 5, text="gracias"),
        )
        signals = detect_funnel_signals(conv)
        assert signals["outbound_media_events"] == []

    def test_multiple_outbound_media_all_captured(self):
        conv = _conv(
            _msg(IN, 0),
            _msg(OUT, 5, msg_type=MessageType.IMAGE),
            _msg(OUT, 10, msg_type=MessageType.DOCUMENT),
            _msg(OUT, 15, msg_type=MessageType.AUDIO),
        )
        signals = detect_funnel_signals(conv)
        assert len(signals["outbound_media_events"]) == 3

    def test_price_pattern_peso_with_periods(self):
        """$1.500.000 format."""
        conv = _conv(
            _msg(IN, 0),
            _msg(OUT, 5, text="El precio es $1.500.000 con envío incluido"),
        )
        signals = detect_funnel_signals(conv)
        assert len(signals["outbound_price_events"]) == 1

    def test_price_pattern_mil_pesos(self):
        """150 mil pesos format."""
        conv = _conv(
            _msg(IN, 0),
            _msg(OUT, 5, text="son 150 mil pesos por unidad"),
        )
        signals = detect_funnel_signals(conv)
        assert len(signals["outbound_price_events"]) == 1

    def test_price_pattern_precio_colon(self):
        """precio: $X format."""
        conv = _conv(
            _msg(IN, 0),
            _msg(OUT, 5, text="precio: $450.000"),
        )
        signals = detect_funnel_signals(conv)
        assert len(signals["outbound_price_events"]) == 1

    def test_price_pattern_son_x(self):
        """'son $X' format."""
        conv = _conv(
            _msg(IN, 0),
            _msg(OUT, 5, text="son $80.000 en efectivo"),
        )
        signals = detect_funnel_signals(conv)
        assert len(signals["outbound_price_events"]) == 1

    def test_price_pattern_cotizacion_adjunta(self):
        conv = _conv(
            _msg(IN, 0),
            _msg(OUT, 5, text="cotización adjunta, revisala"),
        )
        signals = detect_funnel_signals(conv)
        assert len(signals["outbound_price_events"]) == 1

    def test_price_pattern_millones(self):
        conv = _conv(
            _msg(IN, 0),
            _msg(OUT, 5, text="El valor es 2 millones de pesos"),
        )
        signals = detect_funnel_signals(conv)
        assert len(signals["outbound_price_events"]) == 1

    def test_price_pattern_cuesta(self):
        conv = _conv(
            _msg(IN, 0),
            _msg(OUT, 5, text="cuesta $120.000"),
        )
        signals = detect_funnel_signals(conv)
        assert len(signals["outbound_price_events"]) == 1

    def test_inbound_price_text_not_detected(self):
        """Client mentions price — should NOT go into outbound_price_events."""
        conv = _conv(
            _msg(IN, 0, text="¿cuánto cuesta? vi $200.000 en otro lado"),
            _msg(OUT, 5, text="sí correcto"),
        )
        signals = detect_funnel_signals(conv)
        assert signals["outbound_price_events"] == []

    def test_offset_seconds_computed_from_conv_start(self):
        """Offset must be relative to the first message timestamp."""
        base = datetime(2025, 6, 1, 9, 0, 0)
        conv = _conv(
            NormalizedMessage(timestamp=base, direction=IN, message_type=MessageType.TEXT),
            NormalizedMessage(
                timestamp=base + timedelta(minutes=90),
                direction=OUT,
                message_type=MessageType.DOCUMENT,
            ),
        )
        signals = detect_funnel_signals(conv)
        ev = signals["outbound_media_events"][0]
        assert ev["offset_s"] == 90 * 60  # 5400 seconds
        assert ev["timestamp"] == base + timedelta(minutes=90)

    def test_conv_start_is_first_message_timestamp(self):
        base = datetime(2025, 3, 15, 14, 30, 0)
        conv = _conv(
            NormalizedMessage(timestamp=base, direction=IN, message_type=MessageType.TEXT),
            NormalizedMessage(timestamp=base + timedelta(minutes=5), direction=OUT, message_type=MessageType.TEXT),
        )
        assert detect_funnel_signals(conv)["conv_start"] == base

    def test_media_and_price_in_same_conversation(self):
        conv = _conv(
            _msg(IN, 0),
            _msg(OUT, 5, msg_type=MessageType.IMAGE),
            _msg(OUT, 10, text="precio: $300.000"),
        )
        signals = detect_funnel_signals(conv)
        assert len(signals["outbound_media_events"]) == 1
        assert len(signals["outbound_price_events"]) == 1

    def test_outbound_only_conversation_no_inbound(self):
        """Business initiated with no client reply — still valid signals."""
        conv = _conv(
            _msg(OUT, 0, msg_type=MessageType.DOCUMENT),
            _msg(OUT, 5, text="cuesta $200.000"),
        )
        signals = detect_funnel_signals(conv)
        assert len(signals["outbound_media_events"]) == 1
        assert len(signals["outbound_price_events"]) == 1


# ══════════════════════════════════════════════════════════════════════════════
# finalize_funnel
# ══════════════════════════════════════════════════════════════════════════════


def _signals(
    conv_start: datetime,
    media_offsets: list[int] | None = None,
    price_offsets: list[int] | None = None,
) -> dict:
    """Build a funnel_signals dict with typed events."""
    media_events = [
        {"timestamp": conv_start + timedelta(seconds=s), "offset_s": s, "type": "document"}
        for s in (media_offsets or [])
    ]
    price_events = [
        {
            "timestamp": conv_start + timedelta(seconds=s),
            "offset_s": s,
            "snippet": f"precio: $100.000 (offset {s})",
        }
        for s in (price_offsets or [])
    ]
    return {
        "conv_start": conv_start,
        "outbound_media_events": media_events,
        "outbound_price_events": price_events,
    }


def _msgs_from_offsets(
    conv_start: datetime,
    items: list[tuple[MessageDirection, int]],
) -> list[NormalizedMessage]:
    return [
        NormalizedMessage(
            timestamp=conv_start + timedelta(seconds=s),
            direction=d,
            message_type=MessageType.TEXT,
        )
        for d, s in items
    ]


class TestFinalizeFunnel:

    def test_empty_signals_returns_empty_funnel(self):
        result = finalize_funnel(
            funnel_signals={"conv_start": None, "outbound_media_events": [], "outbound_price_events": []},
            msgs=[],
            ai_intent_offset_s=None,
            ai_quote_requested_offset_s=None,
            ai_has_purchase_intent=False,
            ai_intent_stage="none",
            ai_is_ghosted=False,
        )
        for key in ("intent_first_at", "quote_requested_at", "quote_sent_at",
                    "quote_response_time_seconds", "post_quote_followup_count",
                    "followup_delay_hours"):
            assert result[key] is None

    def test_intent_offset_converts_to_timestamp(self):
        base = datetime(2025, 6, 1, 10, 0, 0)
        result = finalize_funnel(
            funnel_signals=_signals(base),
            msgs=[],
            ai_intent_offset_s=3600,  # 1 hour from start
            ai_quote_requested_offset_s=None,
            ai_has_purchase_intent=True,
            ai_intent_stage="exploring",
            ai_is_ghosted=False,
        )
        assert result["intent_first_at"] == base + timedelta(hours=1)

    def test_quote_requested_offset_converts_to_timestamp(self):
        base = datetime(2025, 6, 1, 10, 0, 0)
        result = finalize_funnel(
            funnel_signals=_signals(base),
            msgs=[],
            ai_intent_offset_s=0,
            ai_quote_requested_offset_s=1800,  # 30 min
            ai_has_purchase_intent=True,
            ai_intent_stage="quote_requested",
            ai_is_ghosted=False,
        )
        assert result["quote_requested_at"] == base + timedelta(minutes=30)

    def test_negative_intent_offset_returns_none(self):
        base = datetime(2025, 6, 1, 10, 0, 0)
        result = finalize_funnel(
            funnel_signals=_signals(base),
            msgs=[],
            ai_intent_offset_s=-100,
            ai_quote_requested_offset_s=None,
            ai_has_purchase_intent=True,
            ai_intent_stage="exploring",
            ai_is_ghosted=False,
        )
        assert result["intent_first_at"] is None

    # ── Layer 1: first outbound media AFTER quote_requested_at ───────────────

    def test_layer1_media_after_quote_requested(self):
        """Document arrives after explicit quote request → quote_sent_at = that media ts."""
        base = datetime(2025, 6, 1, 10, 0, 0)
        quote_req_offset = 300   # 5 min
        media_offset = 600       # 10 min (after request)
        result = finalize_funnel(
            funnel_signals=_signals(base, media_offsets=[media_offset]),
            msgs=[],
            ai_intent_offset_s=0,
            ai_quote_requested_offset_s=quote_req_offset,
            ai_has_purchase_intent=True,
            ai_intent_stage="quoted",
            ai_is_ghosted=False,
        )
        assert result["quote_sent_at"] == base + timedelta(seconds=media_offset)

    def test_layer1_media_before_anchor_not_used(self):
        """Media that arrived BEFORE quote_requested_at must be ignored."""
        base = datetime(2025, 6, 1, 10, 0, 0)
        result = finalize_funnel(
            funnel_signals=_signals(base, media_offsets=[100]),  # media at 100s
            msgs=[],
            ai_intent_offset_s=0,
            ai_quote_requested_offset_s=300,  # quote requested at 300s
            ai_has_purchase_intent=True,
            ai_intent_stage="quoted",
            ai_is_ghosted=False,
        )
        # No media after anchor — quote_sent_at must be None
        assert result["quote_sent_at"] is None

    def test_layer1_picks_first_media_after_anchor(self):
        """Multiple media events → pick the earliest one after anchor."""
        base = datetime(2025, 6, 1, 10, 0, 0)
        result = finalize_funnel(
            funnel_signals=_signals(base, media_offsets=[100, 400, 700]),
            msgs=[],
            ai_intent_offset_s=0,
            ai_quote_requested_offset_s=300,  # anchor at 300s
            ai_has_purchase_intent=True,
            ai_intent_stage="quoted",
            ai_is_ghosted=False,
        )
        # 100 < anchor → skip; 400 > anchor → first valid
        assert result["quote_sent_at"] == base + timedelta(seconds=400)

    # ── Layer 2: first outbound media after intent (no explicit quote request) ─

    def test_layer2_media_after_intent_when_no_quote_requested(self):
        """No explicit quote request but intent is known → use intent as anchor."""
        base = datetime(2025, 6, 1, 10, 0, 0)
        result = finalize_funnel(
            funnel_signals=_signals(base, media_offsets=[1000]),
            msgs=[],
            ai_intent_offset_s=500,       # intent at 500s
            ai_quote_requested_offset_s=None,
            ai_has_purchase_intent=True,
            ai_intent_stage="quoted",
            ai_is_ghosted=False,
        )
        assert result["quote_sent_at"] == base + timedelta(seconds=1000)

    # ── Layer 3: price text after anchor ─────────────────────────────────────

    def test_layer3_price_text_after_anchor_when_no_media(self):
        """No media events but outbound price text after anchor → quote_sent_at."""
        base = datetime(2025, 6, 1, 10, 0, 0)
        result = finalize_funnel(
            funnel_signals=_signals(base, media_offsets=[], price_offsets=[800]),
            msgs=[],
            ai_intent_offset_s=200,
            ai_quote_requested_offset_s=None,
            ai_has_purchase_intent=True,
            ai_intent_stage="quoted",
            ai_is_ghosted=False,
        )
        assert result["quote_sent_at"] == base + timedelta(seconds=800)

    def test_layer3_price_text_before_anchor_not_used(self):
        base = datetime(2025, 6, 1, 10, 0, 0)
        result = finalize_funnel(
            funnel_signals=_signals(base, price_offsets=[100]),
            msgs=[],
            ai_intent_offset_s=0,
            ai_quote_requested_offset_s=300,
            ai_has_purchase_intent=True,
            ai_intent_stage="quoted",
            ai_is_ghosted=False,
        )
        assert result["quote_sent_at"] is None

    def test_layer1_takes_priority_over_layer3(self):
        """If both media and price text exist after anchor, media wins."""
        base = datetime(2025, 6, 1, 10, 0, 0)
        result = finalize_funnel(
            funnel_signals=_signals(base, media_offsets=[500], price_offsets=[400]),
            msgs=[],
            ai_intent_offset_s=0,
            ai_quote_requested_offset_s=300,
            ai_has_purchase_intent=True,
            ai_intent_stage="quoted",
            ai_is_ghosted=False,
        )
        # Both 400 and 500 are > anchor=300; media (500) should win over price text (400)
        # Layer 1 runs first → picks media at 500
        assert result["quote_sent_at"] == base + timedelta(seconds=500)

    # ── Proactive (no anchor at all) ─────────────────────────────────────────

    def test_proactive_media_used_when_no_anchor(self):
        """No intent offset, no quote_requested → proactive: take first media."""
        base = datetime(2025, 6, 1, 10, 0, 0)
        result = finalize_funnel(
            funnel_signals=_signals(base, media_offsets=[200, 500]),
            msgs=[],
            ai_intent_offset_s=None,
            ai_quote_requested_offset_s=None,
            ai_has_purchase_intent=True,
            ai_intent_stage="quoted",
            ai_is_ghosted=False,
        )
        assert result["quote_sent_at"] == base + timedelta(seconds=200)

    def test_proactive_price_text_used_when_no_media_and_no_anchor(self):
        base = datetime(2025, 6, 1, 10, 0, 0)
        result = finalize_funnel(
            funnel_signals=_signals(base, price_offsets=[300]),
            msgs=[],
            ai_intent_offset_s=None,
            ai_quote_requested_offset_s=None,
            ai_has_purchase_intent=True,
            ai_intent_stage="quoted",
            ai_is_ghosted=False,
        )
        assert result["quote_sent_at"] == base + timedelta(seconds=300)

    def test_proactive_not_triggered_when_has_purchase_intent_false(self):
        """Without intent, no proactive quote assignment."""
        base = datetime(2025, 6, 1, 10, 0, 0)
        result = finalize_funnel(
            funnel_signals=_signals(base, media_offsets=[200]),
            msgs=[],
            ai_intent_offset_s=None,
            ai_quote_requested_offset_s=None,
            ai_has_purchase_intent=False,
            ai_intent_stage="none",
            ai_is_ghosted=False,
        )
        assert result["quote_sent_at"] is None

    # ── quote_response_time_seconds ──────────────────────────────────────────

    def test_qrt_computed_from_explicit_quote_requested(self):
        """quote_response_time = quote_sent_at − quote_requested_at."""
        base = datetime(2025, 6, 1, 10, 0, 0)
        # quote requested at 300s, media (=quote sent) at 900s → delta = 600s
        result = finalize_funnel(
            funnel_signals=_signals(base, media_offsets=[900]),
            msgs=[],
            ai_intent_offset_s=0,
            ai_quote_requested_offset_s=300,
            ai_has_purchase_intent=True,
            ai_intent_stage="quoted",
            ai_is_ghosted=False,
        )
        assert result["quote_response_time_seconds"] == 600

    def test_qrt_falls_back_to_intent_when_no_explicit_request(self):
        """No explicit quote request → QRT = quote_sent_at − intent_first_at."""
        base = datetime(2025, 6, 1, 10, 0, 0)
        # intent at 0s, media at 5116s (85 min, like Maria's case)
        result = finalize_funnel(
            funnel_signals=_signals(base, media_offsets=[5116]),
            msgs=[],
            ai_intent_offset_s=0,
            ai_quote_requested_offset_s=None,
            ai_has_purchase_intent=True,
            ai_intent_stage="quoted",
            ai_is_ghosted=False,
        )
        assert result["quote_response_time_seconds"] == 5116

    def test_qrt_none_when_quote_not_sent(self):
        base = datetime(2025, 6, 1, 10, 0, 0)
        result = finalize_funnel(
            funnel_signals=_signals(base),  # no media, no price
            msgs=[],
            ai_intent_offset_s=0,
            ai_quote_requested_offset_s=300,
            ai_has_purchase_intent=True,
            ai_intent_stage="quote_requested",
            ai_is_ghosted=False,
        )
        assert result["quote_sent_at"] is None
        assert result["quote_response_time_seconds"] is None

    def test_qrt_none_when_negative_delta(self):
        """If quote_sent_at < reference → delta negative → QRT = None."""
        base = datetime(2025, 6, 1, 10, 0, 0)
        # intent at 1000s, but the only media event is at 500s (before intent)
        result = finalize_funnel(
            funnel_signals=_signals(base, media_offsets=[500]),
            msgs=[],
            ai_intent_offset_s=1000,
            ai_quote_requested_offset_s=None,
            ai_has_purchase_intent=True,
            ai_intent_stage="quoted",
            ai_is_ghosted=False,
        )
        # media at 500 < anchor at 1000 → layer 2 skips it → quote_sent_at = None
        assert result["quote_sent_at"] is None
        assert result["quote_response_time_seconds"] is None

    # ── post_quote_followup_count and followup_delay_hours ───────────────────

    def test_followup_count_after_quote_sent(self):
        """2 outbound messages after quote_sent_at → post_quote_followup_count = 2."""
        base = datetime(2025, 6, 1, 10, 0, 0)
        signals = _signals(base, media_offsets=[300])  # quote sent at 300s
        msgs = _msgs_from_offsets(base, [
            (IN, 0),
            (OUT, 300),  # quote (media, already in signals)
            (OUT, 600),  # followup 1
            (OUT, 900),  # followup 2
        ])
        result = finalize_funnel(
            funnel_signals=signals,
            msgs=msgs,
            ai_intent_offset_s=0,
            ai_quote_requested_offset_s=None,
            ai_has_purchase_intent=True,
            ai_intent_stage="pending",
            ai_is_ghosted=False,
        )
        assert result["post_quote_followup_count"] == 2

    def test_followup_count_zero_when_no_followup(self):
        base = datetime(2025, 6, 1, 10, 0, 0)
        signals = _signals(base, media_offsets=[300])
        msgs = _msgs_from_offsets(base, [(IN, 0), (OUT, 300)])
        result = finalize_funnel(
            funnel_signals=signals,
            msgs=msgs,
            ai_intent_offset_s=0,
            ai_quote_requested_offset_s=None,
            ai_has_purchase_intent=True,
            ai_intent_stage="pending",
            ai_is_ghosted=False,
        )
        assert result["post_quote_followup_count"] == 0
        assert result["followup_delay_hours"] is None

    def test_followup_delay_hours_computed_from_first_followup(self):
        """First followup 3h after quote_sent → followup_delay_hours ≈ 3.0."""
        base = datetime(2025, 6, 1, 10, 0, 0)
        quote_offset = 0
        followup_offset = 3 * 3600  # 3 hours later
        signals = _signals(base, media_offsets=[quote_offset])
        msgs = _msgs_from_offsets(base, [
            (OUT, quote_offset),
            (OUT, followup_offset),
        ])
        result = finalize_funnel(
            funnel_signals=signals,
            msgs=msgs,
            ai_intent_offset_s=None,
            ai_quote_requested_offset_s=None,
            ai_has_purchase_intent=True,
            ai_intent_stage="pending",
            ai_is_ghosted=False,
        )
        assert result["followup_delay_hours"] == pytest.approx(3.0, abs=0.01)

    def test_followup_count_none_when_quote_not_sent(self):
        base = datetime(2025, 6, 1, 10, 0, 0)
        signals = _signals(base)  # no quote
        msgs = _msgs_from_offsets(base, [(IN, 0)])
        result = finalize_funnel(
            funnel_signals=signals,
            msgs=msgs,
            ai_intent_offset_s=0,
            ai_quote_requested_offset_s=None,
            ai_has_purchase_intent=True,
            ai_intent_stage="exploring",
            ai_is_ghosted=False,
        )
        assert result["post_quote_followup_count"] is None

    def test_inbound_messages_not_counted_as_followup(self):
        """Only OUTBOUND messages after quote_sent count as follow-ups."""
        base = datetime(2025, 6, 1, 10, 0, 0)
        signals = _signals(base, media_offsets=[300])
        msgs = _msgs_from_offsets(base, [
            (IN, 0),
            (OUT, 300),
            (IN, 400),   # inbound after quote — does NOT count
            (IN, 500),
            (OUT, 600),  # this is a followup
        ])
        result = finalize_funnel(
            funnel_signals=signals,
            msgs=msgs,
            ai_intent_offset_s=0,
            ai_quote_requested_offset_s=None,
            ai_has_purchase_intent=True,
            ai_intent_stage="pending",
            ai_is_ghosted=False,
        )
        assert result["post_quote_followup_count"] == 1

    def test_conv_start_fallback_to_first_message_when_signals_empty(self):
        """If funnel_signals has no conv_start but messages exist, use first message ts."""
        base = datetime(2025, 6, 1, 10, 0, 0)
        signals = {"conv_start": None, "outbound_media_events": [], "outbound_price_events": []}
        msgs = _msgs_from_offsets(base, [(IN, 0)])
        result = finalize_funnel(
            funnel_signals=signals,
            msgs=msgs,
            ai_intent_offset_s=0,
            ai_quote_requested_offset_s=None,
            ai_has_purchase_intent=True,
            ai_intent_stage="exploring",
            ai_is_ghosted=False,
        )
        # Should not raise — intent_first_at = first msg ts + offset 0 = base
        assert result["intent_first_at"] == base
