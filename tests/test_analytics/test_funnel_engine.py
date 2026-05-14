"""
Comprehensive tests for the commercial funnel cross-validation in AnalyticsEngine.

Tests the interaction between the main AI analysis and the funnel AI call:
  • Outbound-only conversations skip funnel entirely
  • Operational tasks (QR scan, task coordination) are NOT marked as purchase intent
  • conversion_status=converted is only propagated to the funnel when funnel confirms commercial intent
  • Active funnel stages force has_purchase_intent=True
  • Ghosted + no followup + no lost_reason → forced to pending, not lost
  • Funnel AI failure → safe empty defaults, no crash
  • Funnel tokens/cost are accumulated to the total

Uses ControlledMockProvider to inject deterministic responses for both
the main analysis call and the funnel call independently.
"""
import json
from datetime import datetime, timedelta

import pytest

from app.analytics.ai.provider import AIProvider, AIResponse
from app.analytics.engine import AnalyticsEngine
from app.models.enums import MessageDirection, MessageType
from app.models.normalized import NormalizedConversation, NormalizedMessage


# ─── ControlledMockProvider ──────────────────────────────────────────────────


class ControlledMockProvider(AIProvider):
    """
    Returns specific JSON responses based on call order.
    First call → main_response, second call → funnel_response.
    If funnel_response is None, raises on second call (to simulate funnel AI failure).
    """

    def __init__(
        self,
        main_response: dict,
        funnel_response: dict | None = None,
        fail_on_funnel: bool = False,
    ):
        self._main = main_response
        self._funnel = funnel_response
        self._fail_on_funnel = fail_on_funnel
        self._calls: list[str] = []

    @property
    def provider_name(self) -> str:
        return "controlled"

    @property
    def model_name(self) -> str:
        return "controlled-v1"

    async def analyze(self, system_prompt: str, user_prompt: str, **kwargs) -> AIResponse:
        call_num = len(self._calls)
        self._calls.append(system_prompt[:30])

        # Detect funnel call by system prompt content
        is_funnel = "ventas y CRM" in system_prompt or "embudo" in system_prompt.lower()

        if is_funnel:
            if self._fail_on_funnel:
                raise RuntimeError("Simulated funnel AI failure")
            payload = self._funnel if self._funnel is not None else {}
        else:
            payload = self._main

        return AIResponse(
            content=json.dumps(payload),
            model="controlled-v1",
            provider="controlled",
            tokens_input=100,
            tokens_output=50,
            cost_usd=0.001,
        )

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return 0.0


# ─── Conversation builders ────────────────────────────────────────────────────


BASE = datetime(2025, 6, 1, 10, 0, 0)


def _msg(direction: str, offset_min: int, msg_type: MessageType = MessageType.TEXT,
         text: str = "msg") -> NormalizedMessage:
    return NormalizedMessage(
        timestamp=BASE + timedelta(minutes=offset_min),
        direction=MessageDirection(direction),
        message_type=msg_type,
        text_content=text,
    )


def _conv(*msgs: NormalizedMessage) -> NormalizedConversation:
    return NormalizedConversation(
        contact_phone="+57 300 0000000",
        contact_name="Test",
        messages=list(msgs),
        source="waha",
    )


def _main_ai(
    conversion_status: str = "not_applicable",
    sentiment: str = "neutral",
) -> dict:
    return {
        "sentiment": sentiment,
        "sentiment_score": 0.0,
        "sentiment_reason": "test",
        "primary_topic": "consulta",
        "secondary_topics": [],
        "quality_score": 7.0,
        "quality_breakdown": {"helpfulness": 7, "tone": 7, "completeness": 7},
        "conversion_status": conversion_status,
        "conversion_reason": "test" if conversion_status != "not_applicable" else None,
        "summary": "Test conversation.",
        "key_points": [],
        "customer_questions": [],
    }


def _funnel_ai(
    has_purchase_intent: bool = False,
    intent_stage: str = "none",
    intent_first_at_offset_seconds: int | None = None,
    quote_requested_at_offset_seconds: int | None = None,
    lost_reason: str | None = None,
    lost_reason_detail: str | None = None,
) -> dict:
    return {
        "has_purchase_intent": has_purchase_intent,
        "intent_stage": intent_stage,
        "intent_first_at_offset_seconds": intent_first_at_offset_seconds,
        "quote_requested_at_offset_seconds": quote_requested_at_offset_seconds,
        "lost_reason": lost_reason,
        "lost_reason_detail": lost_reason_detail,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Outbound-only: funnel must be skipped
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_outbound_only_conversation_skips_funnel():
    """Business initiated, no client reply → funnel not called, intent fields default."""
    provider = ControlledMockProvider(main_response=_main_ai())
    engine = AnalyticsEngine(ai_provider=provider)

    conv = _conv(_msg("outbound", 0))
    result = await engine.analyze_conversation(conv, "conv-out-only")

    assert result.has_purchase_intent is False
    assert result.intent_stage is None
    # Only one AI call made (no funnel call)
    funnel_calls = [c for c in provider._calls if "ventas" in c.lower() or len(provider._calls) > 0]
    assert len(provider._calls) == 1  # Only main analysis


@pytest.mark.asyncio
async def test_conversation_with_inbound_triggers_funnel():
    """Any conversation with inbound>0 must trigger the funnel AI call."""
    provider = ControlledMockProvider(
        main_response=_main_ai(),
        funnel_response=_funnel_ai(has_purchase_intent=False, intent_stage="none"),
    )
    engine = AnalyticsEngine(ai_provider=provider)
    conv = _conv(_msg("inbound", 0), _msg("outbound", 5))
    result = await engine.analyze_conversation(conv, "conv-with-inbound")

    # Two AI calls: main + funnel
    assert len(provider._calls) == 2
    assert result.has_purchase_intent is False


# ══════════════════════════════════════════════════════════════════════════════
# Operational task: NOT purchase intent, even if main says converted
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_operational_task_not_marked_as_purchase_intent():
    """
    Main analysis says converted (QR scan task completed), but funnel AI
    correctly says has_purchase_intent=False → cross-validation must NOT force intent.
    """
    provider = ControlledMockProvider(
        main_response=_main_ai(conversion_status="converted"),
        funnel_response=_funnel_ai(
            has_purchase_intent=False,
            intent_stage="none",
        ),
    )
    engine = AnalyticsEngine(ai_provider=provider)
    conv = _conv(
        _msg("outbound", 0, text="necesito que escanees este QR"),
        _msg("inbound", 60, text="claro, lo hago mañana"),
        _msg("inbound", 1440, text="listo, escaneé el código"),
    )
    result = await engine.analyze_conversation(conv, "conv-qr-scan")

    # Funnel said no intent → cross-validation must NOT force it
    assert result.has_purchase_intent is False
    assert result.intent_stage == "none"


@pytest.mark.asyncio
async def test_commercial_converted_forces_intent_stage():
    """
    Main analysis says converted + funnel confirms has_purchase_intent=True
    → cross-validation must force intent_stage='converted'.
    """
    provider = ControlledMockProvider(
        main_response=_main_ai(conversion_status="converted"),
        funnel_response=_funnel_ai(
            has_purchase_intent=True,
            intent_stage="quoted",  # AI said quoted but main says converted
            intent_first_at_offset_seconds=0,
        ),
    )
    engine = AnalyticsEngine(ai_provider=provider)
    conv = _conv(
        _msg("inbound", 0, text="quiero comprar el producto"),
        _msg("outbound", 5, text="$500.000, ¿te lo enviamos?"),
        _msg("inbound", 10, text="sí, me lo compro"),
    )
    result = await engine.analyze_conversation(conv, "conv-commercial-sale")

    assert result.intent_stage == "converted"
    assert result.has_purchase_intent is True


# ══════════════════════════════════════════════════════════════════════════════
# Active stages force has_purchase_intent=True
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["exploring", "quote_requested", "quoted", "negotiating", "converted", "lost"])
async def test_active_intent_stage_forces_has_purchase_intent(stage):
    """
    Any active funnel stage (not 'none') must produce has_purchase_intent=True.
    The parser enforces intent=True when stage is active, and the engine's
    cross-validation confirms it. Both paths tested here: send valid (consistent)
    AI response and verify the final result has intent=True.
    """
    extra = {"lost_reason": "price", "lost_reason_detail": "too expensive"} if stage == "lost" else {}
    provider = ControlledMockProvider(
        main_response=_main_ai(conversion_status="lost" if stage == "lost" else "pending"),
        funnel_response=_funnel_ai(
            has_purchase_intent=True,  # consistent with active stage
            intent_stage=stage,
            intent_first_at_offset_seconds=0,
            **extra,
        ),
    )
    engine = AnalyticsEngine(ai_provider=provider)
    conv = _conv(_msg("inbound", 0), _msg("outbound", 5))
    result = await engine.analyze_conversation(conv, f"conv-{stage}")

    assert result.has_purchase_intent is True, f"Stage {stage} should have intent=True"


# ══════════════════════════════════════════════════════════════════════════════
# Ghosted → pending override
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_ghosted_with_no_followup_lost_no_reason_forced_to_pending():
    """
    Ghost + quote_sent + 0 followups + stage=lost + no lost_reason
    → should be forced to 'pending' (we didn't earn the loss).
    """
    from app.models.enums import MessageType as MT

    base = datetime(2025, 6, 1, 10, 0, 0)
    provider = ControlledMockProvider(
        main_response=_main_ai(conversion_status="lost"),
        funnel_response=_funnel_ai(
            has_purchase_intent=True,
            intent_stage="lost",
            intent_first_at_offset_seconds=0,
            quote_requested_at_offset_seconds=None,
            lost_reason=None,          # no explicit reason
            lost_reason_detail=None,
        ),
    )
    engine = AnalyticsEngine(ai_provider=provider)

    # Build a ghosted conversation: business replied (READ ack) and client went silent
    from app.models.normalized import NormalizedMessage
    msgs = [
        NormalizedMessage(
            timestamp=base,
            direction=MessageDirection.INBOUND,
            message_type=MessageType.TEXT,
            text_content="me interesa el producto",
            ack=None,
        ),
        NormalizedMessage(
            timestamp=base + timedelta(minutes=5),
            direction=MessageDirection.OUTBOUND,
            message_type=MessageType.DOCUMENT,  # quote sent as document
            text_content=None,
            ack=3,  # READ
        ),
    ]
    conv = NormalizedConversation(
        contact_phone="+57 300 0000000",
        messages=msgs,
        source="waha",
    )
    result = await engine.analyze_conversation(conv, "conv-ghosted-no-reason")

    # The ghost rule should fire: lost + no reason + quote sent + 0 followup → pending
    assert result.intent_stage == "pending"


@pytest.mark.asyncio
async def test_ghosted_rule_skipped_when_lost_reason_is_set():
    """If lost_reason is explicitly set, the ghost override must NOT fire."""
    provider = ControlledMockProvider(
        main_response=_main_ai(conversion_status="lost"),
        funnel_response=_funnel_ai(
            has_purchase_intent=True,
            intent_stage="lost",
            intent_first_at_offset_seconds=0,
            lost_reason="price",
            lost_reason_detail="el cliente dijo que era muy caro",
        ),
    )
    engine = AnalyticsEngine(ai_provider=provider)

    from app.models.normalized import NormalizedMessage
    base = datetime(2025, 6, 1, 10, 0, 0)
    msgs = [
        NormalizedMessage(
            timestamp=base, direction=MessageDirection.INBOUND,
            message_type=MessageType.TEXT, ack=None, text_content="precio?",
        ),
        NormalizedMessage(
            timestamp=base + timedelta(minutes=5),
            direction=MessageDirection.OUTBOUND,
            message_type=MessageType.DOCUMENT,
            ack=3, text_content=None,
        ),
    ]
    conv = NormalizedConversation(contact_phone="+57 300 0000000", messages=msgs, source="waha")
    result = await engine.analyze_conversation(conv, "conv-real-lost")

    # lost_reason is set → stage stays lost
    assert result.intent_stage == "lost"
    assert result.lost_reason == "price"


# ══════════════════════════════════════════════════════════════════════════════
# Funnel AI failure → safe defaults, no crash
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_funnel_ai_failure_returns_empty_funnel_no_crash():
    """If the funnel AI call raises an exception, engine must not crash."""
    provider = ControlledMockProvider(
        main_response=_main_ai(),
        fail_on_funnel=True,
    )
    engine = AnalyticsEngine(ai_provider=provider)
    conv = _conv(_msg("inbound", 0), _msg("outbound", 5))
    result = await engine.analyze_conversation(conv, "conv-funnel-fails")

    # No crash, safe defaults
    assert result.has_purchase_intent is False
    assert result.intent_stage is None or result.intent_stage == "none"


# ══════════════════════════════════════════════════════════════════════════════
# Cost and token accumulation
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_funnel_cost_added_to_total():
    """Funnel AI tokens and cost must be added to the conversation total."""
    provider = ControlledMockProvider(
        main_response=_main_ai(),
        funnel_response=_funnel_ai(),
    )
    engine = AnalyticsEngine(ai_provider=provider)
    conv = _conv(_msg("inbound", 0), _msg("outbound", 5))
    result = await engine.analyze_conversation(conv, "conv-cost-test")

    # Provider returns tokens_input=100, tokens_output=50 per call
    # Two calls: main + funnel → total = 300 tokens, cost = 0.002
    assert result.tokens_used == 300
    assert result.analysis_cost_usd == pytest.approx(0.002, abs=1e-6)


# ══════════════════════════════════════════════════════════════════════════════
# effective_quote_response_time: backward compat fallback
# ══════════════════════════════════════════════════════════════════════════════


def test_effective_qrt_prefers_stored_value():
    from app.delivery.reports.pdf_generator import effective_quote_response_time
    from app.models.schemas import ConversationAnalysisResult

    r = ConversationAnalysisResult(
        conversation_id="x",
        has_purchase_intent=True,
        quote_response_time_seconds=600,
        intent_first_at=datetime(2025, 6, 1, 10, 0),
        quote_sent_at=datetime(2025, 6, 1, 11, 0),  # delta = 3600, but stored=600
    )
    assert effective_quote_response_time(r) == 600


def test_effective_qrt_falls_back_to_intent_when_stored_is_none():
    from app.delivery.reports.pdf_generator import effective_quote_response_time
    from app.models.schemas import ConversationAnalysisResult

    intent_ts = datetime(2025, 6, 1, 10, 0)
    sent_ts = intent_ts + timedelta(seconds=5116)
    r = ConversationAnalysisResult(
        conversation_id="x",
        has_purchase_intent=True,
        quote_response_time_seconds=None,
        intent_first_at=intent_ts,
        quote_sent_at=sent_ts,
    )
    assert effective_quote_response_time(r) == 5116


def test_effective_qrt_returns_none_when_no_timestamps():
    from app.delivery.reports.pdf_generator import effective_quote_response_time
    from app.models.schemas import ConversationAnalysisResult

    r = ConversationAnalysisResult(
        conversation_id="x",
        has_purchase_intent=True,
        quote_response_time_seconds=None,
        intent_first_at=None,
        quote_sent_at=None,
    )
    assert effective_quote_response_time(r) is None


def test_effective_qrt_returns_none_when_negative_fallback():
    """If quote_sent_at < intent_first_at → delta negative → None."""
    from app.delivery.reports.pdf_generator import effective_quote_response_time
    from app.models.schemas import ConversationAnalysisResult

    intent_ts = datetime(2025, 6, 1, 11, 0)
    sent_ts = datetime(2025, 6, 1, 10, 0)  # sent BEFORE intent
    r = ConversationAnalysisResult(
        conversation_id="x",
        has_purchase_intent=True,
        quote_response_time_seconds=None,
        intent_first_at=intent_ts,
        quote_sent_at=sent_ts,
    )
    assert effective_quote_response_time(r) is None


def test_effective_qrt_returns_none_when_stored_is_negative():
    from app.delivery.reports.pdf_generator import effective_quote_response_time
    from app.models.schemas import ConversationAnalysisResult

    r = ConversationAnalysisResult(
        conversation_id="x",
        has_purchase_intent=True,
        quote_response_time_seconds=-1,
    )
    assert effective_quote_response_time(r) is None


# ══════════════════════════════════════════════════════════════════════════════
# client_relationship: WAHA deterministic override
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_waha_returning_client_overrides_ai_new_classification():
    """wa_is_new_client=False must override AI's 'new' or 'uncertain' classification."""
    main_resp = {**_main_ai(), "client_relationship": "new", "client_relationship_source": "ai",
                 "client_relationship_signals": []}
    provider = ControlledMockProvider(main_response=main_resp, funnel_response=_funnel_ai())
    engine = AnalyticsEngine(ai_provider=provider)

    conv = NormalizedConversation(
        contact_phone="+57 300 0000000",
        messages=[
            NormalizedMessage(timestamp=BASE, direction=MessageDirection.INBOUND,
                              message_type=MessageType.TEXT, text_content="hola"),
        ],
        source="waha",
        wa_is_new_client=False,  # WAHA confirms returning client
    )
    result = await engine.analyze_conversation(conv, "conv-returning")

    assert result.client_relationship == "returning"
    assert result.client_relationship_source == "deterministic"


@pytest.mark.asyncio
async def test_waha_new_client_trusts_ai():
    """wa_is_new_client=True means we rely on AI classification."""
    main_resp = {**_main_ai(), "client_relationship": "new", "client_relationship_source": "ai",
                 "client_relationship_signals": ["primer mensaje detectado"]}
    provider = ControlledMockProvider(main_response=main_resp, funnel_response=_funnel_ai())
    engine = AnalyticsEngine(ai_provider=provider)

    conv = NormalizedConversation(
        contact_phone="+57 300 0000000",
        messages=[
            NormalizedMessage(timestamp=BASE, direction=MessageDirection.INBOUND,
                              message_type=MessageType.TEXT, text_content="hola"),
        ],
        source="waha",
        wa_is_new_client=True,
    )
    result = await engine.analyze_conversation(conv, "conv-new-client")

    assert result.client_relationship == "new"
    assert result.client_relationship_source == "ai"
