"""
WhatsApp keepalive service.

WhatsApp's server-side rule: if a phone hasn't connected to WhatsApp in 14
consecutive days, all linked devices are automatically unlinked. This is
enforced by Meta and WAHA cannot prevent it — but we can prevent it from
HITTING us by waking the WAHA session every ~7 days.

For monthly-plan users (sync every 30 days), the auto-sync alone would let
the device get unlinked. The keepalive job closes that gap by briefly
spinning up the session — read-only, no message traffic — between syncs.

Keepalive cycle:
  1. start_session(name)         — restore credentials, no QR
  2. wait_for_working(...)       — confirm still authenticated
  3. stop_session(logout=False)  — preserve credentials, return to STOPPED
  4. update last_session_active_at = now

If the wake-up returns SCAN_QR_CODE, WhatsApp has already unlinked us.
We notify the user (notification + email) and stop trying.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.database import async_session_factory
from app.integrations.waha.client import WahaClient
from app.integrations.waha.exceptions import (
    WahaError,
    WahaSessionNotFoundError,
)
from app.integrations.waha.models import WahaSessionStatus
from app.repositories.client_repo import ClientRepository
from app.repositories.notification_repo import NotificationRepository
from app.repositories.whatsapp_connection_repo import WhatsAppConnectionRepository

logger = logging.getLogger(__name__)


async def run_keepalive(connection_id: str, waha_client: WahaClient) -> None:
    """
    Wake → verify → sleep cycle for a single connection.
    Errors are caught and logged; never propagate (one bad connection
    shouldn't break the scheduled job for others).
    """
    async with async_session_factory() as session:
        conn_repo = WhatsAppConnectionRepository(session)
        conn = await conn_repo.get(connection_id)
        if conn is None:
            return

        name = conn.waha_session_name
        logger.info("Keepalive start [connection=%s session=%s]", connection_id, name)

        try:
            # 1. Wake the session
            try:
                info = await waha_client.get_session(name)
            except WahaSessionNotFoundError:
                logger.warning(
                    "Keepalive: WAHA session '%s' missing — connection orphaned. "
                    "Marking SCAN_QR_CODE so the user reconnects.",
                    name,
                )
                await conn_repo.update(conn.id, status="SCAN_QR_CODE")
                await session.commit()
                await _notify_reconnect_required(conn, session)
                return

            status = info.status
            if status == WahaSessionStatus.STOPPED:
                await waha_client.start_session(name)
                status = await waha_client.wait_for_working(name, timeout_seconds=45)
            elif status == WahaSessionStatus.STARTING:
                status = await waha_client.wait_for_working(name, timeout_seconds=45)

            # 2. Did WhatsApp unlink the device while we were away?
            if status == WahaSessionStatus.SCAN_QR_CODE:
                logger.warning(
                    "Keepalive: session '%s' moved to SCAN_QR_CODE — WhatsApp unlinked us. "
                    "Notifying user.", name,
                )
                await conn_repo.update(conn.id, status="SCAN_QR_CODE")
                await session.commit()
                await _notify_reconnect_required(conn, session)
                return

            if status != WahaSessionStatus.WORKING:
                logger.warning(
                    "Keepalive: session '%s' did not reach WORKING (got %s). Skipping.",
                    name, status.value if hasattr(status, "value") else status,
                )
                return

            # 3. Session is alive — record the timestamp and put it back to sleep
            await waha_client.stop_session(name, logout=False)
            await conn_repo.update(
                conn.id,
                last_session_active_at=datetime.now(tz=timezone.utc),
                status="STOPPED",
            )
            await session.commit()
            logger.info("Keepalive ok [connection=%s session=%s]", connection_id, name)

        except WahaError as e:
            logger.warning(
                "Keepalive: WAHA error for connection %s: %s. Will retry next cycle.",
                connection_id, e.message if hasattr(e, "message") else e,
            )
        except Exception:
            logger.exception("Keepalive failed unexpectedly [connection=%s]", connection_id)


async def _notify_reconnect_required(conn, session) -> None:
    """
    Send in-app notification + email asking the user to scan a new QR.
    Deduped via `last_reconnect_email_sent_at` — at most once per 24h.
    """
    from app.config import settings
    from app.delivery.notifications.email_service import get_email_service

    now = datetime.now(tz=timezone.utc)
    last_sent = conn.last_reconnect_email_sent_at
    if last_sent is not None:
        if last_sent.tzinfo is None:
            last_sent = last_sent.replace(tzinfo=timezone.utc)
        hours_since = (now - last_sent).total_seconds() / 3600
        if hours_since < 24:
            logger.info(
                "Reconnect notice already sent %.1f h ago — skipping dedupe",
                hours_since,
            )
            return

    client = await ClientRepository(session).get(str(conn.client_id))
    if client is None:
        return

    # 1. In-app notification
    try:
        await NotificationRepository(session).create(
            client_id=str(conn.client_id),
            type="reconnect_required",
            title="Tu WhatsApp se desconectó",
            body="WhatsApp desvinculó la conexión por inactividad. Reconecta tu cuenta para seguir recibiendo reportes.",
        )
    except Exception:
        logger.exception("Failed to create reconnect notification")

    # 2. Email — best-effort, don't fail the keepalive if it doesn't go through
    if client.email:
        try:
            ok = await get_email_service().send_reconnect_required(
                to_email=client.email,
                name=client.name,
                business_name=client.business_name,
            )
            if ok:
                await WhatsAppConnectionRepository(session).update(
                    conn.id, last_reconnect_email_sent_at=now,
                )
        except Exception:
            logger.exception("Failed to send reconnect email")

    await session.commit()


async def check_pending_keepalives() -> None:
    """
    Scheduler entry point. Runs hourly. Fans out keepalive tasks for every
    connection that hasn't been pinged in >7 days.

    Plan-by-plan timing once this is live:
      - weekly  (Enterprise): regular sync covers it; keepalive rarely fires
      - biweekly (Plus):       keepalive fires once between each sync
      - monthly  (Basic):       keepalive fires ~3 times between each sync
    """
    from datetime import timedelta
    from app.integrations.waha.client import get_waha_client

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=7)

    async with async_session_factory() as session:
        due = await WhatsAppConnectionRepository(session).get_due_keepalives(cutoff)

    if not due:
        return

    logger.info("Keepalive: %d connection(s) due", len(due))
    waha_client = get_waha_client()

    # Spread fire-up over a few seconds so we don't hit WAHA all at once
    for i, conn in enumerate(due):
        # Schedule with a small jitter to avoid thundering-herd against WAHA
        delay = i * 2  # 2 s between starts
        asyncio.create_task(_delayed_keepalive(str(conn.id), waha_client, delay))


async def _delayed_keepalive(connection_id: str, waha_client: WahaClient, delay_seconds: int) -> None:
    if delay_seconds:
        await asyncio.sleep(delay_seconds)
    await run_keepalive(connection_id, waha_client)
