import io
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, assert_client_owner, get_current_user
from app.dependencies import get_db
from app.exceptions import ReportGenerationError
from app.models.schemas import AnalysisResultResponse, ConversationAnalysisResult, DashboardOverview
from app.repositories.analysis_repo import AnalysisJobRepository, ConversationAnalysisRepository

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Delivery"])


@router.get("/reports/{job_id}/status")
async def report_status(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    job = await AnalysisJobRepository(db).get(str(job_id))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await assert_client_owner(job.client_id, user, db)
    return {
        "job_id": str(job_id),
        "ready": job.status == "completed",
        "status": job.status,
    }


@router.get("/reports/{job_id}/download")
async def download_report(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> Response:
    job_repo = AnalysisJobRepository(db)
    analysis_repo = ConversationAnalysisRepository(db)

    job = await job_repo.get(str(job_id))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await assert_client_owner(job.client_id, user, db)
    if job.status != "completed":
        raise HTTPException(status_code=425, detail="Report not ready yet. Check /reports/{job_id}/status")

    # Load analyses joined with conversation + contact so the PDF can:
    #   • Dedupe sessions per chat for the "Sin Responder" KPI
    #   • Render readable references on "Conversaciones Destacadas" cards
    rows = await analysis_repo.list_by_job_with_contact(str(job_id))

    from app.models.schemas import QualityBreakdown
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
            # Computed metrics
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
            # Deterministic ack-based metrics
            delivery_rate=getattr(a, "delivery_rate", None),
            read_rate=getattr(a, "read_rate", None),
            is_ghosted=bool(getattr(a, "is_ghosted", False)),
            last_business_msg_ack=getattr(a, "last_business_msg_ack", None),
            operational_coverage_score=getattr(a, "operational_coverage_score", None),
            out_of_hours_inbound_pct=getattr(a, "out_of_hours_inbound_pct", None),
            wa_unread_count=getattr(a, "wa_unread_count", None),
            wa_is_muted=bool(getattr(a, "wa_is_muted", False)),
            wa_is_archived=bool(getattr(a, "wa_is_archived", False)),
        )
        for (a, conv, contact) in rows
    ]

    try:
        from app.delivery.reports.pdf_generator import generate_pdf_report

        # Get business name from client
        from app.repositories.client_repo import ClientRepository
        client_repo = ClientRepository(db)
        client = await client_repo.get(job.client_id)
        business_name = client.business_name if client else "Business"

        # F1 — fetch the immediately previous COMPLETED job for this client so
        # the PDF can render a "vs reporte anterior" comparison block. We pick
        # the most recent completed job whose created_at < this job's created_at.
        previous_results: list[ConversationAnalysisResult] = []
        previous_job_created_at = None
        try:
            sibling_jobs = await job_repo.list_by_client(str(job.client_id))
            prev_job = next(
                (j for j in sibling_jobs
                 if j.status == "completed"
                 and j.id != job.id
                 and j.created_at < job.created_at),
                None,
            )
            if prev_job is not None:
                prev_analyses = await analysis_repo.list_by_job(str(prev_job.id))
                previous_results = [
                    ConversationAnalysisResult(
                        conversation_id=a.conversation_id,
                        sentiment=a.sentiment,
                        sentiment_score=a.sentiment_score,
                        primary_topic=a.primary_topic,
                        quality_score=a.quality_score,
                        conversion_status=a.conversion_status,
                        first_response_time_seconds=a.first_response_time_seconds,
                        avg_response_time_seconds=a.avg_response_time_seconds,
                        unanswered_count=a.unanswered_count or 0,
                        total_messages=a.total_messages or 0,
                        operational_coverage_score=getattr(a, "operational_coverage_score", None),
                    )
                    for a in prev_analyses
                ]
                previous_job_created_at = prev_job.created_at
        except Exception:
            logger.warning("Could not load previous job for comparison (job=%s)", job_id, exc_info=True)

        pdf_bytes = generate_pdf_report(
            results=results,
            business_name=business_name,
            job_id=str(job_id),
            ai_model=job.ai_model or "unknown",
            average_transaction_value=client.average_transaction_value if client else None,
            business_type=client.business_type if client else None,
            previous_results=previous_results,
            previous_job_created_at=previous_job_created_at,
        )
    except Exception as exc:
        logger.exception("PDF generation failed for job %s", job_id)
        raise ReportGenerationError(str(job_id), str(exc)) from exc

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="deeplook-report-{job_id}.pdf"'},
    )


# --- Dashboard endpoints (Phase 2 — stubs) ---

@router.get("/dashboard/overview", response_model=DashboardOverview, tags=["Dashboard"])
async def dashboard_overview(db: AsyncSession = Depends(get_db)) -> DashboardOverview:
    """Dashboard summary (Phase 2 — stub)."""
    return DashboardOverview()


@router.get("/dashboard/sentiment", tags=["Dashboard"])
async def dashboard_sentiment(period: str = "30d") -> dict:
    """Sentiment over time (Phase 2 — stub)."""
    return {"period": period, "data": []}


@router.get("/dashboard/response-times", tags=["Dashboard"])
async def dashboard_response_times(period: str = "30d") -> dict:
    """Response time trends (Phase 2 — stub)."""
    return {"period": period, "data": []}


@router.get("/dashboard/topics", tags=["Dashboard"])
async def dashboard_topics(period: str = "30d") -> dict:
    """Topic breakdown (Phase 2 — stub)."""
    return {"period": period, "data": []}


@router.get("/dashboard/conversations", tags=["Dashboard"])
async def dashboard_conversations(status: str = "all") -> dict:
    """Conversation list (Phase 2 — stub)."""
    return {"status": status, "conversations": []}


@router.get("/dashboard/alerts", tags=["Dashboard"])
async def dashboard_alerts() -> dict:
    """Active alerts (Phase 2 — stub)."""
    return {"alerts": []}
