"""
AnalyticsEngine: orchestrates MetricsEngine → AIAnalysisEngine → InsightsGenerator.

Stateless: receives data, returns results. No DB access.
"""
import asyncio
import logging
from collections.abc import Callable

from app.analytics.ai.cost_tracker import CostTracker
from app.analytics.ai.provider import AIProvider
from app.analytics.ai.prompts.combined import build_system_prompt, build_user_prompt
from app.analytics.ai.prompts.formatter import format_conversation
from app.analytics.ai.prompts.response_parser import parse_ai_response
from app.analytics.insights import alerts as alerts_module
from app.analytics.insights import health_score as hs_module
from app.analytics.insights import recommendations as rec_module
from app.analytics.metrics import conversations as conv_stats
from app.analytics.metrics import response_time as rt
from app.models.normalized import NormalizedConversation
from app.models.schemas import ConversationAnalysisResult

logger = logging.getLogger(__name__)


class AnalyticsEngine:
    def __init__(self, ai_provider: AIProvider):
        self._ai = ai_provider

    async def analyze_conversation(
        self,
        conv: NormalizedConversation,
        conversation_id: str = "",
        business_type: str | None = None,
    ) -> ConversationAnalysisResult:
        """
        Analyze a single conversation end-to-end.

        `business_type`, when provided, is forwarded to the prompt so the AI
        adapts the closed topic taxonomy (P3) and renders into the deterministic
        facts block (P2).
        """
        # Step 1: Metrics (pure math)
        stats = conv_stats.conversation_stats(conv)

        # Step 2: AI analysis — system prompt parametrised by business_type;
        # user prompt prepended with deterministic facts block (includes wa_is_new_client hint).
        system_prompt = build_system_prompt(business_type)
        transcript = format_conversation(conv)
        user_prompt = build_user_prompt(
            transcript,
            stats=stats,
            business_type=business_type,
            wa_is_new_client=conv.wa_is_new_client,
        )

        ai_result: ConversationAnalysisResult | None = None
        tokens_input = 0
        tokens_output = 0
        cost_usd = 0.0
        ai_provider_name = self._ai.provider_name
        ai_model_name = self._ai.model_name

        try:
            response = await self._ai.analyze(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.0,
            )
            ai_result = parse_ai_response(response.content, conversation_id)
            tokens_input = response.tokens_input
            tokens_output = response.tokens_output
            cost_usd = response.cost_usd

            # Retry once if parse failed (ai_result has no sentiment)
            if ai_result.sentiment is None and response.content.strip():
                logger.warning("AI parse retry for conversation %s", conversation_id)
                retry_resp = await self._ai.analyze(
                    system_prompt=system_prompt
                    + "\n\nIMPORTANTE: Devuelve EXCLUSIVAMENTE un objeto JSON válido en español, "
                    "sin texto adicional, sin markdown, sin ```json. Todos los campos de texto en español colombiano.",
                    user_prompt=user_prompt,
                    temperature=0.0,
                )
                ai_result = parse_ai_response(retry_resp.content, conversation_id)
                tokens_input += retry_resp.tokens_input
                tokens_output += retry_resp.tokens_output
                cost_usd += retry_resp.cost_usd

        except Exception as exc:
            logger.error("AI analysis failed for conversation %s: %s", conversation_id, exc)
            ai_result = ConversationAnalysisResult(conversation_id=conversation_id)

        # Step 3: Commercial funnel — dedicated second AI call.
        # Runs on every conversation where the client wrote at least one message.
        # Skipping outbound-only (no client message = no purchase intent possible).
        _inbound_early = stats.get("by_direction", {}).get("inbound", 0)
        if _inbound_early > 0:
            from app.analytics.ai.prompts.funnel_prompt import (
                FUNNEL_SYSTEM_PROMPT,
                build_funnel_user_prompt,
            )
            from app.analytics.ai.prompts.funnel_parser import (
                empty_funnel_ai,
                parse_funnel_response,
            )
            from app.analytics.metrics.funnel import detect_funnel_signals, finalize_funnel

            funnel_signals = detect_funnel_signals(conv)
            funnel_user_prompt = build_funnel_user_prompt(
                transcript=transcript,
                inbound_count=_inbound_early,
                outbound_count=stats.get("by_direction", {}).get("outbound", 0),
                outbound_media_events=funnel_signals.get("outbound_media_events", []),
                outbound_price_events=funnel_signals.get("outbound_price_events", []),
                inbound_quote_request_events=funnel_signals.get("inbound_quote_request_events", []),
                inbound_intent_events=funnel_signals.get("inbound_intent_events", []),
                main_conversion_status=(
                    ai_result.conversion_status.value if ai_result.conversion_status else None
                ),
                main_summary=ai_result.summary,
            )

            try:
                funnel_response = await self._ai.analyze(
                    system_prompt=FUNNEL_SYSTEM_PROMPT,
                    user_prompt=funnel_user_prompt,
                    temperature=0.0,
                )
                funnel_ai = parse_funnel_response(funnel_response.content, conversation_id)
                tokens_input += funnel_response.tokens_input
                tokens_output += funnel_response.tokens_output
                cost_usd += funnel_response.cost_usd
            except Exception as funnel_exc:
                logger.error(
                    "Funnel AI call failed for conversation %s: %s", conversation_id, funnel_exc
                )
                funnel_ai = empty_funnel_ai()

            # Phase B: finalize timestamps and derived metrics deterministically
            funnel_final = finalize_funnel(
                funnel_signals=funnel_signals,
                msgs=conv.messages,
                ai_intent_offset_s=funnel_ai["intent_first_at_offset_seconds"],
                ai_quote_requested_offset_s=funnel_ai["quote_requested_at_offset_seconds"],
                ai_has_purchase_intent=funnel_ai["has_purchase_intent"],
                ai_intent_stage=funnel_ai["intent_stage"],
                ai_is_ghosted=stats.get("is_ghosted", False),
            )

            # Merge funnel results into ai_result
            ai_result.has_purchase_intent = funnel_ai["has_purchase_intent"]
            ai_result.intent_stage = funnel_ai["intent_stage"]
            ai_result.lost_reason = funnel_ai["lost_reason"]
            ai_result.lost_reason_detail = funnel_ai["lost_reason_detail"]
            ai_result.intent_first_at = funnel_final["intent_first_at"]
            ai_result.quote_requested_at = funnel_final["quote_requested_at"]
            ai_result.quote_sent_at = funnel_final["quote_sent_at"]
            ai_result.quote_response_time_seconds = funnel_final["quote_response_time_seconds"]
            ai_result.post_quote_followup_count = funnel_final["post_quote_followup_count"]
            ai_result.followup_delay_hours = funnel_final["followup_delay_hours"]

            # Deterministic floor: if we found an outbound quote/media, purchase intent
            # is certain regardless of the AI's classification (you don't send a quote
            # to someone who showed no interest).
            if funnel_final["quote_sent_at"] is not None and not ai_result.has_purchase_intent:
                ai_result.has_purchase_intent = True
                if ai_result.intent_stage in (None, "none"):
                    ai_result.intent_stage = "quoted"

            # Cross-validation: enforce consistency between funnel and main analysis.
            # Only propagate conversion_status=converted → intent if the funnel AI
            # confirmed purchase intent. If the funnel says has_purchase_intent=False
            # (e.g. operational task, internal coordination), trust the funnel AI —
            # the main analysis may have misclassified a task completion as a sale.
            if (
                ai_result.conversion_status
                and ai_result.conversion_status.value == "converted"
                and ai_result.has_purchase_intent  # funnel AI must agree it's commercial
            ):
                ai_result.intent_stage = "converted"
            if ai_result.intent_stage in (
                "converted", "lost", "negotiating", "quoted", "quote_requested", "exploring"
            ):
                ai_result.has_purchase_intent = True
            # Ghosted + quote sent + no prior followup → pending, not lost
            if (
                stats.get("is_ghosted", False)
                and ai_result.quote_sent_at is not None
                and (ai_result.post_quote_followup_count or 0) == 0
                and ai_result.intent_stage == "lost"
                and ai_result.lost_reason is None
            ):
                ai_result.intent_stage = "pending"

        # Step 4: Insights (single conversation)
        first_rt = stats.get("first_response_time_seconds")
        health = hs_module.calculate_health_score(
            [ai_result],
            first_response_time_seconds=first_rt,
            avg_response_time_seconds=stats.get("avg_response_time_seconds"),
        )
        recs = rec_module.generate_recommendations(
            [ai_result],
            first_response_time_seconds=first_rt,
            avg_response_time_seconds=stats.get("avg_response_time_seconds"),
        )
        conversation_alerts = alerts_module.generate_alerts([ai_result])

        direction_counts = stats.get("by_direction", {})

        # Convert by_hour keys to strings for JSON serialisation
        rt_by_hour_raw = stats.get("response_time_by_hour") or {}
        rt_by_hour = {str(k): v for k, v in rt_by_hour_raw.items()} if rt_by_hour_raw else None

        # Merge everything
        ai_result.conversation_id = conversation_id
        # Response-time metrics
        ai_result.first_response_time_seconds = first_rt
        ai_result.avg_response_time_seconds = stats.get("avg_response_time_seconds")
        ai_result.avg_response_time_bh_seconds = stats.get("avg_response_time_bh_seconds")
        ai_result.median_response_time_seconds = stats.get("median_response_time_seconds")
        ai_result.p95_response_time_seconds = stats.get("p95_response_time_seconds")
        ai_result.unanswered_count = stats.get("unanswered_count", 0)
        ai_result.trailing_inbound_messages = stats.get("trailing_inbound_messages", 0)
        ai_result.total_messages = stats.get("total_messages", 0)
        ai_result.inbound_count = direction_counts.get("inbound", 0)
        ai_result.outbound_count = direction_counts.get("outbound", 0)
        ai_result.duration_minutes = stats.get("duration_minutes")
        ai_result.response_time_by_hour = rt_by_hour
        # Deterministic ack-derived metrics
        ai_result.delivery_rate = stats.get("delivery_rate")
        ai_result.read_rate = stats.get("read_rate")
        ai_result.is_ghosted = stats.get("is_ghosted", False)
        ai_result.last_business_msg_ack = stats.get("last_business_msg_ack")
        # Operational coverage
        ai_result.operational_coverage_score = stats.get("operational_coverage_score")
        ai_result.out_of_hours_inbound_pct = stats.get("out_of_hours_inbound_pct")
        # WAHA chat metadata cross-checks
        ai_result.wa_unread_count = stats.get("wa_unread_count")
        ai_result.wa_is_muted = stats.get("wa_is_muted", False)
        ai_result.wa_is_archived = stats.get("wa_is_archived", False)
        # Client relationship — merge deterministic (Layer 1) with AI (Layer 2).
        # wa_is_new_client=False means WAHA confirmed returning client → override AI.
        # wa_is_new_client=True/None → trust AI classification from text signals.
        if conv.wa_is_new_client is False:
            # Deterministic win: WAHA has prior messages → confirmed returning
            if ai_result.client_relationship in ("new", "uncertain"):
                ai_result.client_relationship = "returning"
            ai_result.client_relationship_source = "deterministic"
        elif ai_result.client_relationship not in (None, "uncertain"):
            ai_result.client_relationship_source = "ai"
        else:
            ai_result.client_relationship_source = None
        # Health / insights / meta
        ai_result.health_score = health
        ai_result.recommendations = recs
        ai_result.alerts = conversation_alerts
        ai_result.ai_provider = ai_provider_name
        ai_result.ai_model = ai_model_name
        ai_result.tokens_input = tokens_input
        ai_result.tokens_output = tokens_output
        ai_result.tokens_used = tokens_input + tokens_output
        ai_result.analysis_cost_usd = cost_usd

        return ai_result

    async def analyze_batch(
        self,
        conversations: list[tuple[NormalizedConversation, str]],
        on_progress: Callable[[int, int], None] | None = None,
    ) -> list[ConversationAnalysisResult]:
        """
        Analyze multiple conversations.

        conversations: list of (NormalizedConversation, conversation_db_id)
        on_progress: callback(processed_count, total_count)
        """
        results: list[ConversationAnalysisResult] = []
        total = len(conversations)

        for i, (conv, conv_id) in enumerate(conversations):
            try:
                result = await self.analyze_conversation(conv, conv_id)
                results.append(result)
            except Exception as exc:
                logger.error("Failed to analyze conversation %s: %s", conv_id, exc)
                results.append(ConversationAnalysisResult(conversation_id=conv_id))

            if on_progress:
                on_progress(i + 1, total)

        return results
