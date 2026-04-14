"""
Background analysis job processor.
Uses FastAPI BackgroundTasks (MVP). Upgrade to Celery for scale.
"""
import asyncio
import logging
from datetime import datetime

from app.analytics.ai.factory import create_provider
from app.analytics.engine import AnalyticsEngine
from app.config import settings
from app.database import async_session_factory
# Build NormalizedConversation from DB messages
from app.models.enums import MessageDirection, MessageType
from app.models.normalized import NormalizedConversation, NormalizedMessage
from app.models.schemas import ConversationAnalysisResult
from app.repositories.analysis_repo import AnalysisJobRepository, ConversationAnalysisRepository
from app.repositories.conversation_repo import ContactRepository, ConversationRepository, MessageRepository

logger = logging.getLogger(__name__)

_PROVIDER_DELAYS = {
    "openai": settings.openai_request_delay,
    "anthropic": settings.anthropic_request_delay,
    "gemini": settings.gemini_request_delay,
    "mock": 0.0,
}

_MAX_RETRIES = 3
_RETRY_DELAYS = [2, 4, 8]


async def run_analysis_job(job_id: str, conversation_ids: list[str]) -> None:
    """
    Background task: analyze all conversations in a job.
    Stores results incrementally and handles partial failures.
    """
    logger.info("Starting analysis job %s with %d conversations",
                job_id, len(conversation_ids))

    async with async_session_factory() as session:
        job_repo = AnalysisJobRepository(session)
        analysis_repo = ConversationAnalysisRepository(session)
        msg_repo = MessageRepository(session)
        conv_repo = ConversationRepository(session)
        contact_repo = ContactRepository(session)

        # Mark job as processing
        await job_repo.update(
            job_id,
            status="processing",
            started_at=datetime.utcnow(),
        )
        await session.commit()

        try:
            provider = create_provider()
        except Exception as exc:
            logger.error("Failed to create AI provider: %s", exc)
            await job_repo.update(job_id, status="failed", error_message=str(exc))
            await session.commit()
            return

        engine = AnalyticsEngine(ai_provider=provider)
        delay = _PROVIDER_DELAYS.get(provider.provider_name, 0.15)

        for conv_id in conversation_ids:
            # Load messages for this conversation
            try:
                messages = await msg_repo.list_by_conversation(conv_id)
                if not messages:
                    logger.warning(
                        "No messages found for conversation %s", conv_id)
                    await job_repo.increment_processed(job_id)
                    await session.commit()
                    continue

                norm_messages = [
                    NormalizedMessage(
                        source_id=m.source_id,
                        timestamp=m.timestamp,
                        direction=MessageDirection(m.direction),
                        sender_phone=m.sender_phone,
                        sender_name=m.sender_name,
                        message_type=MessageType(m.message_type),
                        text_content=m.text_content,
                    )
                    for m in messages
                ]

                # Load contact info via explicit async queries (no lazy loading)
                conv_record = await conv_repo.get(conv_id)
                contact_phone = "unknown"
                contact_name = None
                conv_source = "txt_upload"
                if conv_record:
                    conv_source = conv_record.source or "txt_upload"
                    if conv_record.contact_id:
                        contact_record = await contact_repo.get(str(conv_record.contact_id))
                        if contact_record:
                            contact_phone = contact_record.phone
                            contact_name = contact_record.name

                norm_conv = NormalizedConversation(
                    contact_phone=contact_phone,
                    contact_name=contact_name,
                    messages=norm_messages,
                    source=conv_source,
                )

                # Analyze with retries
                result = await _analyze_with_retry(engine, norm_conv, conv_id)

                # Store result
                await analysis_repo.create(
                    conversation_id=conv_id,
                    analysis_job_id=job_id,
                    sentiment=result.sentiment.value if result.sentiment else None,
                    sentiment_score=result.sentiment_score,
                    sentiment_reason=result.sentiment_reason,
                    primary_topic=result.primary_topic,
                    secondary_topics=result.secondary_topics,
                    quality_score=result.quality_score,
                    quality_breakdown=result.quality_breakdown.model_dump() if result.quality_breakdown else {},
                    conversion_status=result.conversion_status.value if result.conversion_status else None,
                    conversion_reason=result.conversion_reason,
                    summary=result.summary,
                    key_points=result.key_points,
                    ai_provider=result.ai_provider,
                    ai_model=result.ai_model,
                    tokens_used=result.tokens_used,
                    analysis_cost_usd=result.analysis_cost_usd,
                    # Computed metrics
                    first_response_time_seconds=result.first_response_time_seconds,
                    avg_response_time_seconds=result.avg_response_time_seconds,
                    median_response_time_seconds=result.median_response_time_seconds,
                    p95_response_time_seconds=result.p95_response_time_seconds,
                    unanswered_count=result.unanswered_count,
                    total_messages=result.total_messages,
                    inbound_count=result.inbound_count,
                    outbound_count=result.outbound_count,
                    duration_minutes=result.duration_minutes,
                    response_time_by_hour=result.response_time_by_hour,
                )

                await job_repo.increment_processed(job_id)
                await job_repo.add_token_usage(job_id, result.tokens_used, result.analysis_cost_usd)
                await session.commit()

                # Rate limiting
                if delay > 0:
                    await asyncio.sleep(delay)

            except Exception as exc:
                logger.error(
                    "Failed to process conversation %s in job %s: %s", conv_id, job_id, exc)
                await job_repo.increment_processed(job_id)
                await session.commit()

        # Mark job complete
        await job_repo.update(job_id, status="completed", completed_at=datetime.utcnow())
        await session.commit()
        logger.info("Analysis job %s completed.", job_id)


async def _analyze_with_retry(
    engine: AnalyticsEngine,
    conv,
    conv_id: str,
) -> ConversationAnalysisResult:
    last_exc = None
    for attempt, wait in enumerate([0] + _RETRY_DELAYS):
        if wait:
            await asyncio.sleep(wait)
        try:
            return await engine.analyze_conversation(conv, conv_id)
        except Exception as exc:
            last_exc = exc
            logger.warning("Retry %d for conversation %s: %s",
                           attempt, conv_id, exc)

    logger.error("All retries failed for conversation %s: %s",
                 conv_id, last_exc)
    return ConversationAnalysisResult(conversation_id=conv_id)
