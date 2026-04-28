from datetime import datetime, timezone

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

    async def list_by_owner(self, clerk_user_id: str) -> list[Client]:
        result = await self.session.execute(
            select(Client).where(
                Client.clerk_user_id == clerk_user_id,
                Client.is_active == True,  # noqa: E712
            )
        )
        return list(result.scalars().all())

    async def get_by_owner(self, client_id: str, clerk_user_id: str) -> Client | None:
        """Return a client only when it's active and owned by clerk_user_id."""
        result = await self.session.execute(
            select(Client).where(
                Client.id == client_id,
                Client.clerk_user_id == clerk_user_id,
                Client.is_active == True,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def soft_delete(self, client_id: str) -> bool:
        instance = await self.get(client_id)
        if instance is None:
            return False
        instance.is_active = False
        await self.session.flush()
        return True

    async def enforce_expiry(self, client: Client) -> bool:
        """
        Downgrade to free if plan_expires_at has passed.
        Returns True if the plan was just downgraded.
        Call this before serving any quota-sensitive response.
        """
        if client.plan == "free" or client.plan_expires_at is None:
            return False
        now = datetime.now(tz=timezone.utc)
        expires = client.plan_expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if now >= expires:
            client.plan = "free"
            client.subscription_status = "inactive"
            client.plan_expires_at = None
            await self.session.flush()
            return True
        return False
