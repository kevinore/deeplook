from datetime import datetime, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import TrialCode
from app.repositories.base import BaseRepository


class TrialCodeRepository(BaseRepository[TrialCode]):
    def __init__(self, session: AsyncSession):
        super().__init__(TrialCode, session)

    async def get_by_code(self, code: str) -> TrialCode | None:
        result = await self.session.execute(
            select(TrialCode).where(TrialCode.code == code)
        )
        return result.scalar_one_or_none()

    async def claim(self, code: str, client_id: str) -> TrialCode | None:
        """
        Atomic claim: increments claims_count only if the code is active, has
        remaining capacity (claims_count < max_claims), and is within its
        redemption window. Returns the updated TrialCode on success, or None if
        the code is exhausted, inactive, expired, or non-existent.

        Postgres serializes concurrent UPDATEs on the same row, so two callers
        racing on the last available slot can never both succeed. `expires_at IS
        NULL` means the code has no redemption deadline.
        """
        now = datetime.now(tz=timezone.utc)
        stmt = (
            update(TrialCode)
            .where(
                TrialCode.code == code,
                TrialCode.is_active == True,  # noqa: E712
                TrialCode.claims_count < TrialCode.max_claims,
                or_(TrialCode.expires_at.is_(None), TrialCode.expires_at > now),
            )
            .values(claims_count=TrialCode.claims_count + 1)
        )
        result = await self.session.execute(stmt)
        if result.rowcount == 0:
            return None
        return await self.get_by_code(code)
