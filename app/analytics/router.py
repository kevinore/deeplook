import statistics
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.insights.health_score import calculate_health_score, get_health_score_breakdown
from app.auth.dependencies import CurrentUser, assert_client_owner, get_current_user
from app.dependencies import get_db
from app.models.enums import AnalysisStatus, ConversionStatus, Sentiment
from app.models.schemas import (
    AnalysisResultResponse,
    ConversationAnalysisResult,
    HealthDimension,
    JobStatusResponse,
    JobTrendPoint,
    TopicFrequency,
    TrendsResponse,
    TrendsSummary,
)
from app.repositories.analysis_repo import AnalysisJobRepository, ConversationAnalysisRepository
from app.repositories.client_repo import ClientRepository
from app.repositories.conversation_repo import ConversationRepository

router = APIRouter(tags=["Analytics"])


@router.get("/jobs", response_model=list[JobStatusResponse])
async def list_jobs(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> list[JobStatusResponse]:
    """List all analysis jobs for the authenticated user's clients, newest first."""
    clients = await ClientRepository(db).list_by_owner(user.user_id)
    if not clients:
        return []

    all_jobs = []
    for client in clients:
        all_jobs.extend(await AnalysisJobRepository(db).list_by_client(str(client.id)))

    all_jobs.sort(key=lambda j: j.created_at, reverse=True)

    results = []
    for job in all_jobs:
        total = job.total_conversations
        processed = job.processed_conversations
        progress = (processed / total * 100) if total > 0 else 0.0
        report_url = f"/api/v1/reports/{job.id}/download" if job.status == "completed" else None
        results.append(
            JobStatusResponse(
                job_id=job.id,
                status=AnalysisStatus(job.status),
                total_conversations=total,
                processed_conversations=processed,
                progress_percent=round(progress, 1),
                error_message=job.error_message,
                report_url=report_url,
                created_at=job.created_at,
                total_tokens_used=job.total_tokens_used,
                total_cost_usd=job.total_cost_usd,
                ai_provider=job.ai_provider,
                ai_model=job.ai_model,
            )
        )
    return results


async def _get_job_or_404(job_id: str, db: AsyncSession):
    job = await AnalysisJobRepository(db).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> JobStatusResponse:
    job = await _get_job_or_404(str(job_id), db)
    await assert_client_owner(job.client_id, user, db)

    total = job.total_conversations
    processed = job.processed_conversations
    progress = (processed / total * 100) if total > 0 else 0.0

    report_url = f"/api/v1/reports/{job_id}/download" if job.status == "completed" else None

    return JobStatusResponse(
        job_id=job_id,
        status=AnalysisStatus(job.status),
        total_conversations=total,
        processed_conversations=processed,
        progress_percent=round(progress, 1),
        error_message=job.error_message,
        report_url=report_url,
        created_at=job.created_at,
        total_tokens_used=job.total_tokens_used,
        total_cost_usd=job.total_cost_usd,
        ai_provider=job.ai_provider,
        ai_model=job.ai_model,
    )


@router.get("/jobs/{job_id}/results", response_model=AnalysisResultResponse)
async def get_job_results(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> AnalysisResultResponse:
    job = await _get_job_or_404(str(job_id), db)
    await assert_client_owner(job.client_id, user, db)

    analyses = await ConversationAnalysisRepository(db).list_by_job(str(job_id))

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
            # Metric fields needed for health score calculation
            total_messages=a.total_messages,
            unanswered_count=a.unanswered_count,
            trailing_inbound_messages=getattr(a, "trailing_inbound_messages", 0) or 0,
            inbound_count=a.inbound_count,
            outbound_count=a.outbound_count,
            first_response_time_seconds=a.first_response_time_seconds,
            avg_response_time_seconds=a.avg_response_time_seconds,
            # Deterministic ack-based + operational metrics
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
        for a in analyses
    ]

    # Use the exact same formula as the PDF generator
    frt_values = [r.first_response_time_seconds for r in conversation_results if r.first_response_time_seconds is not None]
    rt_values  = [r.avg_response_time_seconds   for r in conversation_results if r.avg_response_time_seconds   is not None]
    avg_first_rt = statistics.mean(frt_values) if frt_values else None
    avg_rt       = statistics.mean(rt_values)  if rt_values  else None
    overall_health = round(calculate_health_score(
        conversation_results,
        first_response_time_seconds=avg_first_rt,
        avg_response_time_seconds=avg_rt,
    )) if conversation_results else None

    return AnalysisResultResponse(
        job_id=str(job_id),
        client_id=job.client_id,
        status=AnalysisStatus(job.status),
        total_conversations=job.total_conversations,
        conversations=conversation_results,
        overall_health_score=overall_health,
        total_tokens_used=job.total_tokens_used,
        total_cost_usd=job.total_cost_usd,
    )


@router.post("/analyze/{conversation_id}", status_code=202)
async def reanalyze_conversation(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Re-analyze a single conversation. Returns accepted status."""
    conv = await ConversationRepository(db).get(str(conversation_id))
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await assert_client_owner(conv.client_id, user, db)

    return {"status": "accepted", "conversation_id": str(conversation_id)}


_MONTH_ES = {1:'Ene',2:'Feb',3:'Mar',4:'Abr',5:'May',6:'Jun',7:'Jul',8:'Ago',9:'Sep',10:'Oct',11:'Nov',12:'Dic'}


@router.get("/trends", response_model=TrendsResponse)
async def get_trends(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> TrendsResponse:
    """Time-series trend data across all completed analysis jobs for the user."""
    clients = await ClientRepository(db).list_by_owner(user.user_id)
    if not clients:
        return TrendsResponse(summary=TrendsSummary())

    client_ids = [str(c.id) for c in clients]
    all_jobs = [
        j for j in await AnalysisJobRepository(db).list_by_clients(client_ids)
        if j.status == "completed"
    ]

    if not all_jobs:
        return TrendsResponse(summary=TrendsSummary())

    all_jobs.sort(key=lambda j: j.created_at)

    trend_points: list[JobTrendPoint] = []
    topic_counter: dict[str, int] = {}
    total_conversations_analyzed = 0  # denominator for topic %, matches PDF logic
    avg_frt_latest: float | None = None
    avg_rt_latest: float | None = None
    latest_results: list[ConversationAnalysisResult] = []

    # Single batch query instead of N+1
    all_job_ids = [str(j.id) for j in all_jobs]
    analyses_by_job = await ConversationAnalysisRepository(db).list_by_jobs(all_job_ids)

    for job in all_jobs:
        analyses_raw = analyses_by_job.get(str(job.id), [])

        # Load every field that calculate_health_score and get_health_score_breakdown
        # need — especially operational_coverage_score, otherwise the trends health
        # score and breakdown don't match the values shown in the PDF / job results.
        results = [
            ConversationAnalysisResult(
                conversation_id=a.conversation_id,
                sentiment=a.sentiment,
                sentiment_score=a.sentiment_score,
                sentiment_reason=a.sentiment_reason,
                primary_topic=a.primary_topic,
                secondary_topics=a.secondary_topics or [],
                quality_score=a.quality_score,
                conversion_status=a.conversion_status,
                total_messages=a.total_messages,
                unanswered_count=a.unanswered_count or 0,
                trailing_inbound_messages=getattr(a, "trailing_inbound_messages", 0) or 0,
                inbound_count=a.inbound_count,
                outbound_count=a.outbound_count,
                first_response_time_seconds=a.first_response_time_seconds,
                avg_response_time_seconds=a.avg_response_time_seconds,
                operational_coverage_score=getattr(a, "operational_coverage_score", None),
            )
            for a in analyses_raw
        ]

        frt_values = [r.first_response_time_seconds for r in results if r.first_response_time_seconds is not None]
        rt_values  = [r.avg_response_time_seconds   for r in results if r.avg_response_time_seconds   is not None]
        avg_frt = statistics.mean(frt_values) if frt_values else None
        avg_rt  = statistics.mean(rt_values)  if rt_values  else None

        health = round(calculate_health_score(results, first_response_time_seconds=avg_frt, avg_response_time_seconds=avg_rt), 1) if results else None

        total = len(results)
        total_conversations_analyzed += total
        pos = sum(1 for r in results if r.sentiment == Sentiment.POSITIVE)
        neu = sum(1 for r in results if r.sentiment == Sentiment.NEUTRAL)
        neg = sum(1 for r in results if r.sentiment == Sentiment.NEGATIVE)

        applicable_list = [r for r in results if r.conversion_status and r.conversion_status != ConversionStatus.NOT_APPLICABLE]
        converted_list  = [r for r in applicable_list if r.conversion_status == ConversionStatus.CONVERTED]
        conv_rate = round(len(converted_list) / len(applicable_list) * 100, 1) if applicable_list else None

        q_vals = [r.quality_score for r in results if r.quality_score is not None]
        avg_quality = round(sum(q_vals) / len(q_vals), 1) if q_vals else None

        # Count primary_topic only — must match the topic counting in
        # pdf_generator.py and recommendations.py so percentages line up.
        for r in results:
            if r.primary_topic:
                topic_counter[r.primary_topic] = topic_counter.get(r.primary_topic, 0) + 1

        dt = job.created_at
        label = f"{_MONTH_ES.get(dt.month, '')} {dt.day}"

        trend_points.append(JobTrendPoint(
            job_id=str(job.id),
            date=dt.isoformat(),
            label=label,
            health_score=health,
            total_conversations=job.total_conversations,
            avg_response_time_min=round(avg_rt / 60, 1) if avg_rt is not None else None,
            first_response_time_min=round(avg_frt / 60, 1) if avg_frt is not None else None,
            positive_pct=round(pos / total * 100, 1) if total > 0 else 0.0,
            neutral_pct=round(neu / total * 100, 1) if total > 0 else 0.0,
            negative_pct=round(neg / total * 100, 1) if total > 0 else 0.0,
            conversion_rate=conv_rate,
            avg_quality_score=avg_quality,
            converted_count=len(converted_list),
            applicable_count=len(applicable_list),
            top_topics=[r.primary_topic for r in results if r.primary_topic][:5],
        ))

        # Always overwrite so last job wins
        latest_results = results
        avg_frt_latest = avg_frt
        avg_rt_latest  = avg_rt

    # Health breakdown for latest job
    breakdown_raw = get_health_score_breakdown(latest_results, first_response_time_seconds=avg_frt_latest, avg_response_time_seconds=avg_rt_latest) if latest_results else []
    health_breakdown = [HealthDimension(**d) for d in breakdown_raw]

    # Top topics across all jobs.
    # Denominator is the number of analyzed conversations (not raw mention count),
    # matching pdf_generator.py and recommendations.py:
    #     topic_pct = top_count / len(results) * 100
    top_topics = [
        TopicFrequency(label=t, count=c, pct=round(c / total_conversations_analyzed * 100, 1))
        for t, c in sorted(topic_counter.items(), key=lambda x: x[1], reverse=True)[:8]
    ] if total_conversations_analyzed > 0 else []

    # Trend direction (last 2 completed jobs)
    health_scores = [p.health_score for p in trend_points if p.health_score is not None]
    trend_direction = "stable"
    if len(health_scores) >= 2:
        delta = health_scores[-1] - health_scores[-2]
        trend_direction = "up" if delta >= 3 else ("down" if delta <= -3 else "stable")

    all_health = [p.health_score for p in trend_points if p.health_score is not None]
    summary = TrendsSummary(
        total_reports=len(trend_points),
        total_conversations=sum(p.total_conversations for p in trend_points),
        latest_health_score=trend_points[-1].health_score if trend_points else None,
        latest_label=trend_points[-1].label if trend_points else None,
        avg_health_score=round(sum(all_health) / len(all_health), 1) if all_health else None,
        trend_direction=trend_direction,
        health_breakdown=health_breakdown,
        top_topics=top_topics,
    )

    return TrendsResponse(jobs=trend_points, summary=summary)
