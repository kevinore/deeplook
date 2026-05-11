import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import Client, WhatsAppConnection
from app.repositories.base import BaseRepository


class WhatsAppConnectionRepository(BaseRepository[WhatsAppConnection]):
    def __init__(self, session: AsyncSession):
        super().__init__(WhatsAppConnection, session)

    async def list_by_client(self, client_id: str) -> list[WhatsAppConnection]:
        result = await self.session.execute(
            select(WhatsAppConnection)
            .where(WhatsAppConnection.client_id == client_id)
            .order_by(WhatsAppConnection.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_by_session_name(self, session_name: str) -> WhatsAppConnection | None:
        result = await self.session.execute(
            select(WhatsAppConnection).where(WhatsAppConnection.waha_session_name == session_name)
        )
        return result.scalar_one_or_none()

    async def get_by_share_token(self, token: str) -> WhatsAppConnection | None:
        now = datetime.now(tz=timezone.utc)
        result = await self.session.execute(
            select(WhatsAppConnection).where(
                WhatsAppConnection.share_token == token,
                WhatsAppConnection.share_token_expires_at > now,
            )
        )
        return result.scalar_one_or_none()

    async def generate_share_token(self, connection_id: str, ttl_hours: int = 24) -> str:
        token = str(uuid.uuid4())
        expires = datetime.now(tz=timezone.utc) + timedelta(hours=ttl_hours)
        await self.update(connection_id, share_token=token, share_token_expires_at=expires)
        return token

    async def invalidate_share_token(self, connection_id: str) -> None:
        await self.update(connection_id, share_token=None, share_token_expires_at=None)

    async def get_pending_syncs(self, now: datetime) -> list[WhatsAppConnection]:
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

    async def get_due_keepalives(self, cutoff: datetime) -> list[WhatsAppConnection]:
        result = await self.session.execute(
            select(WhatsAppConnection)
            .join(Client, WhatsAppConnection.client_id == Client.id)
            .where(
                WhatsAppConnection.status.in_(["WORKING", "STOPPED"]),
                WhatsAppConnection.last_session_active_at.is_not(None),
                WhatsAppConnection.last_session_active_at < cutoff,
                Client.plan != "free",
                Client.is_active == True,  # noqa: E712
            )
        )
        return list(result.scalars().all())
