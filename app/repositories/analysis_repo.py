from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import AnalysisJob, ConversationAnalysis, DailyMetrics
from app.repositories.base import BaseRepository


class AnalysisJobRepository(BaseRepository[AnalysisJob]):
    def __init__(self, session: AsyncSession):
        super().__init__(AnalysisJob, session)

    async def list_by_client(self, client_id: str) -> list[AnalysisJob]:
        result = await self.session.execute(
            select(AnalysisJob)
            .where(AnalysisJob.client_id == client_id)
            .order_by(AnalysisJob.created_at.desc())
        )
        return list(result.scalars().all())

    async def increment_processed(self, job_id: str) -> None:
        job = await self.get(job_id)
        if job:
            job.processed_conversations += 1
            await self.session.flush()

    async def add_token_usage(self, job_id: str, tokens: int, cost: float) -> None:
        job = await self.get(job_id)
        if job:
            job.total_tokens_used += tokens
            job.total_cost_usd += cost
            await self.session.flush()


class ConversationAnalysisRepository(BaseRepository[ConversationAnalysis]):
    def __init__(self, session: AsyncSession):
        super().__init__(ConversationAnalysis, session)

    async def get_by_conversation(self, conversation_id: str) -> ConversationAnalysis | None:
        result = await self.session.execute(
            select(ConversationAnalysis)
            .where(ConversationAnalysis.conversation_id == conversation_id)
            .order_by(ConversationAnalysis.analyzed_at.desc())
        )
        return result.scalars().first()

    async def list_by_job(self, job_id: str) -> list[ConversationAnalysis]:
        result = await self.session.execute(
            select(ConversationAnalysis)
            .where(ConversationAnalysis.analysis_job_id == job_id)
        )
        return list(result.scalars().all())


class DailyMetricsRepository(BaseRepository[DailyMetrics]):
    def __init__(self, session: AsyncSession):
        super().__init__(DailyMetrics, session)

    async def get_by_date(self, client_id: str, metrics_date: date) -> DailyMetrics | None:
        result = await self.session.execute(
            select(DailyMetrics)
            .where(DailyMetrics.client_id == client_id, DailyMetrics.date == metrics_date)
        )
        return result.scalar_one_or_none()

    async def list_by_client(self, client_id: str, limit: int = 90) -> list[DailyMetrics]:
        result = await self.session.execute(
            select(DailyMetrics)
            .where(DailyMetrics.client_id == client_id)
            .order_by(DailyMetrics.date.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
