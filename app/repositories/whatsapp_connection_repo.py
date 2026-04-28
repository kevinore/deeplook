from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import Client, WhatsAppConnection
from app.repositories.base import BaseRepository


class WhatsAppConnectionRepository(BaseRepository[WhatsAppConnection]):
    def __init__(self, session: AsyncSession):
        super().__init__(WhatsAppConnection, session)

    async def get_by_client(self, client_id: str) -> WhatsAppConnection | None:
        result = await self.session.execute(
            select(WhatsAppConnection).where(WhatsAppConnection.client_id == client_id)
        )
        return result.scalar_one_or_none()

    async def get_by_session_name(self, session_name: str) -> WhatsAppConnection | None:
        result = await self.session.execute(
            select(WhatsAppConnection).where(WhatsAppConnection.waha_session_name == session_name)
        )
        return result.scalar_one_or_none()

    async def get_pending_syncs(self, now: datetime) -> list[WhatsAppConnection]:
        """Return connections whose scheduled sync is due and whose client has an active plan."""
        result = await self.session.execute(
            select(WhatsAppConnection)
            .join(Client, WhatsAppConnection.client_id == Client.id)
            .where(
                WhatsAppConnection.next_scheduled_sync_at <= now,
                WhatsAppConnection.status.in_(["WORKING", "STOPPED"]),
                Client.plan != "free",
                Client.is_active == True,  # noqa: E712
            )
        )
        return list(result.scalars().all())
