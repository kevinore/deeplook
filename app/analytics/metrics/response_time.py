"""
Response time calculations — pure math, no AI, no external calls.
"""
import statistics
from collections import defaultdict
from datetime import datetime, timedelta

from app.models.enums import MessageDirection
from app.models.normalized import NormalizedMessage

# Colombia Time = UTC-5. Business hours: Mon–Fri 08:00–18:00.
_COLOMBIA_UTC_OFFSET_H = -5
_BH_START_H = 8
_BH_END_H = 18


def _business_hours_elapsed_seconds(start: datetime, end: datetime) -> float:
    """
    Elapsed seconds between start and end counting only Mon–Fri 08:00–18:00
    Colombia time (UTC-5).  Both datetimes are assumed to be naive UTC.
    """
    if end <= start:
        return 0.0
    offset = timedelta(hours=_COLOMBIA_UTC_OFFSET_H)
    cur = start + offset
    target = end + offset
    # Strip tz info if present (defensive)
    if getattr(cur, "tzinfo", None) is not None:
        cur = cur.replace(tzinfo=None)
    if getattr(target, "tzinfo", None) is not None:
        target = target.replace(tzinfo=None)

    total = 0.0
    while cur < target:
        wd = cur.weekday()   # 0=Mon … 6=Sun
        h = cur.hour
        if wd >= 5:
            # Weekend → next Monday 08:00
            days_ahead = (7 - wd) % 7 or 7
            next_start = (cur + timedelta(days=days_ahead)).replace(
                hour=_BH_START_H, minute=0, second=0, microsecond=0
            )
            cur = min(next_start, target)
        elif h >= _BH_END_H:
            # After hours today → next weekday 08:00
            next_day = (cur + timedelta(days=1)).replace(
                hour=_BH_START_H, minute=0, second=0, microsecond=0
            )
            while next_day.weekday() >= 5:
                next_day += timedelta(days=1)
            cur = min(next_day, target)
        elif h < _BH_START_H:
            # Before hours today
            cur = min(cur.replace(hour=_BH_START_H, minute=0, second=0, microsecond=0), target)
        else:
            # Inside business hours → accumulate until block end or target
            block_end = cur.replace(hour=_BH_END_H, minute=0, second=0, microsecond=0)
            chunk_end = min(block_end, target)
            total += (chunk_end - cur).total_seconds()
            cur = chunk_end
    return total


def _collect_response_times_bh(messages: list[NormalizedMessage]) -> list[float]:
    """Same as _collect_response_times but elapsed time counts only business hours."""
    sorted_msgs = sorted(messages, key=lambda m: m.timestamp)
    response_times: list[float] = []
    waiting_since: datetime | None = None

    for msg in sorted_msgs:
        if msg.direction == MessageDirection.INBOUND and waiting_since is None:
            waiting_since = msg.timestamp
        elif msg.direction == MessageDirection.OUTBOUND and waiting_since is not None:
            bh_delta = _business_hours_elapsed_seconds(waiting_since, msg.timestamp)
            response_times.append(max(0.0, bh_delta))
            waiting_since = None

    return response_times


def average_business_hours(messages: list[NormalizedMessage]) -> float | None:
    """Average response time counting only Mon–Fri 08:00–18:00 Colombia time."""
    times = _collect_response_times_bh(messages)
    return statistics.mean(times) if times else None


def _collect_response_times(messages: list[NormalizedMessage]) -> list[float]:
    """
    Collect response times in seconds.

    Logic: iterate chronologically. When INBOUND is found, start timer.
    The next OUTBOUND closes it. Consecutive INBOUNDs don't reset the timer.
    Consecutive OUTBOUNDs (follow-ups) are ignored.
    """
    sorted_msgs = sorted(messages, key=lambda m: m.timestamp)
    response_times: list[float] = []
    waiting_since: datetime | None = None

    for msg in sorted_msgs:
        if msg.direction == MessageDirection.INBOUND and waiting_since is None:
            waiting_since = msg.timestamp
        elif msg.direction == MessageDirection.OUTBOUND and waiting_since is not None:
            delta = (msg.timestamp - waiting_since).total_seconds()
            response_times.append(max(0.0, delta))
            waiting_since = None

    return response_times


def percentile_of_values(values: list[float], pct: float) -> float | None:
    """
    Compute the given percentile (0-100) of a list of floats using linear interpolation
    between the two closest ranks.

    Returns None for empty input. For a single value, returns that value.
    For very small samples (< 5) the result is dominated by the highest values
    and should be interpreted with caution — the PDF flags this with a confidence note.
    """
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    sorted_vals = sorted(values)
    rank = (pct / 100.0) * (len(sorted_vals) - 1)
    lo = int(rank)
    hi = lo + 1
    if hi >= len(sorted_vals):
        return float(sorted_vals[-1])
    weight = rank - lo
    return float(sorted_vals[lo]) * (1.0 - weight) + float(sorted_vals[hi]) * weight


def average(messages: list[NormalizedMessage]) -> float | None:
    times = _collect_response_times(messages)
    return statistics.mean(times) if times else None


def median(messages: list[NormalizedMessage]) -> float | None:
    times = _collect_response_times(messages)
    return statistics.median(times) if times else None


def percentile_95(messages: list[NormalizedMessage]) -> float | None:
    """95th percentile of response times, using proper linear interpolation."""
    return percentile_of_values(_collect_response_times(messages), 95.0)


def max_response_time(messages: list[NormalizedMessage]) -> float | None:
    times = _collect_response_times(messages)
    return max(times) if times else None


import unicodedata as _ucd

# Known closing/acknowledgment words. A message consisting ONLY of these words
# (optionally combined with emojis) is considered a conversation-ending courtesy
# that doesn't require a business reply.
# If the client adds ANY other word (question, request, new topic), the entire
# message is treated as unanswered — the rule is strict to avoid false negatives.
_CLOSING_WORDS: frozenset[str] = frozenset({
    "ok", "okay", "okey",
    "gracias", "muchas", "mil",
    "bien", "listo", "dale", "va",
    "perfecto", "claro", "entendido",
    "excelente", "genial", "bueno",
    "de", "acuerdo",
    "chévere", "chevere", "chévere",
    "super", "súper",
    "👍", "✅", "🙏", "😊", "🤝", "👌", "💪", "✔", "☑",
})
_MAX_CLOSING_WORDS = 5  # messages longer than this are never filtered


def _token_is_closing(token: str) -> bool:
    """True if a single word token is either a closing word or a pure emoji/symbol."""
    cleaned = token.lower().strip("!.?¡¿,;:'\"-")
    if cleaned in _CLOSING_WORDS:
        return True
    # Pure emoji / symbol token — no letters or digits at all
    return bool(cleaned) and not any(
        _ucd.category(c)[0] in ("L", "N") for c in cleaned
    )


def _is_trailing_acknowledgment(msg: NormalizedMessage) -> bool:
    """
    True when the message is a pure courtesy closing that needs no reply.

    Filtered:
      • Sticker / emoji-reaction messages (WAHA type=sticker or type=unknown+empty)
      • Messages consisting ONLY of closing words and/or emojis:
          "gracias"          → filter
          "ok"               → filter
          "dale 👍"          → filter (closing word + emoji)
          "muchas gracias"   → filter (both are closing words)
          "de acuerdo"       → filter (both are closing words)
      • Pure emoji sequences with no text: "👍", "✅✅", "🙏😊"

    NOT filtered (counted as unanswered):
      • Any message containing even one non-closing word:
          "gracias, ¿cuándo me lo envían?" → NOT filtered (has a question)
          "ok, ¿y el precio?"              → NOT filtered
          "listo, ya pagué"                → NOT filtered ("ya", "pagué" ≠ closing)
          "ok 👍 pero ¿qué debo llevar?"  → NOT filtered
    """
    from app.models.enums import MessageType

    msg_type = getattr(msg, "message_type", MessageType.TEXT)

    if msg_type == MessageType.STICKER:
        return True

    text = (msg.text_content or "").strip()

    # WAHA emoji reactions arrive as type=UNKNOWN with empty text
    if msg_type == MessageType.UNKNOWN and not text:
        return True

    # Media messages (image, audio, doc) with no caption — client sent something,
    # needs a response
    if not text:
        return False

    words = text.split()
    if len(words) > _MAX_CLOSING_WORDS:
        return False  # too long to be a simple acknowledgment

    # Every word must be a closing token or pure emoji — otherwise not filtered
    return all(_token_is_closing(w) for w in words)


def is_unanswered(messages: list[NormalizedMessage]) -> bool:
    """
    True iff the conversation ended with a substantive INBOUND message
    (customer wrote last and the business has not replied).

    Deterministic rule: scan backwards through messages.
      • OUTBOUND found first  → answered (False)
      • INBOUND that is a pure reaction/emoji → skip (not a real message turn)
      • INBOUND with any textual content      → unanswered (True)

    Text messages — even short ones like "gracias" or "ok" — are always
    counted as unanswered because in a sales context they may signal a
    client still waiting for a follow-up, not a closed deal.
    """
    sorted_msgs = sorted(messages, key=lambda m: m.timestamp)
    for msg in reversed(sorted_msgs):
        if msg.direction == MessageDirection.INBOUND:
            if _is_trailing_acknowledgment(msg):
                continue  # pure emoji reaction — not a real conversation turn
            return True
        if msg.direction == MessageDirection.OUTBOUND:
            return False
    return False


def unanswered_count(messages: list[NormalizedMessage]) -> int:
    """
    Per-conversation indicator: 1 if the conversation ended with the customer
    waiting (last message INBOUND), 0 otherwise.

    The DB column keeps the historic name `unanswered_count` for compatibility,
    but the semantic is now boolean-per-conversation. Summing across all
    conversations in a job yields the number of *conversations awaiting reply*,
    not the number of trailing customer messages.
    """
    return 1 if is_unanswered(messages) else 0


def trailing_inbound_messages(messages: list[NormalizedMessage]) -> int:
    """
    Diagnostic metric: number of consecutive trailing INBOUND messages at the
    end of the conversation. Useful for prioritising which unanswered chats are
    "screaming" vs. waiting quietly.

    Returns 0 if the conversation is answered.
    """
    sorted_msgs = sorted(messages, key=lambda m: m.timestamp)
    count = 0
    for msg in reversed(sorted_msgs):
        if msg.direction == MessageDirection.INBOUND:
            count += 1
        elif msg.direction == MessageDirection.OUTBOUND:
            break
    return count


# Heuristic thresholds for auto-reply detection (S2).
# A first OUTBOUND that fires within `_AUTOREPLY_FAST_SECONDS` after the customer's
# first INBOUND, AND is followed by another OUTBOUND within `_AUTOREPLY_FOLLOWUP_WINDOW`,
# is treated as an automated greeting/welcome and excluded from the FRT measurement.
# These thresholds are conservative — most real human replies on WhatsApp Business take
# at least 10–15 seconds to compose.
_AUTOREPLY_FAST_SECONDS = 10.0
_AUTOREPLY_FOLLOWUP_WINDOW = 1800.0   # 30 min — real human reply typically arrives within this window


def first_response_time(messages: list[NormalizedMessage]) -> float | None:
    """
    First response time: seconds from the customer's first message to the business's
    first *real* reply.

    If the conversation opens with business messages (welcome/greeting), those are skipped —
    measurement starts from the first INBOUND message.

    Auto-reply guard: if the first OUTBOUND fires < `_AUTOREPLY_FAST_SECONDS`
    after the customer's first INBOUND AND another OUTBOUND follows within
    `_AUTOREPLY_FOLLOWUP_WINDOW`, the first OUTBOUND is considered an automated
    response and the timer measures up to the *second* OUTBOUND instead. This
    prevents WhatsApp Business' "estamos en línea — en breve te atendemos"
    auto-replies from making the FRT artificially look like 2 seconds.

    Returns None if the business never replies.
    """
    sorted_msgs = sorted(messages, key=lambda m: m.timestamp)
    first_inbound_time: datetime | None = None
    candidate_first_reply: datetime | None = None
    candidate_idx: int | None = None

    for i, msg in enumerate(sorted_msgs):
        if msg.direction == MessageDirection.INBOUND and first_inbound_time is None:
            first_inbound_time = msg.timestamp
            continue
        if msg.direction == MessageDirection.OUTBOUND and first_inbound_time is not None:
            candidate_first_reply = msg.timestamp
            candidate_idx = i
            break

    if candidate_first_reply is None or first_inbound_time is None or candidate_idx is None:
        return None  # Business never replied

    initial_gap = (candidate_first_reply - first_inbound_time).total_seconds()

    # If the first OUTBOUND was suspiciously quick AND another OUTBOUND follows
    # within the auto-reply window, prefer the second OUTBOUND as the "real" reply.
    if 0 <= initial_gap < _AUTOREPLY_FAST_SECONDS:
        for nxt in sorted_msgs[candidate_idx + 1:]:
            if nxt.direction == MessageDirection.OUTBOUND:
                followup_gap = (nxt.timestamp - candidate_first_reply).total_seconds()
                if 0 < followup_gap <= _AUTOREPLY_FOLLOWUP_WINDOW:
                    return max(0.0, (nxt.timestamp - first_inbound_time).total_seconds())
                break  # second OUTBOUND too far away → first one was probably real
            if nxt.direction == MessageDirection.INBOUND:
                # Customer sent another message before any follow-up reply; the
                # quick first OUTBOUND was the real reply.
                break

    return max(0.0, initial_gap)


def by_hour(messages: list[NormalizedMessage]) -> dict[int, float]:
    """
    Median response time grouped by hour of day (0-23) in Colombia time (UTC-5).

    Uses median (not mean) so a single outlier exchange doesn't dominate a bucket.
    Buckets with fewer than 2 samples are excluded — one data point is not
    representative of an "average" for that hour.
    """
    sorted_msgs = sorted(messages, key=lambda m: m.timestamp)
    hour_times: dict[int, list[float]] = defaultdict(list)
    waiting_since: datetime | None = None
    hour_of_wait: int | None = None

    for msg in sorted_msgs:
        if msg.direction == MessageDirection.INBOUND and waiting_since is None:
            waiting_since = msg.timestamp
            # Convert UTC → Colombia time (UTC-5)
            hour_of_wait = (msg.timestamp + timedelta(hours=_COLOMBIA_UTC_OFFSET_H)).hour
        elif msg.direction == MessageDirection.OUTBOUND and waiting_since is not None:
            delta = (msg.timestamp - waiting_since).total_seconds()
            if hour_of_wait is not None:
                hour_times[hour_of_wait].append(max(0.0, delta))
            waiting_since = None
            hour_of_wait = None

    return {
        h: statistics.median(times)
        for h, times in hour_times.items()
        if len(times) >= 2
    }
