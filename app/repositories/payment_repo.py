from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import PaymentSession
from app.repositories.base import BaseRepository


class PaymentSessionRepository(BaseRepository[PaymentSession]):
    def __init__(self, session: AsyncSession):
        super().__init__(PaymentSession, session)

    async def get_by_reference(self, reference: str) -> PaymentSession | None:
        result = await self.session.execute(
            select(PaymentSession).where(PaymentSession.reference == reference)
        )
        return result.scalar_one_or_none()

    async def list_by_client(self, client_id: str) -> list[PaymentSession]:
        result = await self.session.execute(
            select(PaymentSession)
            .where(PaymentSession.client_id == client_id)
            .order_by(PaymentSession.created_at.desc())
        )
        return list(result.scalars().all())
