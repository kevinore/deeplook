"""
APScheduler wrapper for periodic WAHA syncs.
Enabled/disabled via ENABLE_WHATSAPP_SCHEDULER env var.
"""
import asyncio
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings

logger = logging.getLogger(__name__)

_scheduler = AsyncIOScheduler()


async def check_pending_syncs() -> None:
    """Triggered every N minutes. Spawns async tasks for each due sync."""
    from app.database import async_session_factory
    from app.integrations.waha.client import get_waha_client
    from app.repositories.whatsapp_connection_repo import WhatsAppConnectionRepository

    now = datetime.now(tz=timezone.utc)
    async with async_session_factory() as session:
        pending = await WhatsAppConnectionRepository(session).get_pending_syncs(now)

    if not pending:
        return

    logger.info("Scheduler: %d connection(s) due for sync", len(pending))
    waha_client = get_waha_client()
    for conn in pending:
        asyncio.create_task(_safe_sync(str(conn.id), waha_client))


async def _safe_sync(connection_id: str, waha_client) -> None:
    from app.billing.quotas import build_quota_status, get_billing_period
    from app.database import async_session_factory
    from app.repositories.analysis_repo import AnalysisJobRepository
    from app.repositories.client_repo import ClientRepository
    from app.repositories.whatsapp_connection_repo import WhatsAppConnectionRepository
    from app.services.whatsapp_sync_service import create_pending_job, run_waha_sync_job

    try:
        async with async_session_factory() as session:
            conn = await WhatsAppConnectionRepository(session).get(connection_id)
            if conn is None:
                return
            client = await ClientRepository(session).get(str(conn.client_id))
            if client is None:
                return

            period_start, _ = get_billing_period(client.plan_started_at)
            jobs_used = await AnalysisJobRepository(session).count_by_client_this_period(
                str(client.id), period_start
            )
            quota = build_quota_status(client.plan, jobs_used, client.plan_started_at)
            if quota.reports_remaining == 0:
                logger.info(
                    "Scheduled sync skipped: quota exhausted [connection=%s plan=%s used=%d/%d]",
                    connection_id, client.plan, jobs_used, quota.reports_limit,
                )
                # Advance next_scheduled_sync_at to the billing period end so the
                # scheduler stops polling this connection until the quota resets.
                await WhatsAppConnectionRepository(session).update(
                    conn.id,
                    next_scheduled_sync_at=quota.billing_period_end,
                )
                await session.commit()
                return

            job = await create_pending_job(connection_id, session)
        asyncio.create_task(run_waha_sync_job(connection_id, str(job.id), waha_client, source="scheduled"))
    except Exception as exc:
        logger.error("Scheduled sync failed for connection %s: %s", connection_id, exc, exc_info=True)


def start_scheduler() -> None:
    if not settings.enable_whatsapp_scheduler:
        logger.info("WhatsApp scheduler disabled (ENABLE_WHATSAPP_SCHEDULER=false)")
        return
    _scheduler.add_job(
        check_pending_syncs,
        "interval",
        minutes=settings.whatsapp_scheduler_interval_minutes,
        id="check_pending_syncs",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(
        "WhatsApp sync scheduler started (interval=%d min)",
        settings.whatsapp_scheduler_interval_minutes,
    )


def stop_scheduler() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
