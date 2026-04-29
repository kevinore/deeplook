"""
Email notification service backed by Resend.

Three transactional emails:
- send_welcome()           — sent right after onboarding
- send_report_ready()      — sent when an analysis job finishes (PDF attached)
- send_renewal_reminder()  — sent 7 / 3 / 1 days before plan_expires_at

Design notes:
- Uses Jinja2 to render HTML + text templates side-by-side. Sending both is
  important for deliverability (clients that strip HTML still get the message).
- Resend's Python SDK is sync; we run it in asyncio.to_thread() so callers
  can `await` without blocking the event loop.
- Failures are logged and swallowed. Email must never break a user-facing
  request or a background job. Operationally we monitor with Resend's
  dashboard.
"""
from __future__ import annotations

import asyncio
import base64
import logging
from pathlib import Path

import resend
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import settings

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=select_autoescape(["html", "xml"]),
    enable_async=False,
    trim_blocks=True,
    lstrip_blocks=True,
)


def _format_cop(amount: int | float | None) -> str:
    if amount is None:
        return "—"
    return f"${int(amount):,}".replace(",", ".") + " COP"


_env.filters["cop"] = _format_cop


class EmailService:
    """Thin wrapper around Resend with our 3 transactional templates."""

    def __init__(self) -> None:
        self.api_key = settings.resend_api_key
        self.from_email = settings.email_from
        self.reply_to = settings.email_reply_to
        self.enabled = settings.email_enabled and bool(self.api_key)
        if self.enabled:
            resend.api_key = self.api_key
        else:
            logger.warning(
                "EmailService disabled — missing RESEND_API_KEY or EMAIL_ENABLED=false. "
                "Emails will be logged but not sent."
            )

    # ── Public API ─────────────────────────────────────────────────────────

    async def send_welcome(self, *, to_email: str, name: str, business_name: str) -> bool:
        ctx = {
            "name": name,
            "business_name": business_name,
            "dashboard_url": f"{settings.frontend_base_url}/app/inicio",
            "connect_url": f"{settings.frontend_base_url}/app/conectar",
        }
        return await self._send(
            to=to_email,
            subject="Bienvenido a DeepLook — empieza a entender tus conversaciones",
            template="welcome",
            context=ctx,
        )

    async def send_report_ready(
        self,
        *,
        to_email: str,
        name: str,
        business_name: str,
        job_id: str,
        conversation_count: int,
        health_score: float | None,
        pdf_bytes: bytes | None,
    ) -> bool:
        ctx = {
            "name": name,
            "business_name": business_name,
            "conversation_count": conversation_count,
            "health_score": int(round(health_score)) if health_score is not None else None,
            "report_url": f"{settings.frontend_base_url}/app/reports",
            "score_label": _score_label(health_score),
            "score_color": _score_color(health_score),
        }
        attachments = []
        if pdf_bytes:
            attachments.append({
                "filename": f"deeplook-reporte-{job_id[:8]}.pdf",
                "content": base64.b64encode(pdf_bytes).decode("ascii"),
            })
        return await self._send(
            to=to_email,
            subject=f"Tu reporte de {business_name} está listo",
            template="report_ready",
            context=ctx,
            attachments=attachments,
        )

    async def send_reconnect_required(
        self,
        *,
        to_email: str,
        name: str,
        business_name: str,
    ) -> bool:
        """
        Sent when WAHA reports the WhatsApp session as SCAN_QR_CODE — meaning
        WhatsApp unlinked our device (typically because the phone was offline
        more than 14 days). The user must scan a fresh QR to restore service.
        """
        ctx = {
            "name": name,
            "business_name": business_name,
            "connect_url": f"{settings.frontend_base_url}/app/conectar",
        }
        return await self._send(
            to=to_email,
            subject=f"Tu WhatsApp en DeepLook se desconectó — reconéctalo en 1 minuto",
            template="reconnect_required",
            context=ctx,
        )

    async def send_renewal_reminder(
        self,
        *,
        to_email: str,
        name: str,
        business_name: str,
        plan: str,
        days_remaining: int,
        plan_price_cop: int,
        stage: str,  # "7d" | "3d" | "1d"
    ) -> bool:
        urgency = {"7d": "info", "3d": "warning", "1d": "critical"}.get(stage, "info")
        subjects = {
            "7d": f"Tu plan {plan.title()} de DeepLook se renueva en 7 días",
            "3d": f"Quedan {days_remaining} días — renueva tu plan {plan.title()}",
            "1d": f"Último día — renueva tu plan {plan.title()} hoy",
        }
        ctx = {
            "name": name,
            "business_name": business_name,
            "plan": plan,
            "plan_label": plan.title(),
            "days_remaining": days_remaining,
            "plan_price_cop": plan_price_cop,
            "urgency": urgency,
            "renew_url": f"{settings.frontend_base_url}/app/settings",
        }
        return await self._send(
            to=to_email,
            subject=subjects.get(stage, subjects["7d"]),
            template="renewal_reminder",
            context=ctx,
        )

    # ── Internals ──────────────────────────────────────────────────────────

    async def _send(
        self,
        *,
        to: str,
        subject: str,
        template: str,
        context: dict,
        attachments: list[dict] | None = None,
    ) -> bool:
        try:
            html = _env.get_template(f"{template}.html").render(**context)
            text = _env.get_template(f"{template}.txt").render(**context)
        except Exception:
            logger.exception("Failed to render email template '%s'", template)
            return False

        if not self.enabled:
            logger.info(
                "Email skipped (service disabled) — template=%s to=%s subject=%r",
                template, to, subject,
            )
            return False

        payload: dict = {
            "from": self.from_email,
            "to": [to],
            "subject": subject,
            "html": html,
            "text": text,
            "reply_to": self.reply_to,
            # Transactional headers improve deliverability & set
            # expectations with mailbox providers (no marketing intent).
            "headers": {
                "X-Entity-Ref-ID": template,
            },
        }
        if attachments:
            payload["attachments"] = attachments

        try:
            resp = await asyncio.to_thread(resend.Emails.send, payload)
            logger.info(
                "Email sent — template=%s to=%s id=%s",
                template, to, getattr(resp, "id", None) or resp.get("id") if isinstance(resp, dict) else "?",
            )
            return True
        except Exception:
            logger.exception("Resend send failed — template=%s to=%s", template, to)
            return False


# ── Module-level helpers ──────────────────────────────────────────────────

def _score_label(score: float | None) -> str:
    if score is None:
        return "—"
    if score >= 85: return "Excelente"
    if score >= 70: return "Bueno"
    if score >= 55: return "Regular"
    if score >= 40: return "Deficiente"
    return "Crítico"


def _score_color(score: float | None) -> str:
    """Return a brand-aligned hex color for the badge."""
    if score is None:
        return "#6b7280"
    if score >= 70: return "#22c55e"   # green
    if score >= 55: return "#f59e0b"   # amber
    return "#ef4444"                     # red


# Singleton getter — the service has no per-request state.
_service: EmailService | None = None


def get_email_service() -> EmailService:
    global _service
    if _service is None:
        _service = EmailService()
    return _service
