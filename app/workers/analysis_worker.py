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
from app.models.normalized import NormalizedConversation
from app.models.schemas import ConversationAnalysisResult
from app.repositories.analysis_repo import AnalysisJobRepository, ConversationAnalysisRepository
from app.repositories.client_repo import ClientRepository
from app.repositories.notification_repo import NotificationRepository

logger = logging.getLogger(__name__)

_PROVIDER_CONCURRENCY = {
    "openai": 8,
    "anthropic": 4,
    "gemini": 8,
    "mock": 20,
}

_MAX_RETRIES = 3
_RETRY_DELAYS = [2, 4, 8]


async def run_analysis_job(
    job_id: str,
    pairs: list[tuple[NormalizedConversation, str]],
) -> None:
    """
    Background task: analyze all conversations in a job.
    Receives NormalizedConversation objects directly from the sync service —
    no DB round-trip for raw messages (they are never stored).
    Stores results incrementally and handles partial failures.
    """
    logger.info("Starting analysis job %s with %d conversations", job_id, len(pairs))

    # Sort chronologically by first message timestamp for deterministic ordering.
    pairs = sorted(pairs, key=lambda p: min((m.timestamp for m in p[0].messages), default=datetime.utcnow()))

    async with async_session_factory() as session:
        job_repo = AnalysisJobRepository(session)
        analysis_repo = ConversationAnalysisRepository(session)

        # Mark job as processing
        await job_repo.update(job_id, status="processing", started_at=datetime.utcnow())
        await session.commit()

        try:
            provider = create_provider()
        except Exception as exc:
            logger.error("Failed to create AI provider: %s", exc)
            job = await job_repo.get(job_id)
            if job:
                await NotificationRepository(session).create(
                    client_id=str(job.client_id),
                    type="report_failed",
                    title="Error en el análisis",
                    body="No se pudo iniciar el análisis de tus conversaciones. El equipo ha sido notificado.",
                    job_id=job_id,
                )
            await job_repo.update(job_id, status="failed", error_message=str(exc))
            await session.commit()
            return

        engine = AnalyticsEngine(ai_provider=provider)
        concurrency = _PROVIDER_CONCURRENCY.get(provider.provider_name, 5)

        # Resolve the client's business_type once per job — the AI prompt uses it
        # to adapt the closed topic taxonomy (P3) and render the facts block (P2).
        business_type: str | None = None
        try:
            job_for_client = await job_repo.get(job_id)
            if job_for_client is not None:
                client = await ClientRepository(session).get(str(job_for_client.client_id))
                if client is not None:
                    business_type = client.business_type
        except Exception:
            logger.warning("Could not resolve business_type for job %s — falling back to default", job_id)

        await job_repo.update(job_id, ai_provider=provider.provider_name, ai_model=provider.model_name)
        await session.commit()

        try:
            # Phase 1: Run all AI analysis calls concurrently (the slow part).
            # DB writes are NOT done here — AsyncSession is not safe for concurrent access.
            sem = asyncio.Semaphore(concurrency)
            result_queue: asyncio.Queue = asyncio.Queue()

            async def _analyze_one(norm_conv: NormalizedConversation, conv_id: str) -> None:
                async with sem:
                    if not norm_conv.messages:
                        await result_queue.put((None, conv_id))
                        return
                    result = await _analyze_with_retry(engine, norm_conv, conv_id, business_type)
                    await result_queue.put((result, conv_id))

            tasks = [asyncio.create_task(_analyze_one(nc, cid)) for nc, cid in pairs]

            # Phase 2: Write results to DB as they arrive (sequential, progress bar stays live).
            for _ in range(len(pairs)):
                result, conv_id = await result_queue.get()

                if result is None:
                    logger.warning("No messages for conversation %s — skipping", conv_id)
                    await job_repo.increment_processed(job_id)
                    await session.commit()
                    continue

                for store_attempt in range(2):
                    try:
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
                            customer_questions=result.customer_questions,
                            ai_provider=result.ai_provider,
                            ai_model=result.ai_model,
                            tokens_input=result.tokens_input,
                            tokens_output=result.tokens_output,
                            tokens_used=result.tokens_used,
                            analysis_cost_usd=result.analysis_cost_usd,
                            first_response_time_seconds=result.first_response_time_seconds,
                            avg_response_time_seconds=result.avg_response_time_seconds,
                            median_response_time_seconds=result.median_response_time_seconds,
                            p95_response_time_seconds=result.p95_response_time_seconds,
                            avg_response_time_bh_seconds=result.avg_response_time_bh_seconds,
                            unanswered_count=result.unanswered_count,
                            trailing_inbound_messages=result.trailing_inbound_messages,
                            total_messages=result.total_messages,
                            inbound_count=result.inbound_count,
                            outbound_count=result.outbound_count,
                            duration_minutes=result.duration_minutes,
                            response_time_by_hour=result.response_time_by_hour,
                            # Deterministic ack-based metrics
                            delivery_rate=result.delivery_rate,
                            read_rate=result.read_rate,
                            is_ghosted=result.is_ghosted,
                            last_business_msg_ack=result.last_business_msg_ack,
                            operational_coverage_score=result.operational_coverage_score,
                            out_of_hours_inbound_pct=result.out_of_hours_inbound_pct,
                            wa_unread_count=result.wa_unread_count,
                            wa_is_muted=result.wa_is_muted,
                            wa_is_archived=result.wa_is_archived,
                        )
                        await job_repo.increment_processed(job_id)
                        await job_repo.add_token_usage(job_id, result.tokens_input, result.tokens_output, result.analysis_cost_usd)
                        await session.commit()
                        break
                    except Exception as exc:
                        try:
                            await session.rollback()
                        except Exception:
                            pass
                        if store_attempt == 0:
                            logger.warning("Retrying store for conversation %s in job %s: %s", conv_id, job_id, exc)
                        else:
                            logger.error(
                                "CRITICAL: Failed to store analysis for conversation %s in job %s "
                                "after retry — will be MISSING from the PDF. Error: %s",
                                conv_id, job_id, exc)
                            try:
                                await job_repo.increment_processed(job_id)
                                await session.commit()
                            except Exception:
                                pass

            # Ensure all tasks are awaited (they are complete once queue is drained)
            await asyncio.gather(*tasks, return_exceptions=True)

        except Exception as loop_exc:
            logger.error("Unexpected error in analysis loop for job %s: %s", job_id, loop_exc, exc_info=True)
            try:
                await session.rollback()
                job = await job_repo.get(job_id)
                if job:
                    await NotificationRepository(session).create(
                        client_id=str(job.client_id),
                        type="report_failed",
                        title="Error en el análisis",
                        body="El análisis se interrumpió inesperadamente. El equipo ha sido notificado.",
                        job_id=job_id,
                    )
                await job_repo.update(job_id, status="failed", error_message=str(loop_exc))
                await session.commit()
            except Exception:
                pass
            return

        # Mark job complete and notify the user
        count = len(pairs)
        job = await job_repo.get(job_id)
        if job:
            body = (
                f"Se analizó {count} conversación. Revisa tus reportes." if count == 1
                else f"Se analizaron {count} conversaciones. Revisa tus reportes."
            )
            await NotificationRepository(session).create(
                client_id=str(job.client_id),
                type="report_ready",
                title="Tu reporte está listo",
                body=body,
                job_id=job_id,
                extra_data={"conversation_count": count},
            )
        await job_repo.update(job_id, status="completed", completed_at=datetime.utcnow())
        await session.commit()
        logger.info("Analysis job %s completed.", job_id)

        # Fire-and-forget email with the PDF attached.
        # Errors here must NOT mark the job failed — the analysis is already saved.
        if job:
            asyncio.create_task(_send_report_email(job_id, str(job.client_id)))


async def _send_report_email(job_id: str, client_id: str) -> None:
    """Generate the PDF and email it to the client. Best-effort, no retries."""
    import statistics
    from app.analytics.insights.health_score import calculate_health_score
    from app.delivery.notifications.email_service import get_email_service
    from app.delivery.reports.pdf_generator import generate_pdf_report
    from app.models.schemas import ConversationAnalysisResult, QualityBreakdown

    try:
        async with async_session_factory() as session:
            client_repo  = ClientRepository(session)
            job_repo     = AnalysisJobRepository(session)
            analysis_repo = ConversationAnalysisRepository(session)

            client = await client_repo.get(client_id)
            job    = await job_repo.get(job_id)
            if client is None or job is None or not client.email:
                logger.info("Skipping report email — no client/job/email (job=%s)", job_id)
                return

            rows = await analysis_repo.list_by_job_with_contact(job_id)
            results = [
                ConversationAnalysisResult(
                    conversation_id=a.conversation_id,
                    contact_phone=contact.phone if contact else None,
                    contact_name=contact.name if contact else None,
                    started_at=conv.started_at if conv else None,
                    sentiment=a.sentiment,
                    sentiment_score=a.sentiment_score,
                    sentiment_reason=a.sentiment_reason,
                    primary_topic=a.primary_topic,
                    secondary_topics=a.secondary_topics or [],
                    quality_score=a.quality_score,
                    quality_breakdown=QualityBreakdown(**a.quality_breakdown) if a.quality_breakdown else QualityBreakdown(),
                    conversion_status=a.conversion_status,
                    conversion_reason=a.conversion_reason,
                    summary=a.summary,
                    key_points=a.key_points or [],
                    customer_questions=a.customer_questions or [],
                    tokens_used=a.tokens_used,
                    analysis_cost_usd=a.analysis_cost_usd,
                    ai_provider=a.ai_provider,
                    ai_model=a.ai_model,
                    first_response_time_seconds=a.first_response_time_seconds,
                    avg_response_time_seconds=a.avg_response_time_seconds,
                    median_response_time_seconds=a.median_response_time_seconds,
                    p95_response_time_seconds=a.p95_response_time_seconds,
                    unanswered_count=a.unanswered_count or 0,
                    trailing_inbound_messages=getattr(a, "trailing_inbound_messages", 0) or 0,
                    total_messages=a.total_messages or 0,
                    inbound_count=a.inbound_count or 0,
                    outbound_count=a.outbound_count or 0,
                    duration_minutes=a.duration_minutes,
                    response_time_by_hour=a.response_time_by_hour,
                    delivery_rate=getattr(a, "delivery_rate", None),
                    read_rate=getattr(a, "read_rate", None),
                    is_ghosted=bool(getattr(a, "is_ghosted", False)),
                    last_business_msg_ack=getattr(a, "last_business_msg_ack", None),
                    operational_coverage_score=getattr(a, "operational_coverage_score", None),
                    out_of_hours_inbound_pct=getattr(a, "out_of_hours_inbound_pct", None),
                    wa_unread_count=getattr(a, "wa_unread_count", None),
                    wa_is_muted=bool(getattr(a, "wa_is_muted", False)),
                    wa_is_archived=bool(getattr(a, "wa_is_archived", False)),
                    avg_response_time_bh_seconds=getattr(a, "avg_response_time_bh_seconds", None),
                )
                for (a, conv, contact) in rows
            ]
            if not results:
                logger.info("Skipping report email — no analyses (job=%s)", job_id)
                return

            frt_values    = [r.first_response_time_seconds for r in results if r.first_response_time_seconds is not None]
            rt_values     = [r.avg_response_time_seconds   for r in results if r.avg_response_time_seconds   is not None]
            avg_first_rt  = statistics.mean(frt_values) if frt_values else None
            median_frt    = statistics.median(frt_values) if frt_values else None
            avg_rt        = statistics.mean(rt_values) if rt_values else None
            health_score = calculate_health_score(
                results,
                first_response_time_seconds=median_frt,
                avg_response_time_seconds=avg_rt,
            )

        # Generate PDF outside the DB session (CPU-heavy, no DB needed).
        try:
            pdf_bytes = await asyncio.to_thread(
                generate_pdf_report,
                results=results,
                business_name=client.business_name,
                job_id=job_id,
                ai_model=job.ai_model or "unknown",
                average_transaction_value=client.average_transaction_value,
                business_type=client.business_type,
                previous_results=[],
                previous_job_created_at=None,
            )
        except Exception:
            logger.exception("PDF generation failed for report email — sending without attachment")
            pdf_bytes = None

        await get_email_service().send_report_ready(
            to_email=client.email,
            name=client.name,
            business_name=client.business_name,
            job_id=job_id,
            conversation_count=len(results),
            health_score=health_score,
            pdf_bytes=pdf_bytes,
        )
    except Exception:
        logger.exception("Report-ready email task failed (job=%s)", job_id)


async def _analyze_with_retry(
    engine: AnalyticsEngine,
    conv,
    conv_id: str,
    business_type: str | None = None,
) -> ConversationAnalysisResult:
    last_exc = None
    for attempt, wait in enumerate([0] + _RETRY_DELAYS):
        if wait:
            await asyncio.sleep(wait)
        try:
            return await engine.analyze_conversation(conv, conv_id, business_type=business_type)
        except Exception as exc:
            last_exc = exc
            logger.warning("Retry %d for conversation %s: %s",
                           attempt, conv_id, exc)

    logger.error("All retries failed for conversation %s: %s",
                 conv_id, last_exc)
    return ConversationAnalysisResult(conversation_id=conv_id)
