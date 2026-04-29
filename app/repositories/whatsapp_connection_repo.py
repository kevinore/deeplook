from datetime import datetime

from sqlalchemy import or_, select
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

    async def get_due_keepalives(self, cutoff: datetime) -> list[WhatsAppConnection]:
        """
        Return connections that need a keepalive ping — i.e., connections that
        have been idle (no sync, no prior keepalive) since `cutoff`. Skips
        already-broken sessions (SCAN_QR_CODE / FAILED) since those need
        user action; pinging them won't help.

        Pre-paired sessions with no `last_session_active_at` (e.g., brand-new
        connections that never synced) are intentionally NOT picked up — they
        either get their first sync soon, or there's nothing to keep alive.
        """
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
