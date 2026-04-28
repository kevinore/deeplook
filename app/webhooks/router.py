"""
Public webhook endpoints — no Clerk authentication.
Wompi calls these directly after payment events.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.wompi import verify_event_signature
from app.dependencies import get_db
from app.repositories.client_repo import ClientRepository
from app.repositories.payment_repo import PaymentSessionRepository

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
logger = logging.getLogger(__name__)

# Wompi transaction statuses that mean money moved successfully
_APPROVED_STATUSES = {"APPROVED"}


@router.post("/wompi")
async def wompi_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """
    Receive Wompi payment events.
    Verifies the SHA256 signature, then activates the client's plan on APPROVED.
    """
    try:
        event = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body.")

    if not verify_event_signature(event):
        logger.warning("Wompi webhook: invalid signature — payload rejected")
        raise HTTPException(status_code=400, detail="Invalid signature.")

    event_type = event.get("event")
    if event_type != "transaction.updated":
        # We only care about transaction events; ack everything else silently.
        return {"status": "ignored", "event": event_type}

    transaction = event.get("data", {}).get("transaction", {})
    status = transaction.get("status", "")
    reference = transaction.get("reference", "")
    wompi_tx_id = transaction.get("id", "")

    logger.info("Wompi webhook: event=%s status=%s reference=%s", event_type, status, reference)

    # Find our payment session by reference
    session = await PaymentSessionRepository(db).get_by_reference(reference)
    if not session:
        logger.warning("Wompi webhook: unknown reference %s", reference)
        # Return 200 so Wompi doesn't retry — we just can't process it
        return {"status": "reference_not_found"}

    # Update the session status regardless
    new_session_status = status.lower() if status else "error"
    await PaymentSessionRepository(db).update(
        session.id,
        status=new_session_status,
        wompi_transaction_id=wompi_tx_id,
    )

    if status in _APPROVED_STATUSES:
        now = datetime.now(tz=timezone.utc)
        client_repo = ClientRepository(db)
        client = await client_repo.get(str(session.client_id))

        # Extend from current expiry if renewing early, otherwise from now
        current_expiry = client.plan_expires_at if client and client.plan_expires_at else None
        if current_expiry:
            if current_expiry.tzinfo is None:
                current_expiry = current_expiry.replace(tzinfo=timezone.utc)
            base = max(now, current_expiry)
        else:
            base = now

        from app.billing.quotas import _add_one_month
        new_expires_at = _add_one_month(base.year, base.month, base.day)

        await client_repo.update(
            str(session.client_id),
            plan=session.plan,
            plan_started_at=now,
            plan_expires_at=new_expires_at,
            subscription_status="active",
        )
        logger.info(
            "Wompi webhook: activated plan=%s for client=%s (tx=%s) expires=%s",
            session.plan, session.client_id, wompi_tx_id, new_expires_at.isoformat(),
        )

    await db.commit()
    return {"status": "ok"}
