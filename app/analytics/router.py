from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.enums import AnalysisStatus
from app.models.schemas import AnalysisResultResponse, ConversationAnalysisResult, JobStatusResponse
from app.repositories.analysis_repo import AnalysisJobRepository, ConversationAnalysisRepository
from app.repositories.conversation_repo import ConversationRepository, MessageRepository

router = APIRouter(tags=["Analytics"])


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> JobStatusResponse:
    repo = AnalysisJobRepository(db)
    job = await repo.get(str(job_id))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    total = job.total_conversations
    processed = job.processed_conversations
    progress = (processed / total * 100) if total > 0 else 0.0

    report_url = None
    if job.status == "completed":
        report_url = f"/api/v1/reports/{job_id}/download"

    return JobStatusResponse(
        job_id=job_id,
        status=AnalysisStatus(job.status),
        total_conversations=total,
        processed_conversations=processed,
        progress_percent=round(progress, 1),
        error_message=job.error_message,
        report_url=report_url,
    )


@router.get("/jobs/{job_id}/results", response_model=AnalysisResultResponse)
async def get_job_results(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> AnalysisResultResponse:
    job_repo = AnalysisJobRepository(db)
    analysis_repo = ConversationAnalysisRepository(db)

    job = await job_repo.get(str(job_id))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    analyses = await analysis_repo.list_by_job(str(job_id))

    conversation_results = [
        ConversationAnalysisResult(
            conversation_id=a.conversation_id,
            sentiment=a.sentiment,
            sentiment_score=a.sentiment_score,
            sentiment_reason=a.sentiment_reason,
            primary_topic=a.primary_topic,
            secondary_topics=a.secondary_topics or [],
            quality_score=a.quality_score,
            conversion_status=a.conversion_status,
            conversion_reason=a.conversion_reason,
            summary=a.summary,
            key_points=a.key_points or [],
            ai_provider=a.ai_provider,
            ai_model=a.ai_model,
            tokens_used=a.tokens_used,
            analysis_cost_usd=a.analysis_cost_usd,
        )
        for a in analyses
    ]

    return AnalysisResultResponse(
        job_id=str(job_id),
        client_id=job.client_id,
        status=AnalysisStatus(job.status),
        total_conversations=job.total_conversations,
        conversations=conversation_results,
        total_tokens_used=job.total_tokens_used,
        total_cost_usd=job.total_cost_usd,
    )


@router.post("/analyze/{conversation_id}", status_code=202)
async def reanalyze_conversation(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Re-analyze a single conversation. Returns accepted status."""
    conv_repo = ConversationRepository(db)
    conv = await conv_repo.get(str(conversation_id))
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return {"status": "accepted", "conversation_id": str(conversation_id)}
