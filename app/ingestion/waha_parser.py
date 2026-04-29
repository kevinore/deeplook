"""
WAHA parser — equivalent of txt_parser.py but for structured WAHA API data.
Much simpler than txt_parser: no regex, no timestamp guessing.
Produces the same NormalizedBatch shape so store_batch() and all downstream
analytics work without any changes.

Captures the rich chat-level metadata that WAHA returns (unreadCount, isMuted,
archived, lastMessage info, etc.) so deterministic metrics — delivery_rate,
read_rate, ghosted_rate, and operational coverage — can be computed
without involving the AI.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.ingestion.sessionizer import (
    DEFAULT_SESSION_GAP_HOURS,
    filter_junk,
    split_batch_into_sessions,
)
from app.integrations.waha.client import WahaClient
from app.integrations.waha.models import WahaChatOverview, WahaMessage
from app.models.enums import MessageDirection, MessageType
from app.models.normalized import NormalizedBatch, NormalizedConversation, NormalizedMessage

logger = logging.getLogger(__name__)

# Message types that carry no business-relevant content — skip them
_SKIP_TYPES = frozenset({
    "revoked",             # deleted messages
    "e2e_notification",    # encryption announcements
    "notification_template",
    "ephemeral_setting",
    "protocol",
    "reaction",            # emoji reactions
    "call_log",
    "gp2",                 # group protocol
    "poll_creation",
})

# WAHA type → our MessageType
_TYPE_MAP: dict[str, MessageType] = {
    "chat": MessageType.TEXT,
    "image": MessageType.IMAGE,
    "video": MessageType.VIDEO,
    "audio": MessageType.AUDIO,
    "ptt": MessageType.AUDIO,        # push-to-talk
    "document": MessageType.DOCUMENT,
    "location": MessageType.LOCATION,
    "vcard": MessageType.CONTACT,
    "sticker": MessageType.STICKER,
}

_PAUSE_BETWEEN_PAGES = 0.3   # seconds between paginated pages of the SAME chat
_WAHA_FETCH_CONCURRENCY = 3  # concurrent chat fetches — conservative for WAHA Core (single Chromium)


@dataclass
class WahaQualityReport:
    total_chats_fetched: int = 0
    total_messages_fetched: int = 0
    chats_skipped_groups: int = 0
    chats_skipped_archived: int = 0
    chats_skipped_muted: int = 0
    chats_dropped_junk: int = 0
    sessions_produced: int = 0
    messages_skipped_system: int = 0
    date_range_start: Optional[datetime] = None
    date_range_end: Optional[datetime] = None
    confidence_score: float = 0.95
    warnings: list[str] = field(default_factory=list)


def _strip_suffix(wa_id: str) -> str:
    """'5730012345@c.us' → '5730012345'"""
    return wa_id.split("@")[0]


def _waha_msg_to_normalized(
    msg: WahaMessage,
    chat_phone: str,
    chat_name: Optional[str],
    me_phone: Optional[str],
) -> Optional[NormalizedMessage]:
    if msg.type in _SKIP_TYPES:
        return None
    if msg.timestamp == 0:
        return None

    direction = MessageDirection.OUTBOUND if msg.fromMe else MessageDirection.INBOUND
    msg_type = _TYPE_MAP.get(msg.type, MessageType.UNKNOWN)
    ts = datetime.fromtimestamp(msg.timestamp, tz=timezone.utc)

    sender_raw = _strip_suffix(msg.from_)
    sender_phone = sender_raw if not msg.fromMe else (me_phone or sender_raw)
    sender_name = None if msg.fromMe else chat_name

    return NormalizedMessage(
        source_id=msg.id,
        timestamp=ts,
        direction=direction,
        sender_phone=sender_phone,
        sender_name=sender_name,
        message_type=msg_type,
        text_content=msg.body or None,
        ack=msg.ack,
    )


async def build_batch_from_waha(
    waha_client: WahaClient,
    session_name: str,
    client_id: str,
    since_datetime: datetime,
    me_phone: Optional[str] = None,
    max_chats: Optional[int] = None,
    session_gap_hours: float = DEFAULT_SESSION_GAP_HOURS,
    min_messages_per_session: int = 2,
) -> NormalizedBatch:
    """
    Pull all DM conversations from WAHA since `since_datetime`, split each chat
    into independent sessions (gap >= `session_gap_hours`), drop junk sessions
    (< `min_messages_per_session` messages), and return a NormalizedBatch ready
    for store_batch().
    """
    report = WahaQualityReport()
    raw_chat_conversations: list[NormalizedConversation] = []

    since_ts = int(since_datetime.timestamp())

    from app.config import settings

    all_chats = await waha_client.list_chats(session_name)
    report.total_chats_fetched = len(all_chats)

    # Separate groups from DMs (groups are irrelevant for business analytics)
    dm_chats = [c for c in all_chats if not c.id.endswith("@g.us")]
    report.chats_skipped_groups = len(all_chats) - len(dm_chats)

    # Archived chats: customer/business intentionally hid them — do not analyse
    # (silence ≠ lack of attention). Keep muted in the analysis but flag them
    # so health-score "coverage" is computed correctly downstream.
    visible_chats: list[WahaChatOverview] = []
    for c in dm_chats:
        if c.archived:
            report.chats_skipped_archived += 1
            continue
        if c.isMuted:
            report.chats_skipped_muted += 1
            # NOT skipped — kept for analysis with wa_is_muted=True; downstream
            # logic decides whether to count them in unanswered metrics.
        visible_chats.append(c)

    # Apply chat cap — list_chats returns most-recently-active first, so this
    # keeps the N most active conversations and discards the rest.
    effective_max = max_chats if max_chats is not None else settings.waha_max_chats
    if effective_max > 0:
        visible_chats = visible_chats[:effective_max]

    sem = asyncio.Semaphore(_WAHA_FETCH_CONCURRENCY)

    async def _fetch_one_chat(chat: WahaChatOverview) -> Optional[tuple[NormalizedConversation, dict]]:
        """Fetch one chat inside the semaphore. Returns (conversation, partial_report) or None."""
        chat_phone = _strip_suffix(chat.id)
        chat_name = chat.name
        all_messages: list[WahaMessage] = []

        async with sem:
            try:
                offset = 0
                page_size = 500
                while True:
                    batch = await waha_client.get_chat_messages(
                        session_name, chat.id, limit=page_size, since_ts=since_ts, offset=offset
                    )
                    all_messages.extend(batch)
                    if len(batch) < page_size:
                        break
                    offset += page_size
                    await asyncio.sleep(_PAUSE_BETWEEN_PAGES)
            except httpx.ReadTimeout:
                logger.warning("ReadTimeout fetching messages for chat %s — skipping", chat_phone)
                return None, {"warnings": [f"Chat {chat_phone}: skipped due to ReadTimeout"], "confidence_penalty": 0.8, "messages": 0, "skipped_system": 0}
            except Exception as exc:
                logger.warning("Error fetching messages for chat %s: %s — skipping", chat_phone, exc)
                return None, {"warnings": [f"Chat {chat_phone}: skipped due to error ({type(exc).__name__})"], "confidence_penalty": None, "messages": 0, "skipped_system": 0}

        norm_messages: list[NormalizedMessage] = []
        skipped_system = 0
        for raw_msg in all_messages:
            nm = _waha_msg_to_normalized(raw_msg, chat_phone, chat_name, me_phone)
            if nm is None:
                skipped_system += 1
            else:
                norm_messages.append(nm)

        partial = {"warnings": [], "confidence_penalty": None, "messages": len(all_messages), "skipped_system": skipped_system}

        if not norm_messages:
            return None, partial

        outbound = sum(1 for m in norm_messages if m.direction == MessageDirection.OUTBOUND)
        if outbound == 0:
            partial["warnings"].append(f"Chat {chat_phone}: no outbound messages — business never replied")
            # NOT a confidence penalty: this is precisely the "sin responder" signal we want.

        # Capture chat-level metadata directly from WAHA so downstream
        # deterministic metrics (read_rate, ghosting, coverage) have full context.
        last_activity_ts: Optional[datetime] = None
        last_msg_from_me: Optional[bool] = None
        if chat.lastMessage and chat.lastMessage.timestamp:
            last_activity_ts = datetime.fromtimestamp(chat.lastMessage.timestamp, tz=timezone.utc)
            last_msg_from_me = bool(chat.lastMessage.fromMe)
        elif chat.timestamp:
            last_activity_ts = datetime.fromtimestamp(chat.timestamp, tz=timezone.utc)

        conv = NormalizedConversation(
            contact_phone=chat_phone,
            contact_name=chat_name,
            messages=sorted(norm_messages, key=lambda m: m.timestamp),
            source="waha",
            wa_chat_id=chat.id,
            wa_unread_count=chat.unreadCount,
            wa_is_muted=chat.isMuted,
            wa_is_archived=chat.archived,
            wa_is_pinned=chat.pinned,
            wa_last_activity_ts=last_activity_ts,
            wa_last_message_from_me=last_msg_from_me,
        )
        return conv, partial

    chat_results = await asyncio.gather(*[_fetch_one_chat(c) for c in visible_chats])

    for conv, partial in chat_results:
        report.total_messages_fetched += partial.get("messages", 0)
        report.messages_skipped_system += partial.get("skipped_system", 0)
        report.warnings.extend(partial.get("warnings", []))
        if partial.get("confidence_penalty"):
            report.confidence_score = min(report.confidence_score, partial["confidence_penalty"])

        if conv is None:
            continue

        timestamps = [m.timestamp for m in conv.messages]
        earliest, latest = min(timestamps), max(timestamps)
        if report.date_range_start is None or earliest < report.date_range_start:
            report.date_range_start = earliest
        if report.date_range_end is None or latest > report.date_range_end:
            report.date_range_end = latest

        raw_chat_conversations.append(conv)

    # ─── Sessionize & filter ───────────────────────────────────────────────
    # 1) Split each chat into independent sessions wherever messages are
    #    separated by ≥ session_gap_hours (default 6h).
    sessionized = split_batch_into_sessions(raw_chat_conversations, gap_hours=session_gap_hours)
    # 2) Drop sessions too small to analyse meaningfully. A "session" with 1
    #    isolated message is rarely a real interaction — usually a misdirected
    #    text or a one-off greeting.
    pre_filter = len(sessionized)
    final_conversations = filter_junk(sessionized, min_messages=min_messages_per_session)
    report.chats_dropped_junk = pre_filter - len(final_conversations)
    report.sessions_produced = len(final_conversations)

    if not final_conversations:
        report.warnings.append("No analysable sessions found in the sync window")

    return NormalizedBatch(
        client_id=client_id,
        source="waha",
        conversations=final_conversations,
        raw_metadata={
            "waha_quality_report": {
                "total_chats_fetched": report.total_chats_fetched,
                "total_messages_fetched": report.total_messages_fetched,
                "chats_skipped_groups": report.chats_skipped_groups,
                "chats_skipped_archived": report.chats_skipped_archived,
                "chats_skipped_muted": report.chats_skipped_muted,
                "chats_dropped_junk": report.chats_dropped_junk,
                "sessions_produced": report.sessions_produced,
                "messages_skipped_system": report.messages_skipped_system,
                "date_range_start": report.date_range_start.isoformat() if report.date_range_start else None,
                "date_range_end": report.date_range_end.isoformat() if report.date_range_end else None,
                "confidence_score": report.confidence_score,
                "warnings": report.warnings,
                "session_gap_hours": session_gap_hours,
            }
        },
    )
