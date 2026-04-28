from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import Contact, Conversation
from app.repositories.base import BaseRepository


class ContactRepository(BaseRepository[Contact]):
    def __init__(self, session: AsyncSession):
        super().__init__(Contact, session)

    async def get_by_phone(self, client_id: str, phone: str) -> Contact | None:
        result = await self.session.execute(
            select(Contact).where(Contact.client_id == client_id, Contact.phone == phone)
        )
        return result.scalar_one_or_none()

    async def get_or_create(self, client_id: str, phone: str, name: str | None = None) -> Contact:
        existing = await self.get_by_phone(client_id, phone)
        if existing:
            return existing
        return await self.create(client_id=client_id, phone=phone, name=name)


class ConversationRepository(BaseRepository[Conversation]):
    def __init__(self, session: AsyncSession):
        super().__init__(Conversation, session)

    async def list_by_client(self, client_id: str) -> list[Conversation]:
        result = await self.session.execute(
            select(Conversation)
            .where(Conversation.client_id == client_id)
            .order_by(Conversation.started_at.desc())
        )
        return list(result.scalars().all())

    async def list_by_client_and_source(self, client_id: str, source: str) -> list[Conversation]:
        result = await self.session.execute(
            select(Conversation)
            .where(Conversation.client_id == client_id, Conversation.source == source)
            .order_by(Conversation.started_at.desc())
        )
        return list(result.scalars().all())

    async def list_by_ids(self, ids: list[str]) -> list[Conversation]:
        """Return conversations for the given IDs, sorted by started_at ASC then id ASC."""
        if not ids:
            return []
        result = await self.session.execute(
            select(Conversation)
            .where(Conversation.id.in_(ids))
            .order_by(Conversation.started_at.asc(), Conversation.id.asc())
        )
        return list(result.scalars().all())
