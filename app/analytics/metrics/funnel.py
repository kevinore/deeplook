"""
Deterministic commercial funnel signals.

Phase A — detect_funnel_signals() — runs BEFORE the AI call:
  Scans NormalizedMessage objects for outbound media (documents/images/audio)
  and outbound text with price patterns. Results are injected into the funnel
  prompt's HECHOS block so the AI has ground truth it cannot contradict.

Phase B — finalize_funnel() — runs AFTER the AI call:
  Converts AI-provided offsets (seconds from conv start) into real timestamps,
  then resolves quote_sent_at from the deterministic signal pool and computes
  all derived metrics (response time, follow-up count, follow-up delay).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from app.models.enums import MessageDirection, MessageType
from app.models.normalized import NormalizedConversation, NormalizedMessage

# Outbound media types that can carry a quote or proposal document
_MEDIA_QUOTE_TYPES = {MessageType.DOCUMENT, MessageType.IMAGE, MessageType.AUDIO}

# Colombian / general Spanish price patterns in outbound messages.
# Matches: $150.000, $1.500.000, 150 mil pesos, 2 millones, precio: $X,
#          son $X, cuesta X, cotización adjunta, propuesta adjunta, etc.
_PRICE_RE = re.compile(
    r"""
    (?:
        \$\s*[\d]{1,3}(?:[.,]\d{3})+   # $1.500.000 or $1,500,000
        | \$\s*\d{4,}                    # $15000 (no separator)
        | [\d]{3,}(?:[.,]\d{3})*\s*(?:pesos?|cop)  # 150000 pesos
        | [\d]+(?:[.,]\d+)?\s*(?:mil|millones?)\s*(?:de\s+)?(?:pesos?)?  # 150 mil / 2 millones
        | (?:precio|valor|costo|cotizaci[oó]n|presupuesto)\s*[:=\-]\s*[\d$]
        | (?:son|cuesta|vale|cobro|cobramos|queda(?:r[ií]a)?)\s+(?:\$|\d)
        | cotizaci[oó]n\s+adjunta
        | propuesta\s+adjunta
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Inbound patterns: client asking for price/quote — covers both formal proposals
# (document-based) and simple chat price inquiries ("cuánto cuesta?").
_QUOTE_REQUEST_INBOUND_RE = re.compile(
    r"""
    (?:
        # Explicit request for a formal quote/proposal document
        (?:me\s+(?:puede[n]?\s+)?(?:dar|enviar|pasar|mandar|compartir))
            \s+(?:una?\s+)?(?:cotizaci[oó]n|presupuesto|propuesta|precio)
        | (?:quiero|quisiera|necesito)\s+(?:una?\s+)?(?:cotizaci[oó]n|presupuesto|propuesta)
        | (?:pueden\s+)?cotizarme

        # Price inquiry with specific service/treatment keyword
        | cu[aá]nto\s+(?:vale|cuesta[n]?|cobran?|quedar[ií]a)\s+.{0,40}
            (?:el\s+)?(?:tratamiento|servicio|procedimiento|paquete|plan|implante|ortodoncia
                        |blanqueamiento|carilla|limpieza|endodoncia|corona|consulta|cita
                        |estamp?|producto|curso|clase|taller|sesi[oó]n)

        # Generic price inquiry — short and unambiguous in a business context
        | cu[aá]nto\s+(?:vale[n]?|cuestan?|cobran?|sale[n]?|est[aá][n]?)\b
        | a\s+cu[aá]nto\s+(?:est[aá][n]?|queda[n]?|lo\s+dan?)
        | cu[aá]l\s+es\s+el\s+(?:precio|costo|valor|tarifa)
        | (?:tienen?\s+)?(?:alg[uú]n\s+)?(?:precio|tarifa|costo)\s+(?:de|para|por|del)
        | (?:precio|presupuesto|cotizaci[oó]n)\s+(?:de|para|del|por)

        # Payment / financing terms
        | (?:tienen\s+)?(?:alg[uú]n\s+)?plan\s+de\s+(?:pago|financiaci[oó]n|cuotas)
        | forma(?:s)?\s+de\s+pago
        | manejan?\s+(?:cuotas|cr[eé]dito|financiaci[oó]n)

        # "How much would X cost?"
        | (?:cu[aá]nto\s+)?(?:quedar[ií]a|sale[n]?)\s+(?:los?\s+)?
            (?:tratamiento|servicio|implante|brackets|ortodoncia|todo|eso|esos|esas)
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Inbound patterns: client showing purchase intent (querer/necesitar with specificity).
_INTENT_SIGNAL_INBOUND_RE = re.compile(
    r"""
    (?:
        (?:quiero|quisiera)\s+
            (?:agendar|pedir\s+una?\s+cita|contratar|comprar|hacerme|realizarme
               |empezar|iniciar|el\s+servicio|los?\s+(?:servicio|tratamiento|implante|bracket))
        | me\s+interesa\s+(?:el|la|un|una|contratar|hacerme|el\s+servicio|el\s+tratamiento
                             |los?\s+bracket|la\s+ortodoncia|el\s+implante|el\s+blanqueamiento)
        | estoy\s+interesad[oa]
        | (?:voy\s+a|vamos\s+a)\s+(?:pedir|contratar|hacernos?|agendar|comprar)
        | necesito\s+(?:agendar|contratar|hacerme|realizarme|el\s+servicio|el\s+tratamiento)
        | quiero\s+(?:saber\s+)?(?:si\s+)?(?:son|pueden\s+atender(?:me)?)\s+.{0,30}
            (?:hoy|ma[ñn]ana|esta\s+semana|el\s+s[aá]bado|urgente)
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)


def detect_funnel_signals(conv: NormalizedConversation) -> dict:
    """
    Phase A: scan message sequence for deterministic funnel signals.

    Returns a dict consumed by both:
    - build_funnel_user_prompt() — injects into HECHOS block
    - finalize_funnel() — resolves timestamps after AI call
    """
    msgs = conv.messages
    if not msgs:
        return {
            "conv_start": None,
            "outbound_media_events": [],
            "outbound_price_events": [],
        }

    conv_start: datetime = msgs[0].timestamp
    outbound_media_events: list[dict] = []
    outbound_price_events: list[dict] = []
    inbound_quote_request_events: list[dict] = []
    inbound_intent_events: list[dict] = []

    for msg in msgs:
        offset_s = int((msg.timestamp - conv_start).total_seconds())

        if msg.direction == MessageDirection.OUTBOUND:
            if msg.message_type in _MEDIA_QUOTE_TYPES:
                outbound_media_events.append({
                    "timestamp": msg.timestamp,
                    "offset_s": offset_s,
                    "type": msg.message_type.value,
                })
            if msg.text_content and _PRICE_RE.search(msg.text_content):
                snippet = msg.text_content[:120].replace("\n", " ")
                outbound_price_events.append({
                    "timestamp": msg.timestamp,
                    "offset_s": offset_s,
                    "snippet": snippet,
                })

        elif msg.direction == MessageDirection.INBOUND and msg.text_content:
            # Quote request: client explicitly asks for a price/quote
            m = _QUOTE_REQUEST_INBOUND_RE.search(msg.text_content)
            if m:
                snippet = msg.text_content[:120].replace("\n", " ")
                inbound_quote_request_events.append({
                    "timestamp": msg.timestamp,
                    "offset_s": offset_s,
                    "snippet": snippet,
                })

            # Intent signal: client expresses purchase intent (not just curiosity)
            if not inbound_intent_events:  # first match only
                mi = _INTENT_SIGNAL_INBOUND_RE.search(msg.text_content)
                if mi:
                    snippet = msg.text_content[:120].replace("\n", " ")
                    inbound_intent_events.append({
                        "timestamp": msg.timestamp,
                        "offset_s": offset_s,
                        "snippet": snippet,
                    })

    return {
        "conv_start": conv_start,
        "outbound_media_events": outbound_media_events,
        "outbound_price_events": outbound_price_events,
        "inbound_quote_request_events": inbound_quote_request_events,
        "inbound_intent_events": inbound_intent_events,
    }


def finalize_funnel(
    funnel_signals: dict,
    msgs: list[NormalizedMessage],
    ai_intent_offset_s: int | None,
    ai_quote_requested_offset_s: int | None,
    ai_has_purchase_intent: bool,
    ai_intent_stage: str,
    ai_is_ghosted: bool,
) -> dict:
    """
    Phase B: merge deterministic signals with AI offsets.

    Timestamp resolution priority (highest → lowest confidence):
      1. Deterministic: real message timestamp from inbound regex scan
      2. Semi-deterministic: AI offset converted to timestamp (fallback)

    Resolution order for quote_sent_at (outbound):
      Layer 1 — First outbound MEDIA after quote_requested_at
      Layer 2 — First outbound MEDIA after intent_first_at (proactive/implicit)
      Layer 3 — First outbound TEXT with price pattern after quote_requested_at
      Layer 4 — First outbound TEXT with price pattern after intent_first_at
      Layer 5 — First outbound media overall (if has_purchase_intent and no ref time)

    Returns empty-funnel dict when no signals available.
    """
    conv_start: datetime | None = funnel_signals.get("conv_start")
    if conv_start is None:
        conv_start = msgs[0].timestamp if msgs else None
    if conv_start is None:
        return _empty_funnel()

    outbound_media: list[dict] = funnel_signals.get("outbound_media_events") or []
    outbound_price: list[dict] = funnel_signals.get("outbound_price_events") or []
    inbound_quote_reqs: list[dict] = funnel_signals.get("inbound_quote_request_events") or []
    inbound_intents: list[dict] = funnel_signals.get("inbound_intent_events") or []

    # --- intent_first_at: prefer deterministic inbound signal, fall back to AI offset ---
    intent_first_at: datetime | None = None
    if inbound_intents:
        # Use the earliest deterministic intent signal found in actual messages
        intent_first_at = min(inbound_intents, key=lambda e: e["timestamp"])["timestamp"]
    elif inbound_quote_reqs:
        # A quote request IS an intent signal — use earliest if no pure intent match
        intent_first_at = min(inbound_quote_reqs, key=lambda e: e["timestamp"])["timestamp"]
    elif ai_intent_offset_s is not None and ai_intent_offset_s >= 0:
        intent_first_at = conv_start + timedelta(seconds=ai_intent_offset_s)

    # --- quote_requested_at: prefer deterministic inbound quote-request, fall back to AI offset ---
    quote_requested_at: datetime | None = None
    if inbound_quote_reqs:
        # First message where client explicitly asked for a price/quote
        quote_requested_at = min(inbound_quote_reqs, key=lambda e: e["timestamp"])["timestamp"]
    elif ai_quote_requested_offset_s is not None and ai_quote_requested_offset_s >= 0:
        quote_requested_at = conv_start + timedelta(seconds=ai_quote_requested_offset_s)

    # --- Resolve quote_sent_at ---
    # The anchor time is the earliest point at which a "quote" makes sense:
    # prefer quote_requested_at; fall back to intent_first_at.
    anchor_ts: datetime | None = quote_requested_at or intent_first_at
    quote_sent_at: datetime | None = None

    if anchor_ts is not None:
        # Layer 1: first outbound media strictly after anchor
        for ev in sorted(outbound_media, key=lambda e: e["timestamp"]):
            if ev["timestamp"] > anchor_ts:
                quote_sent_at = ev["timestamp"]
                break

        # Layer 3: first outbound price-text strictly after anchor
        if quote_sent_at is None:
            for ev in sorted(outbound_price, key=lambda e: e["timestamp"]):
                if ev["timestamp"] > anchor_ts:
                    quote_sent_at = ev["timestamp"]
                    break
    elif ai_has_purchase_intent:
        # No explicit request time — proactive quote case
        if outbound_media:
            quote_sent_at = min(outbound_media, key=lambda e: e["timestamp"])["timestamp"]
        elif outbound_price:
            quote_sent_at = min(outbound_price, key=lambda e: e["timestamp"])["timestamp"]

    # --- Derived metrics ---
    # Use quote_requested_at as reference if available; fall back to intent_first_at.
    # Both are real data points — the former measures explicit-request→quote,
    # the latter measures interest-shown→quote.
    quote_response_time_seconds: int | None = None
    if quote_sent_at is not None:
        ref_ts = quote_requested_at or intent_first_at
        if ref_ts is not None:
            delta = (quote_sent_at - ref_ts).total_seconds()
            if delta >= 0:
                quote_response_time_seconds = int(delta)

    post_quote_followup_count: int | None = None
    followup_delay_hours: float | None = None
    if quote_sent_at is not None:
        followup_msgs = [
            m for m in msgs
            if m.direction == MessageDirection.OUTBOUND
            and m.timestamp > quote_sent_at
        ]
        post_quote_followup_count = len(followup_msgs)
        if followup_msgs:
            followup_delay_hours = round(
                (followup_msgs[0].timestamp - quote_sent_at).total_seconds() / 3600.0, 2
            )

    return {
        "intent_first_at": intent_first_at,
        "quote_requested_at": quote_requested_at,
        "quote_sent_at": quote_sent_at,
        "quote_response_time_seconds": quote_response_time_seconds,
        "post_quote_followup_count": post_quote_followup_count,
        "followup_delay_hours": followup_delay_hours,
        # Confidence flags — True when timestamp comes from a real message, not an AI offset
        "intent_first_at_is_deterministic": bool(inbound_intents or inbound_quote_reqs),
        "quote_requested_at_is_deterministic": bool(inbound_quote_reqs),
    }


def _empty_funnel() -> dict:
    return {
        "intent_first_at": None,
        "quote_requested_at": None,
        "quote_sent_at": None,
        "quote_response_time_seconds": None,
        "post_quote_followup_count": None,
        "followup_delay_hours": None,
        "intent_first_at_is_deterministic": False,
        "quote_requested_at_is_deterministic": False,
    }
