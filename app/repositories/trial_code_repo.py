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
        Atomic single-use claim: marks the code as redeemed only if it is currently
        active, unredeemed, and within its redemption window. Returns the updated
        TrialCode on success, or None if the code was already redeemed, inactive,
        expired, or non-existent.

        Postgres serializes concurrent UPDATEs on the same row, so two callers
        racing on the same code can never both succeed. `expires_at IS NULL`
        means the code has no redemption deadline.
        """
        now = datetime.now(tz=timezone.utc)
        stmt = (
            update(TrialCode)
            .where(
                TrialCode.code == code,
                TrialCode.is_active == True,  # noqa: E712
                TrialCode.redeemed_by_client_id.is_(None),
                or_(TrialCode.expires_at.is_(None), TrialCode.expires_at > now),
            )
            .values(redeemed_by_client_id=client_id, redeemed_at=now)
        )
        result = await self.session.execute(stmt)
        if result.rowcount == 0:
            return None
        return await self.get_by_code(code)
