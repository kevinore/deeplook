"""
AnalyticsEngine: orchestrates MetricsEngine → AIAnalysisEngine → InsightsGenerator.

Stateless: receives data, returns results. No DB access.
"""
import asyncio
import logging
from collections.abc import Callable

from app.analytics.ai.cost_tracker import CostTracker
from app.analytics.ai.provider import AIProvider
from app.analytics.ai.prompts.combined import SYSTEM_PROMPT, build_user_prompt
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
        self, conv: NormalizedConversation, conversation_id: str = ""
    ) -> ConversationAnalysisResult:
        """Analyze a single conversation end-to-end."""
        # Step 1: Metrics (pure math)
        stats = conv_stats.conversation_stats(conv)

        # Step 2: AI analysis
        transcript = format_conversation(conv)
        user_prompt = build_user_prompt(transcript)

        ai_result: ConversationAnalysisResult | None = None
        tokens_used = 0
        cost_usd = 0.0
        ai_provider_name = self._ai.provider_name
        ai_model_name = self._ai.model_name

        try:
            response = await self._ai.analyze(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
            ai_result = parse_ai_response(response.content, conversation_id)
            tokens_used = response.tokens_input + response.tokens_output
            cost_usd = response.cost_usd

            # Retry once if parse failed (ai_result has no sentiment)
            if ai_result.sentiment is None and response.content.strip():
                logger.warning("AI parse retry for conversation %s", conversation_id)
                retry_resp = await self._ai.analyze(
                    system_prompt=SYSTEM_PROMPT + "\n\nIMPORTANT: Return ONLY a JSON object, nothing else.",
                    user_prompt=user_prompt,
                )
                ai_result = parse_ai_response(retry_resp.content, conversation_id)
                tokens_used += retry_resp.tokens_input + retry_resp.tokens_output
                cost_usd += retry_resp.cost_usd

        except Exception as exc:
            logger.error("AI analysis failed for conversation %s: %s", conversation_id, exc)
            ai_result = ConversationAnalysisResult(conversation_id=conversation_id)

        # Step 3: Insights (single conversation)
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
        ai_result.first_response_time_seconds = first_rt
        ai_result.avg_response_time_seconds = stats.get("avg_response_time_seconds")
        ai_result.median_response_time_seconds = stats.get("median_response_time_seconds")
        ai_result.p95_response_time_seconds = stats.get("p95_response_time_seconds")
        ai_result.unanswered_count = stats.get("unanswered_count", 0)
        ai_result.total_messages = stats.get("total_messages", 0)
        ai_result.inbound_count = direction_counts.get("inbound", 0)
        ai_result.outbound_count = direction_counts.get("outbound", 0)
        ai_result.duration_minutes = stats.get("duration_minutes")
        ai_result.response_time_by_hour = rt_by_hour
        ai_result.health_score = health
        ai_result.recommendations = recs
        ai_result.alerts = conversation_alerts
        ai_result.ai_provider = ai_provider_name
        ai_result.ai_model = ai_model_name
        ai_result.tokens_used = tokens_used
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
