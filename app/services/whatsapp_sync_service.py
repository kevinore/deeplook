"""
WhatsApp sync service.

trigger_sync_background() is the main entry point — it creates a job shell
immediately and does all heavy WAHA work (fetch + store + analysis) in a
background task so the HTTP endpoint can return 202 right away.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.integrations.waha.client import WahaClient
from app.integrations.waha.exceptions import WahaError, WahaRePairingRequiredError, WahaSessionNotReadyError
from app.integrations.waha.models import WahaSessionStatus
from app.ingestion.waha_parser import build_batch_from_waha
from app.models.database import AnalysisJob
from app.repositories.analysis_repo import AnalysisJobRepository
from app.repositories.client_repo import ClientRepository
from app.repositories.notification_repo import NotificationRepository
from app.repositories.whatsapp_connection_repo import WhatsAppConnectionRepository

logger = logging.getLogger(__name__)

_LOOKBACK_BY_PLAN: dict[str, int] = {
    "basic": 30,
    "plus": 90,
    "enterprise": 180,
    "free": 30,
}

_MAX_CHATS_BY_PLAN: dict[str, int] = {
    "basic": 100,
    "plus": 300,
    "enterprise": 1000,
    "free": 100,
}

_SYNC_PERIOD_DAYS: dict[str, int] = {
    "monthly": 30,
    "biweekly": 15,
    "weekly": 7,
}


async def create_pending_job(connection_id: str, session: AsyncSession) -> AnalysisJob:
    """
    Create a shell AnalysisJob immediately so the endpoint can return its ID.
    The actual work happens in run_waha_sync_job().
    """
    conn = await WhatsAppConnectionRepository(session).get(connection_id)
    if conn is None:
        raise ValueError(f"Connection {connection_id} not found")

    job = await AnalysisJobRepository(session).create(
        client_id=str(conn.client_id),
        status="pending",
        job_type="full_analysis",
        total_conversations=0,
    )
    await session.flush()

    await WhatsAppConnectionRepository(session).update(conn.id, last_sync_job_id=job.id)
    await session.commit()
    return job


async def run_waha_sync_job(
    connection_id: str,
    job_id: str,
    waha_client: WahaClient,
    force_full: bool = False,
    source: Literal["manual", "scheduled"] = "manual",
) -> None:
    """
    Background task: fetch conversations from WAHA, store them, then kick off
    the AI analysis worker. Creates its own DB session.
    """
    logger.info("WAHA sync started [job=%s connection=%s]", job_id, connection_id)

    async with async_session_factory() as session:
        job_repo = AnalysisJobRepository(session)
        conn_repo = WhatsAppConnectionRepository(session)

        conn = await conn_repo.get(connection_id)
        if conn is None:
            logger.error("WAHA sync: connection %s not found", connection_id)
            return

        name = conn.waha_session_name

        # Mark job as processing
        await job_repo.update(job_id, status="processing", started_at=datetime.utcnow())
        await session.commit()

        try:
            # --- 1. Ensure session is WORKING ---
            info = await waha_client.get_session(name)
            status = info.status

            if status == WahaSessionStatus.STOPPED:
                await waha_client.start_session(name)
                status = await waha_client.wait_for_working(name, timeout_seconds=60)
            elif status == WahaSessionStatus.STARTING:
                status = await waha_client.wait_for_working(name, timeout_seconds=60)

            if status == WahaSessionStatus.SCAN_QR_CODE:
                await conn_repo.update(conn.id, status="SCAN_QR_CODE")
                await session.commit()
                # Inform the user with a specific reconnect notice (not generic "sync failed").
                from app.services.whatsapp_keepalive import _notify_reconnect_required
                fresh_conn = await conn_repo.get(connection_id)
                if fresh_conn is not None:
                    await _notify_reconnect_required(fresh_conn, session)
                raise WahaRePairingRequiredError(name)

            if status not in (WahaSessionStatus.WORKING,):
                raise WahaSessionNotReadyError(name, status.value)

            # Session is up — record activity so the keepalive scheduler doesn't
            # double-poke it. Updated again at the end on full success.
            await conn_repo.update(conn.id, last_session_active_at=datetime.now(tz=timezone.utc))
            await session.flush()

            # --- 2. Resolve me.id ---
            fresh = await waha_client.get_session(name)
            me_phone: str | None = None
            if fresh.me:
                me_phone = fresh.me.id.split("@")[0]
                if not conn.phone_number and me_phone:
                    await conn_repo.update(conn.id, phone_number=me_phone, push_name=fresh.me.pushName or None)
                    await session.flush()

            # --- 3. Calculate sync window ---
            now = datetime.now(tz=timezone.utc)
            client = await ClientRepository(session).get(str(conn.client_id))
            plan = client.plan if client else "basic"
            if force_full or conn.last_sync_at is None:
                days = _LOOKBACK_BY_PLAN.get(plan, 30)
                since = now - timedelta(days=days)
            else:
                since = conn.last_sync_at - timedelta(hours=24)

            max_chats = _MAX_CHATS_BY_PLAN.get(plan, 100)

            # --- 4. Fetch conversations (the slow part — safely in background) ---
            try:
                batch = await build_batch_from_waha(
                    waha_client=waha_client,
                    session_name=name,
                    client_id=str(conn.client_id),
                    since_datetime=since,
                    me_phone=me_phone,
                    max_chats=max_chats,
                )
            finally:
                try:
                    await waha_client.stop_session(name, logout=False)
                    conn_status = "STOPPED"
                except Exception:
                    logger.warning("Could not stop WAHA session '%s'", name, exc_info=True)
                    conn_status = "WORKING"

            if not batch.conversations:
                logger.info("WAHA sync [job=%s]: no new conversations since %s", job_id, since.date())
                await job_repo.update(job_id, status="completed", completed_at=datetime.utcnow(), total_conversations=0)
                await conn_repo.update(
                    conn.id, last_sync_at=now, last_session_active_at=now, status=conn_status,
                )
                await session.commit()
                return

            # --- 5. Store batch (contacts + conversations only, no message text) ---
            from app.analytics.pipeline import store_batch
            pairs = await store_batch(batch, session)

            # --- 6. Update job with real count ---
            await job_repo.update(job_id, total_conversations=len(pairs))

            # --- 7. Update connection record ---
            period_days = _SYNC_PERIOD_DAYS.get(conn.sync_frequency, 30)
            await conn_repo.update(
                conn.id,
                last_sync_at=now,
                last_session_active_at=now,
                last_sync_job_id=job_id,
                status=conn_status,
                next_scheduled_sync_at=now + timedelta(days=period_days),
            )
            await session.commit()

            logger.info(
                "WAHA sync [job=%s]: %d conversations ready, kicking off AI analysis",
                job_id, len(pairs),
            )

        except WahaRePairingRequiredError as exc:
            # The reconnect notification + email were already sent above; here we
            # just mark the job failed with a clear status code so the dashboard
            # can show "Reconectar" instead of "Error en sincronización".
            logger.warning("WAHA sync stopped [job=%s]: re-pairing required for session", job_id)
            try:
                await job_repo.update(
                    job_id,
                    status="failed",
                    error_message="WhatsApp desvinculó el dispositivo — requiere reconexión",
                )
                await session.commit()
            except Exception:
                pass
            return
        except Exception as exc:
            logger.error("WAHA sync failed [job=%s]: %s", job_id, exc, exc_info=True)
            try:
                await NotificationRepository(session).create(
                    client_id=str(conn.client_id),
                    type="sync_failed",
                    title="Error en la sincronización",
                    body="No se pudieron obtener las conversaciones de WhatsApp. Verifica tu conexión e intenta de nuevo.",
                    job_id=job_id,
                )
                await job_repo.update(job_id, status="failed", error_message=str(exc))
                await session.commit()
            except Exception:
                pass
            return

    # --- 8. Kick off AI analysis — pass NormalizedConversation objects directly,
    #         no DB round-trip needed since they're already in memory.
    from app.workers.analysis_worker import run_analysis_job
    asyncio.create_task(run_analysis_job(job_id, pairs))
