from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, get_current_user
from app.dependencies import get_db
from app.repositories.client_repo import ClientRepository
from app.repositories.notification_repo import NotificationRepository

router = APIRouter(prefix="/notifications", tags=["Notifications"])


class NotificationOut(BaseModel):
    id: str
    type: str
    title: str
    body: str
    is_read: bool
    job_id: str | None = None
    extra_data: dict = {}
    created_at: datetime

    model_config = {"from_attributes": True}


async def _get_client_id(user: CurrentUser, db: AsyncSession) -> str:
    clients = await ClientRepository(db).list_by_owner(user.user_id)
    if not clients:
        raise HTTPException(status_code=404, detail="Client not found.")
    return str(clients[0].id)


@router.get("", response_model=list[NotificationOut])
async def list_notifications(
    limit: int = 20,
    unread_only: bool = False,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> list[NotificationOut]:
    client_id = await _get_client_id(user, db)
    items = await NotificationRepository(db).list_for_client(
        client_id, limit=min(limit, 50), unread_only=unread_only
    )
    return [NotificationOut.model_validate(n) for n in items]


@router.patch("/{notification_id}/read", status_code=204)
async def mark_notification_read(
    notification_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> None:
    client_id = await _get_client_id(user, db)
    ok = await NotificationRepository(db).mark_read(str(notification_id), client_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Notification not found.")
    await db.commit()


@router.post("/read-all", status_code=204)
async def mark_all_notifications_read(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> None:
    client_id = await _get_client_id(user, db)
    await NotificationRepository(db).mark_all_read(client_id)
    await db.commit()
