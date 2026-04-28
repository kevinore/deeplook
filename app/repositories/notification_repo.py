from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import Notification
from app.repositories.base import BaseRepository


class NotificationRepository(BaseRepository[Notification]):
    def __init__(self, session: AsyncSession):
        super().__init__(Notification, session)

    async def list_for_client(
        self, client_id: str, limit: int = 20, unread_only: bool = False
    ) -> list[Notification]:
        stmt = select(Notification).where(Notification.client_id == client_id)
        if unread_only:
            stmt = stmt.where(Notification.is_read == False)  # noqa: E712
        stmt = stmt.order_by(Notification.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def mark_read(self, notification_id: str, client_id: str) -> bool:
        n = await self.get(notification_id)
        if n is None or str(n.client_id) != str(client_id):
            return False
        n.is_read = True
        await self.session.flush()
        return True

    async def mark_all_read(self, client_id: str) -> None:
        await self.session.execute(
            update(Notification)
            .where(Notification.client_id == client_id, Notification.is_read == False)  # noqa: E712
            .values(is_read=True)
        )
        await self.session.flush()

    async def get_unread_count(self, client_id: str) -> int:
        result = await self.session.execute(
            select(func.count(Notification.id)).where(
                Notification.client_id == client_id,
                Notification.is_read == False,  # noqa: E712
            )
        )
        return result.scalar_one()
