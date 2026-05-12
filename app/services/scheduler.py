"""
APScheduler wrapper for periodic WAHA syncs and renewal reminders.
Enabled/disabled via ENABLE_WHATSAPP_SCHEDULER env var.
"""
import asyncio
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.billing.router import PLAN_DISPLAY
from app.config import settings
from app.models.database import Client

logger = logging.getLogger(__name__)

_scheduler = AsyncIOScheduler()

# Stages of renewal reminder: emit one email at each threshold (idempotent).
_RENEWAL_STAGES = [
    (7, "7d"),
    (3, "3d"),
    (1, "1d"),
]


async def check_missed_initial_syncs() -> None:
    """
    Safety net: find connections that connected successfully but whose initial
    auto-sync never ran (or crashed silently).

    Triggers a sync for connections where ALL of:
      • status is WORKING or STOPPED (session is authenticated)
      • last_sync_at is NULL (never produced a report)
      • created_at was more than 10 minutes ago (enough time for auto-sync to have run)
      • no active pending/processing job on last_sync_job_id
      • plan is not free (free accounts can't sync)

    This runs every 5 minutes and acts as the final guarantee that a connected
    account always gets its first sync regardless of what went wrong with the
    primary auto-sync path.
    """
    from app.database import async_session_factory
    from app.integrations.waha.client import get_waha_client
    from app.models.database import WhatsAppConnection, Client, AnalysisJob
    from sqlalchemy import select, or_
    from datetime import timedelta

    now = datetime.now(tz=timezone.utc)
    cutoff = now - timedelta(minutes=10)

    async with async_session_factory() as session:
        result = await session.execute(
            select(WhatsAppConnection)
            .join(Client, WhatsAppConnection.client_id == Client.id)
            .where(
                WhatsAppConnection.last_sync_at.is_(None),
                WhatsAppConnection.created_at <= cutoff,
                or_(
                    WhatsAppConnection.status == "WORKING",
                    WhatsAppConnection.status == "STOPPED",
                ),
                Client.plan != "free",
                Client.is_active.is_(True),
            )
        )
        candidates = result.scalars().all()

    if not candidates:
        return

    from app.repositories.analysis_repo import AnalysisJobRepository
    from app.database import async_session_factory as asf

    waha_client = get_waha_client()
    for conn in candidates:
        # Check if there's already an active job before spawning a new sync
        async with asf() as session:
            if conn.last_sync_job_id:
                job = await AnalysisJobRepository(session).get(str(conn.last_sync_job_id))
                if job and job.status in ("pending", "processing"):
                    continue  # already running, skip

        logger.warning(
            "Missed initial sync detected — firing fallback sync [connection=%s created=%s]",
            conn.id, conn.created_at,
        )
        asyncio.create_task(_safe_sync(str(conn.id), waha_client))


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
            jobs_used = await AnalysisJobRepository(session).count_by_connection_this_period(
                connection_id, period_start
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


async def check_renewal_reminders() -> None:
    """
    Daily job: send 7d/3d/1d-before-expiry email reminders to paid plans.

    Uses `last_renewal_email_stage` to dedupe: each stage is emitted at most once
    per renewal cycle. The stage is reset on payment (handled in the Wompi
    webhook when plan_started_at is updated — TODO: wire that in payment_repo).
    """
    from app.database import async_session_factory
    from app.delivery.notifications.email_service import get_email_service

    now = datetime.now(tz=timezone.utc)
    sent_count = 0

    async with async_session_factory() as session:
        # Pull all active paid clients with an expiry date.
        result = await session.execute(
            select(Client).where(
                Client.plan != "free",
                Client.plan_expires_at.is_not(None),
                Client.is_active.is_(True),
                Client.email.is_not(None),
            )
        )
        clients = result.scalars().all()

        for client in clients:
            expires_at = client.plan_expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)

            delta_days = (expires_at - now).days
            # Pick the most-urgent stage that applies right now.
            target_stage: str | None = None
            for threshold, stage in _RENEWAL_STAGES:
                if 0 <= delta_days <= threshold:
                    target_stage = stage
                    break
            if target_stage is None:
                continue

            # Skip if we've already sent this stage in the current cycle.
            # Stage order: 7d → 3d → 1d. Once we've emitted a more-urgent stage,
            # we never go back to a less-urgent one.
            stage_rank = {"7d": 1, "3d": 2, "1d": 3}
            already = client.last_renewal_email_stage or ""
            if stage_rank.get(target_stage, 0) <= stage_rank.get(already, 0):
                continue

            plan_price = PLAN_DISPLAY.get(client.plan, {}).get("price_cop", 0)
            ok = await get_email_service().send_renewal_reminder(
                to_email=client.email,
                name=client.name,
                business_name=client.business_name,
                plan=client.plan,
                days_remaining=max(0, delta_days),
                plan_price_cop=plan_price,
                stage=target_stage,
            )
            if ok:
                client.last_renewal_email_stage = target_stage
                client.last_renewal_email_sent_at = now
                sent_count += 1

        if sent_count > 0:
            await session.commit()
            logger.info("Renewal reminders sent: %d", sent_count)


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
    # Safety net: every 5 min, catch any connections that connected but never got
    # their initial sync (crashed auto-sync, de-dupe bug, event loop hiccup, etc.)
    _scheduler.add_job(
        check_missed_initial_syncs,
        "interval",
        minutes=5,
        id="check_missed_initial_syncs",
        replace_existing=True,
    )
    # Daily renewal-reminder check at 09:00 UTC (≈ 04:00 Colombia).
    _scheduler.add_job(
        check_renewal_reminders,
        "cron",
        hour=9,
        minute=0,
        id="check_renewal_reminders",
        replace_existing=True,
    )
    # Keepalive: every hour, find sessions idle >7 days and ping them.
    # Defends against WhatsApp's 14-day idle-device-unlink rule for users on
    # biweekly/monthly plans whose normal sync cadence exceeds 14 days.
    from app.services.whatsapp_keepalive import check_pending_keepalives
    _scheduler.add_job(
        check_pending_keepalives,
        "interval",
        hours=1,
        id="check_pending_keepalives",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(
        "Schedulers started — sync=%d min, keepalive=hourly, renewal check daily at 09:00 UTC",
        settings.whatsapp_scheduler_interval_minutes,
    )


def stop_scheduler() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
