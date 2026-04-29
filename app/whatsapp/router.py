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
    # True = WhatsApp Business; False = personal account; None = not yet checked.
    # A personal account CAN be connected but the analytics will still work —
    # we surface this as a UI warning so the user knows to switch to WA Business.
    is_business_account: bool | None = None

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

    # PERSONAL_ACCOUNT_BLOCKED is a terminal state set by business logic — the WAHA session
    # was intentionally destroyed. Polling WAHA here would return 404/STOPPED and incorrectly
    # overwrite this status, causing the UI to show FailedCard instead of the blocked screen.
    if conn.status == WahaSessionStatus.PERSONAL_ACCOUNT_BLOCKED.value:
        return {
            "connection_id": str(connection_id),
            "status": conn.status,
            "phone_number": conn.phone_number,
            "push_name": conn.push_name,
            "is_business_account": conn.is_business_account,
        }

    try:
        info = await waha.get_session(conn.waha_session_name)
        new_status = info.status.value
        updates: dict = {"status": new_status}

        if info.me:
            own_jid = info.me.id  # e.g. "57300...@c.us"
            if not conn.phone_number:
                updates["phone_number"] = own_jid.split("@")[0]
                updates["push_name"] = info.me.pushName or None

            if new_status == WahaSessionStatus.WORKING.value:
                # Phase 1 — first detection of WORKING (transitioning from SCAN_QR_CODE etc.):
                # return CHECKING_ACCOUNT immediately so the frontend shows a loading state
                # within the next 2-second poll cycle instead of blocking for 12+ seconds.
                if conn.status not in (
                    WahaSessionStatus.WORKING.value,
                    WahaSessionStatus.CHECKING_ACCOUNT.value,
                ):
                    updates["status"] = WahaSessionStatus.CHECKING_ACCOUNT.value
                    # User just (re)scanned the QR — clear the reconnect-email dedupe so
                    # any future disconnection sends a fresh notice instead of being silent.
                    updates["last_reconnect_email_sent_at"] = None
                    # Bump session-active so the keepalive scheduler doesn't immediately
                    # re-poke a session that was just brought online.
                    updates["last_session_active_at"] = datetime.now(tz=timezone.utc)
                    await conn_repo.update(conn.id, **updates)
                    await db.commit()
                    return {
                        "connection_id": str(connection_id),
                        "status": WahaSessionStatus.CHECKING_ACCOUNT.value,
                        "phone_number": updates.get("phone_number") or conn.phone_number,
                        "push_name": updates.get("push_name") or conn.push_name,
                        "is_business_account": None,
                    }

                # Phase 2 — already in CHECKING_ACCOUNT: run the business-account check now.
                if conn.status == WahaSessionStatus.CHECKING_ACCOUNT.value:
                    is_biz = await waha.check_is_business_account(conn.waha_session_name, own_jid)
                    updates["is_business_account"] = is_biz

                    if settings.waha_require_business_account and is_biz is False:
                        logger.warning(
                            "Personal WhatsApp account blocked [connection=%s phone=%s]",
                            connection_id, own_jid.split("@")[0],
                        )
                        try:
                            await waha.logout_session(conn.waha_session_name)
                        except WahaError:
                            pass
                        try:
                            await waha.delete_session(conn.waha_session_name)
                        except WahaError:
                            pass

                        await conn_repo.update(
                            conn.id,
                            status=WahaSessionStatus.PERSONAL_ACCOUNT_BLOCKED.value,
                            is_business_account=False,
                        )
                        await db.commit()
                        return {
                            "connection_id": str(connection_id),
                            "status": WahaSessionStatus.PERSONAL_ACCOUNT_BLOCKED.value,
                            "phone_number": own_jid.split("@")[0],
                            "push_name": info.me.pushName or None,
                            "is_business_account": False,
                        }
                # If conn.status == WORKING: business check already done — fall through.

        await conn_repo.update(conn.id, **updates)
        await db.commit()

        is_biz_val = updates.get("is_business_account", getattr(conn, "is_business_account", None))
        return {
            "connection_id": str(connection_id),
            "status": new_status,
            "phone_number": info.me.id.split("@")[0] if info.me else conn.phone_number,
            "push_name": info.me.pushName if info.me else conn.push_name,
            "is_business_account": is_biz_val,
        }
    except WahaSessionNotFoundError:
        # Re-read from DB: a concurrent personal-account-block may have already set
        # PERSONAL_ACCOUNT_BLOCKED and intentionally deleted the session. Don't overwrite it.
        fresh = await conn_repo.get(str(conn.id))
        if fresh and fresh.status == WahaSessionStatus.PERSONAL_ACCOUNT_BLOCKED.value:
            return {
                "connection_id": str(connection_id),
                "status": WahaSessionStatus.PERSONAL_ACCOUNT_BLOCKED.value,
                "phone_number": fresh.phone_number,
                "push_name": fresh.push_name,
                "is_business_account": fresh.is_business_account,
            }
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

    # Terminal state — session was intentionally destroyed, no QR will ever come from it.
    if current_status == WahaSessionStatus.PERSONAL_ACCOUNT_BLOCKED.value:
        raise HTTPException(
            status_code=409,
            detail={"code": "PERSONAL_ACCOUNT_BLOCKED", "message": "Personal WhatsApp accounts are not allowed."},
        )

    # If stopped or starting, wake the session up first
    if current_status in (WahaSessionStatus.STOPPED.value, WahaSessionStatus.STARTING.value):
        try:
            if current_status == WahaSessionStatus.STOPPED.value:
                await waha.start_session(conn.waha_session_name)
            current_status = (await waha.wait_for_working(conn.waha_session_name, timeout_seconds=30)).value
            await conn_repo.update(conn.id, status=current_status)
            await db.commit()
        except WahaSessionNotFoundError:
            # Session was deleted (e.g. during personal-account-block cleanup). Re-check DB before
            # recreating — if it was intentionally blocked, surface that instead.
            fresh = await conn_repo.get(str(conn.id))
            if fresh and fresh.status == WahaSessionStatus.PERSONAL_ACCOUNT_BLOCKED.value:
                raise HTTPException(
                    status_code=409,
                    detail={"code": "PERSONAL_ACCOUNT_BLOCKED", "message": "Personal WhatsApp accounts are not allowed."},
                )
            try:
                session_info = await waha.create_session(conn.waha_session_name, str(conn.client_id))
                current_status = session_info.status.value
                await conn_repo.update(conn.id, status=current_status)
                await db.commit()
            except WahaError as e:
                raise HTTPException(status_code=502, detail=f"Could not recreate WAHA session: {e.message}")
        except WahaError as e:
            raise HTTPException(status_code=502, detail=f"Could not start WAHA session: {e.message}")

    if current_status == WahaSessionStatus.WORKING.value:
        raise HTTPException(
            status_code=409,
            detail={"code": "ALREADY_CONNECTED", "message": "Session is already connected. No QR needed."},
        )

    if current_status != WahaSessionStatus.SCAN_QR_CODE.value:
        # 409 (not 502) so the frontend triggers a status refresh rather than showing FailedCard.
        raise HTTPException(
            status_code=409,
            detail={"code": "SESSION_NOT_READY", "message": f"Session is in state '{current_status}'. QR not available yet."},
        )

    try:
        qr_base64 = await waha.get_qr_base64(conn.waha_session_name)
    except WahaError as e:
        # WAHA rejected the QR fetch (session moved out of SCAN_QR_CODE between our check and the call).
        # Sync the live status to DB so the next status poll reflects reality immediately.
        try:
            live = await waha.get_session(conn.waha_session_name)
            await conn_repo.update(conn.id, status=live.status.value)
            await db.commit()
        except WahaError:
            pass
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

    # Block only if there's an active sync running RIGHT NOW.
    # If a previous sync got stuck pending/processing for >15 min, treat it as
    # orphaned (worker crashed) and allow a new attempt — otherwise the user
    # would be permanently locked out by a single bad sync.
    if conn.last_sync_job_id:
        last_job = await AnalysisJobRepository(db).get(str(conn.last_sync_job_id))
        if last_job and last_job.status in ("pending", "processing"):
            job_created = last_job.created_at
            if job_created.tzinfo is None:
                job_created = job_created.replace(tzinfo=timezone.utc)
            age_minutes = (datetime.now(tz=timezone.utc) - job_created).total_seconds() / 60
            if age_minutes < 15:
                raise HTTPException(
                    status_code=409,
                    detail={"code": "SYNC_IN_PROGRESS", "message": "Ya hay un sync en curso. Espera a que termine."},
                )
            # Orphaned: mark the stuck job as failed so it won't keep blocking
            await AnalysisJobRepository(db).update(
                str(last_job.id), status="failed",
                error_message="Sync orphaned (no completion within 15 min)",
            )
            await db.commit()

    # Anti-spam guard: minimum 2 minutes between manual syncs to prevent rapid
    # double-clicks and give the WAHA session time to be torn down between runs.
    # The plan-based interval (biweekly/monthly) only applies to the AUTO scheduler;
    # manual syncs are gated solely by the billing quota below.
    if conn.last_sync_at is not None:
        now_utc = datetime.now(tz=timezone.utc)
        last = conn.last_sync_at if conn.last_sync_at.tzinfo else conn.last_sync_at.replace(tzinfo=timezone.utc)
        next_allowed = last + timedelta(minutes=2)
        if now_utc < next_allowed:
            seconds_left = int((next_allowed - now_utc).total_seconds())
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "TOO_SOON",
                    "message": f"Espera {seconds_left} segundos antes de generar otro reporte.",
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


