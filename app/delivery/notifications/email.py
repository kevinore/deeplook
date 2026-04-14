"""
Email notification sender (Phase 2 — stub).
"""
import logging

logger = logging.getLogger(__name__)


async def send_report_email(to_email: str, business_name: str, report_url: str) -> bool:
    """Send a report ready notification email. Phase 2 implementation."""
    logger.info("Email notification (Phase 2 stub): to=%s url=%s", to_email, report_url)
    return True
