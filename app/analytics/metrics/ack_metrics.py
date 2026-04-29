"""
Deterministic delivery & read metrics derived from WAHA's `message.ack` field.

WAHA ack codes (from `WahaAck` enum):
    -1 ERROR     : delivery failed
     0 PENDING   : not yet sent
     1 SERVER    : accepted by WhatsApp server
     2 DEVICE    : delivered to recipient's device
     3 READ      : recipient opened the chat (double blue check)
     4 PLAYED    : audio/video played by recipient

These metrics give us deterministic visibility that the AI can't infer from
text alone:
  • read_rate — what % of our outbound messages were actually read
  • delivery_rate — % accepted by WhatsApp servers
  • is_ghosted — the customer READ our last message but never replied
  • last_business_msg_ack — the ack of our most recent outbound, useful for
    classifying "pending" conversations (delivered? read?)

For .txt-uploaded conversations (no WAHA), `ack` is None on every message and
all rates return None.
"""
from datetime import datetime, timezone

from app.models.enums import MessageDirection
from app.models.normalized import NormalizedMessage

ACK_SERVER = 1   # delivered to WhatsApp server
ACK_DEVICE = 2   # delivered to recipient's device
ACK_READ = 3     # recipient opened the chat
ACK_PLAYED = 4   # audio/video played

# After this many seconds with no customer reply, an OUTBOUND that's been READ
# is treated as "ghosted by customer" — a strong lost-sale signal.
GHOSTING_THRESHOLD_SECONDS = 86_400.0   # 24 hours


def _outbound_with_ack(messages: list[NormalizedMessage]) -> list[NormalizedMessage]:
    """Return outbound messages that carry an ack (i.e. originated from a WAHA sync)."""
    return [m for m in messages if m.direction == MessageDirection.OUTBOUND and m.ack is not None]


def delivery_rate(messages: list[NormalizedMessage]) -> float | None:
    """
    % of outbound messages successfully delivered to WhatsApp's server (ack ≥ 1).
    Returns None when no outbound has ack info (e.g. .txt upload).
    """
    eligible = _outbound_with_ack(messages)
    if not eligible:
        return None
    delivered = sum(1 for m in eligible if (m.ack or -1) >= ACK_SERVER)
    return round(delivered / len(eligible) * 100, 1)


def read_rate(messages: list[NormalizedMessage]) -> float | None:
    """
    % of outbound messages READ by the customer (ack == 3 or 4).
    Returns None when no outbound has ack info.
    """
    eligible = _outbound_with_ack(messages)
    if not eligible:
        return None
    read = sum(1 for m in eligible if (m.ack or 0) >= ACK_READ)
    return round(read / len(eligible) * 100, 1)


def last_business_msg_ack(messages: list[NormalizedMessage]) -> int | None:
    """The ack of the most recent OUTBOUND message, or None if no outbound."""
    sorted_msgs = sorted(messages, key=lambda m: m.timestamp)
    for msg in reversed(sorted_msgs):
        if msg.direction == MessageDirection.OUTBOUND:
            return msg.ack
    return None


def is_ghosted(
    messages: list[NormalizedMessage],
    threshold_seconds: float = GHOSTING_THRESHOLD_SECONDS,
    now: datetime | None = None,
) -> bool:
    """
    True iff:
      • the conversation's last message is OUTBOUND (we wrote last),
      • that OUTBOUND has ack >= READ (customer opened the chat),
      • more than `threshold_seconds` have elapsed since.

    Strong "lost sale" signal — the customer saw our message and walked away.
    Returns False when ack info isn't available (e.g. .txt upload).
    """
    sorted_msgs = sorted(messages, key=lambda m: m.timestamp)
    if not sorted_msgs:
        return False

    # The last meaningful message must be OUTBOUND
    last = None
    for msg in reversed(sorted_msgs):
        if msg.direction in (MessageDirection.OUTBOUND, MessageDirection.INBOUND):
            last = msg
            break
    if last is None or last.direction != MessageDirection.OUTBOUND:
        return False

    if last.ack is None or last.ack < ACK_READ:
        return False

    reference = now if now is not None else datetime.now(tz=timezone.utc)
    last_ts = last.timestamp
    if last_ts.tzinfo is None:
        last_ts = last_ts.replace(tzinfo=timezone.utc)
    elapsed = (reference - last_ts).total_seconds()
    return elapsed >= threshold_seconds


# ─── Operational coverage (replaces the hardcoded 50) ─────────────────────────
# Default business-hours window used for operational coverage. Tunable per client
# in a future iteration; keep it conservative — most Colombian MiPymes operate
# Mon-Sat 8 AM to 7 PM.
DEFAULT_BUSINESS_HOURS_START = 8     # inclusive
DEFAULT_BUSINESS_HOURS_END = 19      # exclusive


def inbound_in_business_hours(
    messages: list[NormalizedMessage],
    start_hour: int = DEFAULT_BUSINESS_HOURS_START,
    end_hour: int = DEFAULT_BUSINESS_HOURS_END,
) -> tuple[int, int]:
    """
    Split inbound messages into (business_hours_count, after_hours_count).

    A message is "in business hours" if its hour is in [start_hour, end_hour).
    """
    in_hours = 0
    after_hours = 0
    for m in messages:
        if m.direction != MessageDirection.INBOUND:
            continue
        hour = m.timestamp.hour
        if start_hour <= hour < end_hour:
            in_hours += 1
        else:
            after_hours += 1
    return in_hours, after_hours


def out_of_hours_rate(
    messages: list[NormalizedMessage],
    start_hour: int = DEFAULT_BUSINESS_HOURS_START,
    end_hour: int = DEFAULT_BUSINESS_HOURS_END,
) -> float | None:
    """
    % of customer messages that arrived outside business hours.
    Useful context: a slow average-response-time becomes more forgivable when
    a large share of inbound traffic is at 3 AM.
    """
    in_hours, after_hours = inbound_in_business_hours(messages, start_hour, end_hour)
    total = in_hours + after_hours
    if total == 0:
        return None
    return round(after_hours / total * 100, 1)


def operational_coverage_score(
    messages: list[NormalizedMessage],
    start_hour: int = DEFAULT_BUSINESS_HOURS_START,
    end_hour: int = DEFAULT_BUSINESS_HOURS_END,
    answer_window_seconds: float = 3600.0,
) -> float | None:
    """
    Score 0-100 for the operational-coverage health-score component.

    Logic: walk the conversation chronologically. Each time an INBOUND triggers
    a "wait" (no prior open wait), record whether it arrived during business
    hours. When the next OUTBOUND closes the wait, mark it answered if the
    elapsed time ≤ `answer_window_seconds` (default 1 h).

    The score is the % of in-hours waits that were answered within the window.
    Out-of-hours arrivals are excluded from the denominator — we don't penalise
    the business for not answering messages at 4 AM.

    Returns None if there were no in-hours waits to evaluate.
    """
    sorted_msgs = sorted(messages, key=lambda m: m.timestamp)

    in_hours_total = 0
    in_hours_answered = 0
    waiting_since: NormalizedMessage | None = None

    for msg in sorted_msgs:
        if msg.direction == MessageDirection.INBOUND:
            if waiting_since is None:
                waiting_since = msg
        elif msg.direction == MessageDirection.OUTBOUND and waiting_since is not None:
            elapsed = (msg.timestamp - waiting_since.timestamp).total_seconds()
            if start_hour <= waiting_since.timestamp.hour < end_hour:
                in_hours_total += 1
                if 0 <= elapsed <= answer_window_seconds:
                    in_hours_answered += 1
            waiting_since = None

    # An open wait at the end means an in-hours arrival went unanswered.
    if waiting_since is not None and start_hour <= waiting_since.timestamp.hour < end_hour:
        in_hours_total += 1

    if in_hours_total == 0:
        return None
    return round(in_hours_answered / in_hours_total * 100, 1)
