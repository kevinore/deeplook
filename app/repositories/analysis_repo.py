from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import AnalysisJob, Contact, Conversation, ConversationAnalysis, DailyMetrics
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

    async def count_by_client_this_period(self, client_id: str, period_start: datetime) -> int:
        """Count non-failed jobs since period_start (used for quota enforcement)."""
        result = await self.session.execute(
            select(func.count(AnalysisJob.id)).where(
                AnalysisJob.client_id == client_id,
                AnalysisJob.created_at >= period_start,
                AnalysisJob.status.in_(["pending", "processing", "completed"]),
            )
        )
        return result.scalar() or 0

    async def list_by_clients(self, client_ids: list[str]) -> list[AnalysisJob]:
        """Single batch query for multiple clients."""
        if not client_ids:
            return []
        result = await self.session.execute(
            select(AnalysisJob)
            .where(AnalysisJob.client_id.in_(client_ids))
            .order_by(AnalysisJob.created_at.asc())
        )
        return list(result.scalars().all())

    async def increment_processed(self, job_id: str) -> None:
        job = await self.get(job_id)
        if job:
            job.processed_conversations += 1
            await self.session.flush()

    async def add_token_usage(
        self, job_id: str, tokens_input: int, tokens_output: int, cost: float
    ) -> None:
        job = await self.get(job_id)
        if job:
            job.total_tokens_input += tokens_input
            job.total_tokens_output += tokens_output
            job.total_tokens_used += tokens_input + tokens_output
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

    async def list_by_jobs(self, job_ids: list[str]) -> dict[str, list[ConversationAnalysis]]:
        """Single batch query for multiple jobs. Returns {job_id: [analyses]} dict."""
        if not job_ids:
            return {}
        result = await self.session.execute(
            select(ConversationAnalysis)
            .join(Conversation, ConversationAnalysis.conversation_id == Conversation.id)
            .where(ConversationAnalysis.analysis_job_id.in_(job_ids))
            .order_by(Conversation.started_at.asc(), ConversationAnalysis.conversation_id.asc())
        )
        grouped: dict[str, list[ConversationAnalysis]] = {}
        for analysis in result.scalars().all():
            jid = str(analysis.analysis_job_id)
            grouped.setdefault(jid, []).append(analysis)
        return grouped

    async def list_by_job(self, job_id: str) -> list[ConversationAnalysis]:
        """
        Return analyses for this job ordered by conversation start time (chronological).
        Stable sort: started_at ASC, conversation_id ASC as tiebreaker.
        This guarantees the same PDF is produced every time the report is downloaded.
        """
        result = await self.session.execute(
            select(ConversationAnalysis)
            .join(Conversation, ConversationAnalysis.conversation_id == Conversation.id)
            .where(ConversationAnalysis.analysis_job_id == job_id)
            .order_by(Conversation.started_at.asc(), ConversationAnalysis.conversation_id.asc())
        )
        return list(result.scalars().all())

    async def list_by_job_with_contact(
        self, job_id: str
    ) -> list[tuple[ConversationAnalysis, Conversation, Contact]]:
        """
        Return (analysis, conversation, contact) tuples for the job, in chronological
        order. Used by the PDF generator to:
          • Aggregate "sin responder" at the chat level (dedupe sessions per contact)
          • Render contact references on the "Conversaciones Destacadas" cards
        """
        result = await self.session.execute(
            select(ConversationAnalysis, Conversation, Contact)
            .join(Conversation, ConversationAnalysis.conversation_id == Conversation.id)
            .join(Contact, Conversation.contact_id == Contact.id)
            .where(ConversationAnalysis.analysis_job_id == job_id)
            .order_by(Conversation.started_at.asc(), ConversationAnalysis.conversation_id.asc())
        )
        return list(result.all())


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
