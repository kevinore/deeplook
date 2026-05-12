import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

import asyncio

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
public_router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])
logger = logging.getLogger(__name__)


# --- Schemas ---

class CreateConnectionRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)


class RenameConnectionRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)


class RequestCodeBody(BaseModel):
    phone_number: str = Field(
        description="Phone number with country code, digits only. E.g. '573178881502'",
        min_length=7,
        max_length=20,
    )




class ConnectionResponse(BaseModel):
    id: UUID
    client_id: UUID
    display_name: str | None = None
    status: str
    waha_session_name: str
    phone_number: str | None = None
    push_name: str | None = None
    last_sync_at: datetime | None = None
    next_scheduled_sync_at: datetime | None = None
    sync_frequency: str
    is_business_account: bool | None = None
    share_token_expires_at: datetime | None = None
    # Populated at query-time (not a DB column).
    active_job_status: str | None = None    # 'pending' | 'processing' | None
    reports_remaining: int | None = None    # remaining quota slots for this connection this period

    model_config = {"from_attributes": True}


class SyncResponse(BaseModel):
    job_id: str
    status: str = "accepted"


class ShareTokenResponse(BaseModel):
    url: str
    expires_at: datetime


# --- Helpers ---

def _session_name(client_id: str, display_name: str, connection_id: str) -> str:
    """
    Human-readable WAHA session name: cl_{client_id[:8]}_{display_name_slug}_{conn[:6]}
    e.g. 'cl_a1b2c3d4_juan_ventas_norte_f7e2c1'
    The connection_id suffix guarantees uniqueness even when display names match.
    WAHA Core (WAHA_MULTI_SESSION=false): always "default" — single session only.
    """
    if not settings.waha_multi_session:
        return "default"
    client_short = client_id.replace("-", "")[:8]
    slug = re.sub(r"[^a-z0-9]+", "_", (display_name or "cuenta").lower()).strip("_")[:18]
    conn_suffix = connection_id.replace("-", "")[:6]
    return f"cl_{client_short}_{slug}_{conn_suffix}"


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
    client = await ClientRepository(db).get_by_owner(str(conn.client_id), user.user_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Connection not found.")
    return conn


# --- Auto-sync helper ---

async def _wait_for_waha_store(session_name: str, waha_client: WahaClient, max_wait: int = 300) -> None:
    """
    After a first-ever QR pairing, WAHA's NOWEB engine enters AwaitingInitialSync:
    WhatsApp pushes message history to the new linked device asynchronously. Duration
    depends on account size and network — small accounts take ~30s, large ones several
    minutes. Instead of a fixed sleep, we poll every 15s until:
      • At least one DM chat appears in the WAHA store  → proceed immediately
      • max_wait (default 5 min) is reached             → proceed with whatever's available
    """
    poll_interval = 15
    elapsed = 0
    while elapsed < max_wait:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
        try:
            chats = await waha_client.list_chats(session_name, limit=10)
            dm_chats = [c for c in chats if not c.id.endswith("@g.us") and not c.archived]
            if dm_chats:
                logger.info(
                    "WAHA store ready: %d DM chats after %ds [session=%s]",
                    len(dm_chats), elapsed, session_name,
                )
                return
        except Exception:
            pass  # session may still be starting; retry next interval
    logger.warning(
        "WAHA store still empty after %ds — syncing with available data [session=%s]",
        max_wait, session_name,
    )


async def _auto_sync_on_connect(connection_id: str, waha_client: WahaClient) -> None:
    """
    Fired as a background task the moment a QR is scanned (first WORKING transition).

    Job creation order is intentional:
      1. De-dupe + quota check
      2. CREATE JOB immediately → active_job_status = "pending" visible to frontend
         within the next 3-second connections refresh, so the button changes to
         "Sincronizando..." right away instead of staying on "Generar reporte"
         for several minutes.
      3. Wait for WAHA store (up to 5 min on first sync)
      4. Run the actual sync worker with the already-created job_id
    """
    from app.config import settings
    from app.database import async_session_factory

    try:
        async with async_session_factory() as session:
            conn = await WhatsAppConnectionRepository(session).get(connection_id)
            if conn is None:
                return
            is_first_sync = conn.last_sync_at is None
            session_name = conn.waha_session_name

            # De-dupe: skip only for actively running jobs OR very recently completed
            # ones (< 5 min).  "completed" jobs older than 5 min MUST allow a new
            # sync — otherwise re-connecting after a previous sync never triggers
            # the initial auto-sync.  "failed" jobs always retry.
            if conn.last_sync_job_id:
                existing = await AnalysisJobRepository(session).get(str(conn.last_sync_job_id))
                if existing:
                    if existing.status in ("pending", "processing"):
                        logger.info(
                            "Auto-sync skipped — job already active [connection=%s status=%s]",
                            connection_id, existing.status,
                        )
                        return
                    if existing.status == "completed" and existing.completed_at:
                        age_s = (datetime.now(tz=timezone.utc) - existing.completed_at).total_seconds()
                        if age_s < 300:  # 5 minutes
                            logger.info(
                                "Auto-sync skipped — job completed recently (%.0fs ago) [connection=%s]",
                                age_s, connection_id,
                            )
                            return

            # Quota check
            client = await ClientRepository(session).get(str(conn.client_id))
            if not client:
                return
            period_start, _ = get_billing_period(client.plan_started_at)
            jobs_used = await AnalysisJobRepository(session).count_by_connection_this_period(
                connection_id, period_start
            )
            quota = build_quota_status(client.plan, jobs_used, client.plan_started_at)
            if quota.reports_remaining == 0:
                logger.info("Auto-sync skipped — quota exhausted [connection=%s]", connection_id)
                return

            # Create the job NOW so active_job_status is populated immediately.
            # The frontend polls connections every 3s and will show "Sincronizando..."
            # within seconds instead of waiting up to 5 min for the WAHA store.
            job = await create_pending_job(connection_id, session)
            logger.info("Auto-sync job created on connect [connection=%s job=%s]", connection_id, job.id)

        # For first-ever syncs: wait for WAHA's store to be populated.
        # Job is already in DB so the UI reflects the sync in progress.
        if is_first_sync:
            max_wait = getattr(settings, "waha_initial_sync_delay_seconds", 300)
            logger.info(
                "Auto-sync: waiting for WAHA store (max %ds) [connection=%s job=%s]",
                max_wait, connection_id, job.id,
            )
            await _wait_for_waha_store(session_name, waha_client, max_wait=max_wait)

        asyncio.create_task(
            _run_sync_with_fallback(connection_id, str(job.id), waha_client),
        )
        logger.info("Auto-sync worker started [connection=%s job=%s]", connection_id, job.id)
    except Exception:
        logger.exception("Auto-sync on connect failed [connection=%s]", connection_id)


async def _run_sync_with_fallback(connection_id: str, job_id: str, waha_client) -> None:
    """
    Wrapper around run_waha_sync_job that catches unhandled exceptions and marks
    the job as failed so it doesn't sit in 'pending' forever and block future syncs.
    """
    try:
        await run_waha_sync_job(connection_id, job_id, waha_client, False, "auto_connect")
    except Exception:
        logger.exception(
            "Auto-sync worker crashed unexpectedly [connection=%s job=%s]",
            connection_id, job_id,
        )
        from app.database import async_session_factory
        from app.repositories.analysis_repo import AnalysisJobRepository
        try:
            async with async_session_factory() as session:
                await AnalysisJobRepository(session).update(
                    job_id,
                    status="failed",
                    error_message="Auto-sync worker crashed — will retry on next scheduler run",
                )
                await session.commit()
        except Exception:
            logger.exception("Could not mark crashed auto-sync job as failed [job=%s]", job_id)


# --- Authenticated endpoints ---

@router.post("/connections", response_model=ConnectionResponse, status_code=201)
async def create_connection(
    body: CreateConnectionRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    waha: WahaClient = Depends(get_waha_client),
) -> ConnectionResponse:
    client = await _require_active_plan(user, db)
    conn_repo = WhatsAppConnectionRepository(db)

    existing_list = await conn_repo.list_by_client(str(client.id))

    # WAHA Core supports exactly one session ("default"). Block a second connection
    # until the operator upgrades to WAHA PLUS and sets WAHA_MULTI_SESSION=true.
    if not settings.waha_multi_session and existing_list:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "MULTI_SESSION_REQUIRED",
                "message": (
                    "Tu servidor WAHA solo permite una cuenta simultánea. "
                    "Actualiza a WAHA PLUS y activa WAHA_MULTI_SESSION=true para conectar múltiples cuentas."
                ),
            },
        )

    # Enforce per-plan connections limit
    from app.billing.quotas import get_connections_limit
    conn_limit = get_connections_limit(client.plan, getattr(client, "connections_limit", None))
    if len(existing_list) >= conn_limit:
        raise HTTPException(
            status_code=402,
            detail={
                "code": "CONNECTION_LIMIT_REACHED",
                "message": f"Alcanzaste el límite de {conn_limit} conexión(es) de tu plan. Agrega más conexiones desde Configuración → Plan.",
            },
        )

    connection_id = str(uuid.uuid4())
    session_name = _session_name(str(client.id), body.display_name, connection_id)

    _FREQ = {"enterprise": "weekly", "plus": "biweekly"}
    sync_freq = _FREQ.get(client.plan, "monthly")

    try:
        session_info = await waha.get_or_create_session(session_name, str(client.id))
    except WahaError as e:
        raise HTTPException(status_code=502, detail=f"Could not create WAHA session: {e.message}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"No se pudo conectar con el servicio WAHA: {e}")

    conn = await conn_repo.create(
        id=connection_id,
        client_id=str(client.id),
        display_name=body.display_name,
        waha_session_name=session_name,
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
    conns = await WhatsAppConnectionRepository(db).list_by_client(str(client.id))

    job_repo = AnalysisJobRepository(db)
    period_start, _ = get_billing_period(client.plan_started_at)

    results: list[ConnectionResponse] = []
    for conn in conns:
        resp = ConnectionResponse.model_validate(conn)

        # Active job status — drives the button state in real-time
        if conn.last_sync_job_id:
            job = await job_repo.get(str(conn.last_sync_job_id))
            if job and job.status in ("pending", "processing"):
                resp.active_job_status = job.status

        # Per-connection remaining quota — so the frontend doesn't rely on a stale
        # parent quota prop; this updates on every connections refresh
        jobs_used = await job_repo.count_by_connection_this_period(str(conn.id), period_start)
        conn_quota = build_quota_status(client.plan, jobs_used, client.plan_started_at)
        resp.reports_remaining = conn_quota.reports_remaining

        results.append(resp)
    return results


@router.patch("/connections/{connection_id}", response_model=ConnectionResponse)
async def rename_connection(
    connection_id: UUID,
    body: RenameConnectionRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> ConnectionResponse:
    conn = await _get_connection_or_404(str(connection_id), user, db)
    conn_repo = WhatsAppConnectionRepository(db)
    updated = await conn_repo.update(conn.id, display_name=body.display_name)
    await db.commit()
    return ConnectionResponse.model_validate(updated)


@router.post("/connections/{connection_id}/share-token", response_model=ShareTokenResponse)
async def create_share_token(
    connection_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> ShareTokenResponse:
    conn = await _get_connection_or_404(str(connection_id), user, db)

    if conn.status == WahaSessionStatus.WORKING.value:
        raise HTTPException(
            status_code=409,
            detail={"code": "ALREADY_CONNECTED", "message": "Esta cuenta ya está conectada. No es necesario compartir el QR."},
        )
    if conn.status == WahaSessionStatus.PERSONAL_ACCOUNT_BLOCKED.value:
        raise HTTPException(
            status_code=409,
            detail={"code": "PERSONAL_ACCOUNT_BLOCKED", "message": "Esta cuenta fue bloqueada por usar WhatsApp personal."},
        )

    conn_repo = WhatsAppConnectionRepository(db)
    token = await conn_repo.generate_share_token(str(conn.id), ttl_hours=24)
    await db.commit()
    await db.refresh(conn)

    base = settings.frontend_dev_url or settings.frontend_base_url
    url = f"{base}/qr/{token}"
    expires_at = conn.share_token_expires_at
    return ShareTokenResponse(url=url, expires_at=expires_at)


@router.get("/connections/{connection_id}/status")
async def get_connection_status(
    connection_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    waha: WahaClient = Depends(get_waha_client),
) -> dict:
    conn = await _get_connection_or_404(str(connection_id), user, db)
    conn_repo = WhatsAppConnectionRepository(db)

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
            own_jid = info.me.id
            if not conn.phone_number:
                updates["phone_number"] = own_jid.split("@")[0]
                updates["push_name"] = info.me.pushName or None

            if new_status == WahaSessionStatus.WORKING.value:
                if conn.status not in (
                    WahaSessionStatus.WORKING.value,
                    WahaSessionStatus.CHECKING_ACCOUNT.value,
                ):
                    updates["status"] = WahaSessionStatus.CHECKING_ACCOUNT.value
                    updates["last_reconnect_email_sent_at"] = None
                    updates["last_session_active_at"] = datetime.now(tz=timezone.utc)
                    await conn_repo.update(conn.id, **updates)
                    await db.commit()
                    # Invalidate share token — connection is now established
                    await conn_repo.invalidate_share_token(str(conn.id))
                    await db.commit()
                    # Fire auto-sync — QR was just scanned for the first time
                    background_tasks.add_task(_auto_sync_on_connect, str(conn.id), waha)
                    return {
                        "connection_id": str(connection_id),
                        "status": WahaSessionStatus.CHECKING_ACCOUNT.value,
                        "phone_number": updates.get("phone_number") or conn.phone_number,
                        "push_name": updates.get("push_name") or conn.push_name,
                        "is_business_account": None,
                    }

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
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"No se pudo conectar con el servicio WAHA: {e}")


@router.get("/connections/{connection_id}/qr")
async def get_connection_qr(
    connection_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    waha: WahaClient = Depends(get_waha_client),
) -> dict:
    conn = await _get_connection_or_404(str(connection_id), user, db)
    return await _fetch_qr_for_connection(conn, db, waha)


@router.post("/connections/{connection_id}/auth/request-code")
async def request_auth_code(
    connection_id: UUID,
    body: RequestCodeBody,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    waha: WahaClient = Depends(get_waha_client),
) -> dict:
    """
    Generate a WhatsApp pairing code as an alternative to QR scanning.

    Flow:
      1. Frontend calls this endpoint with the user's WhatsApp Business phone number.
      2. WAHA returns a short pairing code (e.g. "NK1N-E28V").
      3. Frontend displays the code and instructs the user to enter it in WhatsApp:
            More options → Linked Devices → Link a Device → Use phone number instead
      4. Once entered, WhatsApp authenticates the session automatically.
      5. Frontend polls GET /connections/{id}/status — WORKING triggers auto-sync,
         identical to the QR-scan flow. No further API call needed from our side.
    """
    conn = await _get_connection_or_404(str(connection_id), user, db)

    if conn.status == WahaSessionStatus.WORKING.value:
        raise HTTPException(
            status_code=409,
            detail={"code": "ALREADY_CONNECTED", "message": "Esta cuenta ya está conectada."},
        )
    if conn.status == WahaSessionStatus.PERSONAL_ACCOUNT_BLOCKED.value:
        raise HTTPException(
            status_code=409,
            detail={"code": "PERSONAL_ACCOUNT_BLOCKED", "message": "Cuenta bloqueada por usar WhatsApp personal."},
        )

    conn_repo = WhatsAppConnectionRepository(db)

    # Ensure session is started and awaiting authentication
    if conn.status in (WahaSessionStatus.STOPPED.value, WahaSessionStatus.FAILED.value):
        try:
            if conn.status == WahaSessionStatus.FAILED.value:
                await waha.restart_session(conn.waha_session_name)
            else:
                await waha.start_session(conn.waha_session_name)
            new_status = (await waha.wait_for_working(conn.waha_session_name, timeout_seconds=60)).value
            await conn_repo.update(conn.id, status=new_status)
            await db.commit()
            # WEBJS: give Chromium 3s to finish rendering the QR/login page
            # after reaching SCAN_QR_CODE before we call requestPairingCode.
            if new_status == WahaSessionStatus.SCAN_QR_CODE.value:
                await asyncio.sleep(3)
        except WahaSessionNotFoundError:
            try:
                session_info = await waha.create_session(conn.waha_session_name, str(conn.id))
                new_status = session_info.status.value
                await conn_repo.update(conn.id, status=new_status)
                await db.commit()
            except (WahaError, httpx.RequestError) as e:
                raise HTTPException(status_code=502, detail=f"No se pudo iniciar la sesión: {e}")
        except (WahaError, httpx.RequestError) as e:
            raise HTTPException(status_code=502, detail=f"No se pudo iniciar la sesión: {e}")

    phone_digits = re.sub(r"[^\d]", "", body.phone_number)

    # WEBJS engine: WhatsApp Web loads inside Chromium. The session reaches
    # SCAN_QR_CODE before the page's JavaScript is fully interactive, so
    # requestPairingCode raises a cryptic 500 if called too soon.
    # Fix: one automatic retry after a 5-second pause — enough for the page
    # to finish loading without meaningfully affecting the user experience.
    pairing_code: str | None = None
    last_waha_error: WahaError | None = None
    for attempt in range(2):
        try:
            pairing_code = await waha.request_auth_code(conn.waha_session_name, phone_digits)
            break
        except WahaError as e:
            last_waha_error = e
            if e.status_code == 500 and attempt == 0:
                logger.info(
                    "request_auth_code: WAHA 500 on attempt 1, retrying in 5s [session=%s]",
                    conn.waha_session_name,
                )
                await asyncio.sleep(5)
                continue
            raise HTTPException(status_code=502, detail=f"WAHA error: {e.message}")
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"No se pudo conectar con WAHA: {e}")

    if pairing_code is None:
        # Persistent 500 from WAHA typically means whatsapp-web.js is incompatible
        # with the current WhatsApp Web version (internal 'Cmd' object missing).
        # This is a WAHA/whatsapp-web.js version issue, not a transient error.
        logger.warning(
            "request_auth_code: phone-code method failed after retries — "
            "WAHA WEBJS engine likely incompatible with current WhatsApp Web version "
            "[session=%s]",
            conn.waha_session_name,
        )
        raise HTTPException(
            status_code=503,
            detail={
                "code": "PHONE_CODE_UNAVAILABLE",
                "message": (
                    "El método de código de teléfono no está disponible con la versión "
                    "actual de WAHA. Usa el código QR para vincular tu cuenta."
                ),
            },
        )

    # Return the code for the frontend to display.
    # The user enters it in WhatsApp Business → no further call needed from our side.
    return {"pairing_code": pairing_code, "phone_number": phone_digits}


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
            await AnalysisJobRepository(db).update(
                str(last_job.id), status="failed",
                error_message="Sync orphaned (no completion within 15 min)",
            )
            await db.commit()

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

    # Per-connection quota check
    client = await _get_client(user, db)
    period_start, _ = get_billing_period(client.plan_started_at)
    jobs_used = await AnalysisJobRepository(db).count_by_connection_this_period(
        str(connection_id), period_start
    )
    quota = build_quota_status(client.plan, jobs_used, client.plan_started_at)
    if quota.reports_remaining == 0:
        renewal = quota.billing_period_end.strftime("%d/%m/%Y")
        raise HTTPException(
            status_code=429,
            detail={
                "code": "QUOTA_EXCEEDED",
                "message": f"Esta cuenta alcanzó el límite de {quota.reports_limit} reporte(s) para este período. La cuota se renueva el {renewal}.",
            },
        )

    job = await create_pending_job(str(connection_id), db)

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

    current_status: WahaSessionStatus | None = None
    try:
        info = await waha.get_session(session_name)
        current_status = info.status
        if current_status not in (WahaSessionStatus.WORKING, WahaSessionStatus.SCAN_QR_CODE):
            await waha.start_session(session_name)
            current_status = await waha.wait_for_working(session_name, timeout_seconds=30)
    except WahaSessionNotFoundError:
        pass
    except (WahaError, httpx.RequestError) as e:
        logger.warning("WAHA error while starting session for unlink (connection=%s): %s", connection_id, e)

    if current_status == WahaSessionStatus.WORKING:
        try:
            await waha.logout_session(session_name)
        except (WahaError, httpx.RequestError) as e:
            logger.warning("WAHA logout error during unlink (connection=%s): %s", connection_id, e)

    try:
        await waha.delete_session(session_name)
    except (WahaError, httpx.RequestError) as e:
        logger.warning("WAHA delete session error during unlink (connection=%s): %s", connection_id, e)

    await WhatsAppConnectionRepository(db).delete(conn.id)
    await db.commit()


# --- Public endpoints (no auth — token-gated) ---

async def _fetch_qr_for_connection(conn, db, waha: WahaClient) -> dict:
    """Shared QR-fetch logic used by both the authed and public QR endpoints."""
    from app.repositories.whatsapp_connection_repo import WhatsAppConnectionRepository
    conn_repo = WhatsAppConnectionRepository(db)
    current_status = conn.status

    if current_status == WahaSessionStatus.PERSONAL_ACCOUNT_BLOCKED.value:
        raise HTTPException(
            status_code=409,
            detail={"code": "PERSONAL_ACCOUNT_BLOCKED", "message": "Personal WhatsApp accounts are not allowed."},
        )

    if current_status == WahaSessionStatus.FAILED.value:
        try:
            await waha.restart_session(conn.waha_session_name)
            current_status = (await waha.wait_for_working(conn.waha_session_name, timeout_seconds=30)).value
            await conn_repo.update(conn.id, status=current_status)
            await db.commit()
        except WahaSessionNotFoundError:
            try:
                session_info = await waha.create_session(conn.waha_session_name, str(conn.client_id))
                current_status = session_info.status.value
                await conn_repo.update(conn.id, status=current_status)
                await db.commit()
            except (WahaError, httpx.RequestError) as e:
                raise HTTPException(status_code=502, detail=f"Could not recreate WAHA session: {e}")
        except (WahaError, httpx.RequestError) as e:
            raise HTTPException(status_code=502, detail=f"Could not restart WAHA session: {e}")

    if current_status in (WahaSessionStatus.STOPPED.value, WahaSessionStatus.STARTING.value):
        try:
            if current_status == WahaSessionStatus.STOPPED.value:
                await waha.start_session(conn.waha_session_name)
            # NOWEB engine can take 45-60s to load Chromium + WhatsApp Web on a
            # busy container. 30s was too short when multiple sessions start simultaneously.
            current_status = (await waha.wait_for_working(conn.waha_session_name, timeout_seconds=60)).value
            await conn_repo.update(conn.id, status=current_status)
            await db.commit()
        except WahaSessionNotFoundError:
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
            except (WahaError, httpx.RequestError) as e:
                raise HTTPException(status_code=502, detail=f"Could not recreate WAHA session: {e}")
        except (WahaError, httpx.RequestError) as e:
            raise HTTPException(status_code=502, detail=f"Could not start WAHA session: {e}")

    if current_status == WahaSessionStatus.WORKING.value:
        raise HTTPException(
            status_code=409,
            detail={"code": "ALREADY_CONNECTED", "message": "Session is already connected. No QR needed."},
        )

    # STARTING means WAHA is still loading Chromium — not an error, just not ready yet.
    # Return a retriable 425 (Too Early) so the frontend knows to try again in a few seconds.
    if current_status == WahaSessionStatus.STARTING.value:
        raise HTTPException(
            status_code=425,
            detail={"code": "SESSION_STARTING", "message": "La sesión está iniciando. Intenta de nuevo en unos segundos."},
        )

    if current_status != WahaSessionStatus.SCAN_QR_CODE.value:
        raise HTTPException(
            status_code=409,
            detail={"code": "SESSION_NOT_READY", "message": f"Session is in state '{current_status}'. QR not available yet."},
        )

    try:
        qr_base64 = await waha.get_qr_base64(conn.waha_session_name)
    except WahaError as e:
        # Refresh live status before deciding what to return
        live_status: str | None = None
        try:
            live = await waha.get_session(conn.waha_session_name)
            live_status = live.status.value
            await conn_repo.update(conn.id, status=live_status)
            await db.commit()
        except (WahaError, httpx.RequestError):
            pass

        # Session became WORKING while we were fetching QR (user just scanned) → not an error
        if live_status == WahaSessionStatus.WORKING.value:
            raise HTTPException(
                status_code=409,
                detail={"code": "ALREADY_CONNECTED", "message": "Session is already connected. No QR needed."},
            )
        # Session went STOPPED (e.g. sync completed) → retriable, not a 502
        if live_status == WahaSessionStatus.STOPPED.value:
            raise HTTPException(
                status_code=409,
                detail={"code": "SESSION_NOT_READY", "message": "La sesión se detuvo. Intenta de nuevo."},
            )
        raise HTTPException(status_code=502, detail=f"Could not fetch QR: {e.message}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"No se pudo conectar con el servicio WAHA: {e}")

    expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=20)
    return {"qr_base64": qr_base64, "expires_at": expires_at.isoformat()}


@public_router.get("/share/{token}")
async def get_share_context(
    token: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Public: return connection context (no sensitive data) for the QR share page."""
    conn = await WhatsAppConnectionRepository(db).get_by_share_token(token)
    if conn is None:
        raise HTTPException(status_code=404, detail={"code": "TOKEN_EXPIRED", "message": "Este enlace ha vencido o no existe."})

    client = await ClientRepository(db).get(str(conn.client_id))
    business_name = client.business_name if client else ""

    return {
        "connection_id": str(conn.id),
        "display_name": conn.display_name or "WhatsApp",
        "business_name": business_name,
        "status": conn.status,
        "expires_at": conn.share_token_expires_at.isoformat() if conn.share_token_expires_at else None,
    }


@public_router.get("/share/{token}/qr")
async def get_share_qr(
    token: str,
    db: AsyncSession = Depends(get_db),
    waha: WahaClient = Depends(get_waha_client),
) -> dict:
    """Public: return QR for this share token. Proxies WAHA."""
    conn = await WhatsAppConnectionRepository(db).get_by_share_token(token)
    if conn is None:
        raise HTTPException(status_code=404, detail={"code": "TOKEN_EXPIRED", "message": "Este enlace ha vencido o no existe."})

    return await _fetch_qr_for_connection(conn, db, waha)


@public_router.get("/share/{token}/status")
async def get_share_status(
    token: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    waha: WahaClient = Depends(get_waha_client),
) -> dict:
    """Public: poll connection status for the QR share page."""
    conn = await WhatsAppConnectionRepository(db).get_by_share_token(token)
    if conn is None:
        raise HTTPException(status_code=404, detail={"code": "TOKEN_EXPIRED", "message": "Este enlace ha vencido o no existe."})

    try:
        info = await waha.get_session(conn.waha_session_name)
        new_status = info.status.value
        conn_repo = WhatsAppConnectionRepository(db)

        updates: dict = {"status": new_status}
        if info.me and not conn.phone_number:
            updates["phone_number"] = info.me.id.split("@")[0]

        await conn_repo.update(conn.id, **updates)

        if new_status == WahaSessionStatus.WORKING.value:
            await conn_repo.invalidate_share_token(str(conn.id))
            background_tasks.add_task(_auto_sync_on_connect, str(conn.id), waha)

        await db.commit()
        return {"status": new_status}
    except WahaSessionNotFoundError:
        return {"status": "FAILED"}
    except (WahaError, httpx.RequestError):
        return {"status": conn.status}
