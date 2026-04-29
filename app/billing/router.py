from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, get_current_user
from app.billing.quotas import PLAN_LIMITS, build_quota_status, get_billing_period
from app.billing.wompi import compute_integrity, get_plan_amount, make_reference
from app.config import settings
from app.dependencies import get_db
from app.repositories.analysis_repo import AnalysisJobRepository
from app.repositories.client_repo import ClientRepository
from app.repositories.payment_repo import PaymentSessionRepository

router = APIRouter(prefix="/billing", tags=["Billing"])

PLAN_DISPLAY = {
    "basic":      {"label": "Básico",     "price_cop": 160_000, "description": "Visibilidad mensual de tu WhatsApp"},
    "plus":       {"label": "Plus",       "price_cop": 250_000, "description": "Detección de cambios cada 15 días"},
    "enterprise": {"label": "Enterprise", "price_cop": 400_000, "description": "Visibilidad semanal con soporte prioritario"},
}


@router.get("/plans")
async def list_plans() -> list[dict]:
    """Return all purchasable plans with prices and feature limits."""
    plans = []
    for key in ("basic", "plus", "enterprise"):
        limits = PLAN_LIMITS[key]
        display = PLAN_DISPLAY[key]
        plans.append({
            "key": key,
            "label": display["label"],
            "description": display["description"],
            "price_cop": display["price_cop"],
            "amount_in_cents": get_plan_amount(key),
            "features": {
                "reports_per_month": limits["reports_per_month"],
                "conversations_per_report": limits["conversations_per_report"],
                "lookback_days": limits["lookback_days"],
                "manual_upload": limits["manual_upload"],
                "trends_dashboard": limits["trends_dashboard"],
            },
        })
    return plans


class PaymentSessionRequest(BaseModel):
    plan: str


@router.post("/payment-session")
async def create_payment_session(
    body: PaymentSessionRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Create a Wompi payment session.
    Returns the reference, pre-computed integrity hash, and all widget parameters
    needed to render the Wompi checkout button on the frontend.
    """
    if body.plan not in ("basic", "plus", "enterprise"):
        raise HTTPException(status_code=422, detail="Invalid plan. Choose basic, plus, or enterprise.")

    clients = await ClientRepository(db).list_by_owner(user.user_id)
    if not clients:
        raise HTTPException(status_code=404, detail="Client profile not found.")
    client = clients[0]

    amount_in_cents = get_plan_amount(body.plan)
    reference = make_reference(str(client.id), body.plan)
    integrity = compute_integrity(reference, amount_in_cents, "COP")

    session = await PaymentSessionRepository(db).create(
        client_id=str(client.id),
        plan=body.plan,
        amount_in_cents=amount_in_cents,
        reference=reference,
        status="pending",
    )
    await db.commit()

    return {
        "session_id": str(session.id),
        "reference": reference,
        "integrity": integrity,
        "amount_in_cents": amount_in_cents,
        "currency": "COP",
        "public_key": settings.wompi_public_key,
        "redirect_url": f"{settings.wompi_redirect_base_url}/pago-exitoso?ref={reference}",
        "plan": body.plan,
        "plan_label": PLAN_DISPLAY[body.plan]["label"],
        "price_cop": PLAN_DISPLAY[body.plan]["price_cop"],
    }


@router.get("/payment-status")
async def get_payment_status(
    ref: str,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Poll the live status of a payment session by Wompi reference."""
    clients = await ClientRepository(db).list_by_owner(user.user_id)
    if not clients:
        raise HTTPException(status_code=404, detail="Client profile not found.")
    client = clients[0]

    session = await PaymentSessionRepository(db).get_by_reference(ref)
    if not session or str(session.client_id) != str(client.id):
        raise HTTPException(status_code=404, detail="Payment session not found.")

    return {"reference": session.reference, "status": session.status, "plan": session.plan}


@router.get("/payment-history")
async def get_payment_history(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    """Return all payment sessions for the authenticated user's client, newest first."""
    clients = await ClientRepository(db).list_by_owner(user.user_id)
    if not clients:
        raise HTTPException(status_code=404, detail="Client profile not found.")
    client = clients[0]
    sessions = await PaymentSessionRepository(db).list_by_client(str(client.id))
    return [
        {
            "id": str(s.id),
            "plan": s.plan,
            "amount_in_cents": s.amount_in_cents,
            "reference": s.reference,
            "status": s.status,
            "wompi_transaction_id": s.wompi_transaction_id,
            "created_at": s.created_at.isoformat(),
        }
        for s in sessions
    ]


@router.get("/quota")
async def get_quota(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Return current billing period quota usage for the authenticated user's client."""
    client_repo = ClientRepository(db)
    clients = await client_repo.list_by_owner(user.user_id)
    if not clients:
        raise HTTPException(status_code=404, detail="Client profile not found.")
    client = clients[0]

    # Lazy expiry enforcement — downgrade before computing quota
    downgraded = await client_repo.enforce_expiry(client)
    if downgraded:
        await db.commit()

    period_start, _ = get_billing_period(client.plan_started_at)
    jobs_used = await AnalysisJobRepository(db).count_by_client_this_period(
        str(client.id), period_start
    )
    quota = build_quota_status(client.plan, jobs_used, client.plan_started_at)

    # Compute days remaining and renewal urgency
    now = datetime.now(tz=timezone.utc)
    days_remaining: int | None = None
    renewal_urgency = "ok"
    plan_expires_at_iso: str | None = None

    if client.plan != "free" and client.plan_expires_at:
        expires = client.plan_expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        delta = expires - now
        days_remaining = max(0, delta.days)
        plan_expires_at_iso = expires.isoformat()
        if days_remaining == 0:
            renewal_urgency = "expired"
        elif days_remaining <= 3:
            renewal_urgency = "critical"
        elif days_remaining <= 7:
            renewal_urgency = "warning"

    return {
        "plan": quota.plan,
        "subscription_status": client.subscription_status,
        "plan_expires_at": plan_expires_at_iso,
        "days_remaining": days_remaining,
        "renewal_urgency": renewal_urgency,
        "billing_period_start": quota.billing_period_start.isoformat(),
        "billing_period_end": quota.billing_period_end.isoformat(),
        "reports": {
            "limit": quota.reports_limit,
            "used": quota.reports_used,
            "remaining": quota.reports_remaining,
        },
        "conversations_per_report": quota.conversations_per_report,
        "lookback_days": quota.lookback_days,
        "features": {
            "manual_upload": quota.manual_upload,
            "trends_dashboard": quota.trends_dashboard,
        },
    }
