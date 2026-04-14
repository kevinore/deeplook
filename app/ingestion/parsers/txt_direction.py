"""
Business vs Customer direction detection for WhatsApp .txt exports.
"""
import re
from collections import Counter


def _normalize_phone(phone: str) -> str:
    """Strip all non-digit characters and return last 10 digits."""
    digits = re.sub(r"\D", "", phone)
    return digits[-10:] if len(digits) >= 10 else digits


def detect_direction(
    sender: str,
    business_identifiers: list[str],
) -> str:
    """
    Return 'outbound' if sender matches any business identifier, else 'inbound'.

    Matching rules:
    - Case-insensitive partial string match
    - For phone-like identifiers, normalize and compare last 10 digits
    """
    sender_lower = sender.lower().strip()
    sender_digits = _normalize_phone(sender)

    for identifier in business_identifiers:
        ident_lower = identifier.lower().strip()
        ident_digits = _normalize_phone(identifier)

        # Partial text match
        if ident_lower and (ident_lower in sender_lower or sender_lower in ident_lower):
            return "outbound"

        # Phone digit match
        if ident_digits and sender_digits and ident_digits == sender_digits:
            return "outbound"

    return "inbound"


def auto_detect_business(senders: list[str]) -> tuple[str | None, bool]:
    """
    Heuristic: the sender who sends the most messages that has a display name
    (not just digits/phone format) is likely the business.

    Returns (business_sender_name_or_None, is_confident).
    is_confident is False when auto-detection was used (no identifiers provided).
    """
    if not senders:
        return None, False

    counter = Counter(senders)
    # Prefer senders that look like names (contain letters) over phone numbers
    name_senders = [s for s in counter if re.search(r"[a-zA-ZáéíóúñüÁÉÍÓÚÑÜ]", s)]

    if name_senders:
        # Most frequent name-sender is assumed to be the business
        business = max(name_senders, key=lambda s: counter[s])
    else:
        # Fall back to most frequent sender overall
        business = counter.most_common(1)[0][0]

    return business, False
