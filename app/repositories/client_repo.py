from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import Client
from app.repositories.base import BaseRepository


class ClientRepository(BaseRepository[Client]):
    def __init__(self, session: AsyncSession):
        super().__init__(Client, session)

    async def get_by_email(self, email: str) -> Client | None:
        result = await self.session.execute(
            select(Client).where(Client.email == email)
        )
        return result.scalar_one_or_none()

    async def list_active(self) -> list[Client]:
        result = await self.session.execute(
            select(Client).where(Client.is_active == True)  # noqa: E712
        )
        return list(result.scalars().all())

    async def soft_delete(self, client_id: str) -> bool:
        instance = await self.get(client_id)
        if instance is None:
            return False
        instance.is_active = False
        await self.session.flush()
        return True
