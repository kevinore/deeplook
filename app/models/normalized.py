from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import MessageDirection, MessageType


class NormalizedMessage(BaseModel):
    """
    Source-agnostic message shape produced by either txt_parser or waha_parser.

    `ack` carries the WAHA delivery state for OUTBOUND messages (None when
    the source is .txt or the value isn't available). It enables deterministic
    metrics: delivery_rate (ack >= 1), read_rate (ack == 3), and ghosting
    detection (last OUTBOUND was READ but the customer never replied).
    """
    source_id: str | None = None
    timestamp: datetime
    direction: MessageDirection
    sender_phone: str | None = None
    sender_name: str | None = None
    recipient_phone: str | None = None
    message_type: MessageType = MessageType.TEXT
    text_content: str | None = None
    media_url: str | None = None
    # WAHA ack code: -1 ERROR, 0 PENDING, 1 SERVER, 2 DEVICE, 3 READ, 4 PLAYED.
    # Only meaningful for OUTBOUND messages from a live WhatsApp connection.
    ack: int | None = None
    metadata: dict = Field(default_factory=dict)


class NormalizedConversation(BaseModel):
    """
    A single conversation with one contact.

    For WAHA sources: one WhatsApp chat (contact) = one NormalizedConversation
    covering the full lookback window (e.g., last 30 days for Basic plan).

    For txt_upload sources: the sessionizer may split a single chat export into
    multiple NormalizedConversation objects based on time gaps; session_index /
    session_count track the position within that split.

    WAHA-only fields (`wa_*`) carry chat-level metadata captured at sync time.
    These are None for .txt-uploaded conversations.
    """
    contact_phone: str
    contact_name: str | None = None
    messages: list[NormalizedMessage] = Field(default_factory=list)
    source: str  # "txt_upload", "meta_api", "meta_history", "waha"

    # Session-split bookkeeping (used by txt_upload sessionizer; always 0/1 for waha)
    session_index: int = 0           # 0 = first session of this chat in the batch
    session_count: int = 1           # how many sessions this chat was split into

    # Chat-level metadata from the source (WAHA in particular)
    wa_chat_id: str | None = None             # raw WAHA chat id (e.g. "57300...@c.us")
    wa_unread_count: int | None = None         # WAHA's `chat.unreadCount` at sync time
    wa_is_muted: bool = False
    wa_is_archived: bool = False
    wa_is_pinned: bool = False
    wa_last_activity_ts: datetime | None = None
    # Last message direction at sync time (from chat overview's lastMessage.fromMe).
    # Useful as a cross-check against our own is_unanswered() computation.
    wa_last_message_from_me: bool | None = None


class NormalizedBatch(BaseModel):
    client_id: str
    source: str
    ingested_at: datetime = Field(default_factory=datetime.utcnow)
    conversations: list[NormalizedConversation] = Field(default_factory=list)
    raw_metadata: dict = Field(default_factory=dict)
