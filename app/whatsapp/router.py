import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, get_current_user
from app.billing.quotas import build_quota_status, get_billing_period
from app.config import settings
from app.dependencies import get_db
from app.integrations.waha.client import WahaClient, get_waha_client
from app.integrations.waha.exceptions import WahaError, WahaRePairingRequiredError, WahaSessionNotFoundError
from app.integrations.waha.models import WahaSessionStatus
from app.models.database import Client
from app.repositories.analysis_repo import AnalysisJobRepository
from app.repositories.client_repo import ClientRepository
from app.repositories.whatsapp_connection_repo import WhatsAppConnectionRepository
from app.services.whatsapp_sync_service import create_pending_job, run_waha_sync_job

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])
logger = logging.getLogger(__name__)


# --- Schemas ---

class ConnectionResponse(BaseModel):
    id: UUID
    client_id: UUID
    status: str
    waha_session_name: str
    phone_number: str | None = None
    push_name: str | None = None
    last_sync_at: datetime | None = None
    next_scheduled_sync_at: datetime | None = None
    sync_frequency: str

    model_config = {"from_attributes": True}


class SyncResponse(BaseModel):
    job_id: str
    status: str = "accepted"


# --- Helpers ---

def _session_name(client_id: str) -> str:
    """
    Session name for WAHA.
    WAHA Core (free): only "default" is allowed — all clients share one session.
    WAHA PLUS: unique name per client, set WAHA_MULTI_SESSION=true to enable.
    """
    if not settings.waha_multi_session:
        return "default"
    return "client_" + client_id.replace("-", "")[:12]


async def _get_client(user: CurrentUser, db: AsyncSession) -> Client:
    clients = await ClientRepository(db).list_by_owner(user.user_id)
    if not clients:
        raise HTTPException(status_code=404, detail="Client profile not found. Complete onboarding first.")
    return clients[0]


async def _require_active_plan(user: CurrentUser, db: AsyncSession) -> Client:
    client = await _get_client(user, db)
    if settings.enforce_billing and client.plan == "free":
        raise HTTPException(
            status_code=402,
            detail={"code": "PAYMENT_REQUIRED", "message": "Upgrade your plan to connect WhatsApp."},
        )
    return client


async def _get_connection_or_404(connection_id: str, user: CurrentUser, db: AsyncSession):
    conn = await WhatsAppConnectionRepository(db).get(connection_id)
    if conn is None:
        raise HTTPException(status_code=404, detail="Connection not found.")
    # Verify ownership by checking that the connection's client belongs to the user
    client = await ClientRepository(db).get_by_owner(str(conn.client_id), user.user_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Connection not found.")
    return conn


# --- Endpoints ---

@router.post("/connections", response_model=ConnectionResponse, status_code=201)
async def create_connection(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    waha: WahaClient = Depends(get_waha_client),
) -> ConnectionResponse:
    client = await _require_active_plan(user, db)
    conn_repo = WhatsAppConnectionRepository(db)

    existing = await conn_repo.get_by_client(str(client.id))
    if existing:
        raise HTTPException(status_code=409, detail="A WhatsApp connection already exists for this client.")

    name = _session_name(str(client.id))

    try:
        session_info = await waha.get_or_create_session(name, str(client.id))
    except WahaError as e:
        raise HTTPException(status_code=502, detail=f"Could not create WAHA session: {e.message}")

    # Derive sync_frequency from plan
    _FREQ = {"enterprise": "weekly", "plus": "biweekly"}
    sync_freq = _FREQ.get(client.plan, "monthly")

    conn = await conn_repo.create(
        client_id=str(client.id),
        waha_session_name=name,
        status=session_info.status.value,
        sync_frequency=sync_freq,
    )
    await db.commit()
    await db.refresh(conn)
    return ConnectionResponse.model_validate(conn)


@router.get("/connections", response_model=list[ConnectionResponse])
async def list_connections(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> list[ConnectionResponse]:
    client = await _get_client(user, db)
    conn = await WhatsAppConnectionRepository(db).get_by_client(str(client.id))
    return [ConnectionResponse.model_validate(conn)] if conn else []


@router.get("/connections/{connection_id}/status")
async def get_connection_status(
    connection_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    waha: WahaClient = Depends(get_waha_client),
) -> dict:
    conn = await _get_connection_or_404(str(connection_id), user, db)
    conn_repo = WhatsAppConnectionRepository(db)

    try:
        info = await waha.get_session(conn.waha_session_name)
        new_status = info.status.value
        updates: dict = {"status": new_status}

        if info.me and not conn.phone_number:
            updates["phone_number"] = info.me.id.split("@")[0]
            updates["push_name"] = info.me.pushName or None

        await conn_repo.update(conn.id, **updates)
        await db.commit()

        return {
            "connection_id": str(connection_id),
            "status": new_status,
            "phone_number": info.me.id.split("@")[0] if info.me else conn.phone_number,
            "push_name": info.me.pushName if info.me else conn.push_name,
        }
    except WahaSessionNotFoundError:
        await conn_repo.update(conn.id, status="FAILED")
        await db.commit()
        return {"connection_id": str(connection_id), "status": "FAILED", "phone_number": None, "push_name": None}
    except WahaError as e:
        raise HTTPException(status_code=502, detail=f"WAHA error: {e.message}")


@router.get("/connections/{connection_id}/qr")
async def get_connection_qr(
    connection_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    waha: WahaClient = Depends(get_waha_client),
) -> dict:
    conn = await _get_connection_or_404(str(connection_id), user, db)
    conn_repo = WhatsAppConnectionRepository(db)

    current_status = conn.status

    # If stopped or starting, wake the session up first
    if current_status in (WahaSessionStatus.STOPPED.value, WahaSessionStatus.STARTING.value):
        try:
            if current_status == WahaSessionStatus.STOPPED.value:
                await waha.start_session(conn.waha_session_name)
            current_status = (await waha.wait_for_working(conn.waha_session_name, timeout_seconds=30)).value
            await conn_repo.update(conn.id, status=current_status)
            await db.commit()
        except WahaError as e:
            raise HTTPException(status_code=502, detail=f"Could not start WAHA session: {e.message}")

    if current_status == WahaSessionStatus.WORKING.value:
        raise HTTPException(
            status_code=409,
            detail={"code": "ALREADY_CONNECTED", "message": "Session is already connected. No QR needed."},
        )

    if current_status != WahaSessionStatus.SCAN_QR_CODE.value:
        raise HTTPException(
            status_code=502,
            detail={"code": "SESSION_NOT_READY", "message": f"Unexpected session status: '{current_status}'."},
        )

    try:
        qr_base64 = await waha.get_qr_base64(conn.waha_session_name)
    except WahaError as e:
        raise HTTPException(status_code=502, detail=f"Could not fetch QR: {e.message}")

    expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=20)
    return {"qr_base64": qr_base64, "expires_at": expires_at.isoformat()}


@router.post("/connections/{connection_id}/sync", response_model=SyncResponse, status_code=202)
async def manual_sync(
    connection_id: UUID,
    background_tasks: BackgroundTasks,
    force_full: bool = False,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    waha: WahaClient = Depends(get_waha_client),
) -> SyncResponse:
    conn = await _get_connection_or_404(str(connection_id), user, db)

    # Block if an active sync is already running
    if conn.last_sync_job_id:
        last_job = await AnalysisJobRepository(db).get(str(conn.last_sync_job_id))
        if last_job and last_job.status in ("pending", "processing"):
            raise HTTPException(
                status_code=409,
                detail={"code": "SYNC_IN_PROGRESS", "message": "A sync is already running."},
            )

    # Enforce minimum interval between syncs so Plus/Enterprise reports are
    # spaced correctly (biweekly = 15 days, weekly = 7 days, monthly = 30 days).
    _MIN_DAYS = {"weekly": 7, "biweekly": 15, "monthly": 30}
    min_days = _MIN_DAYS.get(conn.sync_frequency, 30)
    if conn.last_sync_at is not None:
        now_utc = datetime.now(tz=timezone.utc)
        last = conn.last_sync_at if conn.last_sync_at.tzinfo else conn.last_sync_at.replace(tzinfo=timezone.utc)
        next_allowed = last + timedelta(days=min_days)
        if now_utc < next_allowed:
            days_left = (next_allowed - now_utc).days + 1
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "TOO_SOON",
                    "message": f"Tu siguiente reporte estará disponible en {days_left} día{'s' if days_left != 1 else ''}.",
                    "next_sync_at": next_allowed.isoformat(),
                },
            )

    # Enforce billing-period report quota
    client = await _get_client(user, db)
    period_start, _ = get_billing_period(client.plan_started_at)
    jobs_used = await AnalysisJobRepository(db).count_by_client_this_period(str(client.id), period_start)
    quota = build_quota_status(client.plan, jobs_used, client.plan_started_at)
    if quota.reports_remaining == 0:
        renewal = quota.billing_period_end.strftime("%d/%m/%Y")
        raise HTTPException(
            status_code=429,
            detail={
                "code": "QUOTA_EXCEEDED",
                "message": f"Has alcanzado el límite de {quota.reports_limit} reporte(s) para este período. Tu cuota se renueva el {renewal}.",
            },
        )

    # Create the job shell immediately — endpoint returns 202 right away
    job = await create_pending_job(str(connection_id), db)

    # All heavy work (WAHA fetch + store + AI analysis) runs in background
    background_tasks.add_task(
        run_waha_sync_job,
        str(connection_id),
        str(job.id),
        waha,
        force_full,
        "manual",
    )
    return SyncResponse(job_id=str(job.id))


@router.delete("/connections/{connection_id}", status_code=204)
async def delete_connection(
    connection_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    waha: WahaClient = Depends(get_waha_client),
) -> None:
    conn = await _get_connection_or_404(str(connection_id), user, db)
    session_name = conn.waha_session_name

    # NOWEB sessions are stopped between syncs to conserve resources.
    # Calling logout on a stopped session sends no revocation signal to
    # WhatsApp — the linked device would persist on the user's phone.
    # We must start the session first so it reconnects with saved credentials,
    # then logout while the connection is live.
    current_status: WahaSessionStatus | None = None
    try:
        info = await waha.get_session(session_name)
        current_status = info.status
        if current_status not in (WahaSessionStatus.WORKING, WahaSessionStatus.SCAN_QR_CODE):
            await waha.start_session(session_name)
            current_status = await waha.wait_for_working(session_name, timeout_seconds=30)
    except WahaSessionNotFoundError:
        pass  # WAHA has no record — skip straight to DB cleanup
    except WahaError as e:
        logger.warning("WAHA error while starting session for unlink (client=%s): %s", conn.client_id, e.message)

    # Send the logout signal only when we have a live WhatsApp connection.
    # SCAN_QR_CODE means the QR was never scanned — no linked device to revoke.
    if current_status == WahaSessionStatus.WORKING:
        try:
            await waha.logout_session(session_name)
            logger.info("WAHA logout sent for session=%s (client=%s)", session_name, conn.client_id)
        except WahaError as e:
            logger.warning("WAHA logout error during unlink (client=%s): %s", conn.client_id, e.message)

    try:
        await waha.delete_session(session_name)
    except WahaError as e:
        logger.warning("WAHA delete session error during unlink (client=%s): %s", conn.client_id, e.message)

    await WhatsAppConnectionRepository(db).delete(conn.id)
    await db.commit()


