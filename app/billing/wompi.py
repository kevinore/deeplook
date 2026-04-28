import hashlib
import logging
from datetime import datetime, timezone

from app.config import settings

logger = logging.getLogger(__name__)


def compute_integrity(reference: str, amount_in_cents: int, currency: str) -> str:
    """
    Wompi integrity hash for the payment widget.
    SHA256(reference + amount_in_cents + currency + integrity_secret)
    """
    text = f"{reference}{amount_in_cents}{currency}{settings.wompi_integrity_secret}"
    return hashlib.sha256(text.encode()).hexdigest()


def verify_event_signature(event_data: dict) -> bool:
    """
    Verify the Wompi webhook event signature.
    Checksum = SHA256(property_values... + timestamp + events_secret)
    The properties to concatenate are listed in event_data['signature']['properties'].
    """
    if not settings.wompi_events_secret:
        logger.warning("WOMPI_EVENTS_SECRET not set — skipping webhook signature verification")
        return True

    try:
        signature_block = event_data.get("signature", {})
        properties = signature_block.get("properties", [])
        checksum = signature_block.get("checksum", "")
        timestamp = str(event_data.get("timestamp", ""))
        data = event_data.get("data", {})

        values: list[str] = []
        for prop_path in properties:
            # Navigate nested keys like "transaction.id"
            parts = prop_path.split(".")
            node = data
            for part in parts:
                node = node.get(part, "") if isinstance(node, dict) else ""
            values.append(str(node))

        values.append(timestamp)
        values.append(settings.wompi_events_secret)

        computed = hashlib.sha256("".join(values).encode()).hexdigest()
        return computed == checksum
    except Exception as exc:
        logger.error("Wompi signature verification error: %s", exc)
        return False


def make_reference(client_id: str, plan: str) -> str:
    ts = int(datetime.now(tz=timezone.utc).timestamp())
    short_id = client_id.replace("-", "")[:10]
    return f"DL-{plan}-{short_id}-{ts}"


PLAN_PRICES: dict[str, int] = {
    "basic":      None,  # filled from settings at runtime
    "plus":       None,
    "enterprise": None,
}


def get_plan_amount(plan: str) -> int:
    mapping = {
        "basic":      settings.wompi_price_basic_cents,
        "plus":       settings.wompi_price_plus_cents,
        "enterprise": settings.wompi_price_enterprise_cents,
    }
    amount = mapping.get(plan)
    if not amount:
        raise ValueError(f"Unknown or free plan: {plan}")
    return amount
