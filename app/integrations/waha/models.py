from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


def _coerce_jid(v: Any) -> str:
    """WAHA sometimes returns a JID as an object instead of a plain string."""
    if isinstance(v, dict):
        return v.get("_serialized") or v.get("id") or v.get("user") or ""
    return str(v) if v is not None else ""


class WahaSessionStatus(str, Enum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    SCAN_QR_CODE = "SCAN_QR_CODE"
    WORKING = "WORKING"
    FAILED = "FAILED"
    # Set by DeepLook (not by WAHA) when the connected account is a personal
    # WhatsApp account and WAHA_REQUIRE_BUSINESS_ACCOUNT=true.
    PERSONAL_ACCOUNT_BLOCKED = "PERSONAL_ACCOUNT_BLOCKED"
    # Transient state: WAHA is WORKING but the business-account check has not completed yet.
    # The frontend shows a "verifying…" card during this window (typically 12-15 s).
    CHECKING_ACCOUNT = "CHECKING_ACCOUNT"


class WahaSessionMe(BaseModel):
    id: str           # "5730012345@c.us"
    pushName: str = ""

    @field_validator("id", mode="before")
    @classmethod
    def coerce_id(cls, v: Any) -> str:
        return _coerce_jid(v)


class WahaSessionInfo(BaseModel):
    name: str
    status: WahaSessionStatus
    me: Optional[WahaSessionMe] = None


class WahaChatLastMessage(BaseModel):
    """Slimmed-down view of `chat.lastMessage` returned by GET /api/{session}/chats."""
    timestamp: int = 0
    fromMe: bool = False
    body: Optional[str] = None
    type: Optional[str] = None
    ack: Optional[int] = None

    model_config = {"extra": "ignore"}

    @field_validator("timestamp", mode="before")
    @classmethod
    def coerce_ts(cls, v: Any) -> int:
        if v is None:
            return 0
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0


class WahaChatOverview(BaseModel):
    """
    Chat overview from GET /api/{session}/chats.

    Captures the rich metadata WAHA returns at the chat level — used to:
      • exclude muted/archived from "needs response" calculations,
      • cross-validate the unanswered count via `unreadCount`,
      • split groups vs DMs via `isGroup`.
    """
    id: str           # "5730012345@c.us" (DM) or "xxx@g.us" (group)
    name: Optional[str] = None
    isGroup: bool = False
    isReadOnly: bool = False
    unreadCount: int = 0
    timestamp: int = 0           # Unix epoch seconds — last activity
    archived: bool = False
    pinned: bool = False
    isLocked: bool = False
    isMuted: bool = False
    muteExpiration: int = 0
    lastMessage: Optional[WahaChatLastMessage] = None

    model_config = {"extra": "ignore"}

    @field_validator("id", mode="before")
    @classmethod
    def coerce_id(cls, v: Any) -> str:
        return _coerce_jid(v)

    @field_validator("timestamp", "muteExpiration", mode="before")
    @classmethod
    def coerce_ts(cls, v: Any) -> int:
        if v is None:
            return 0
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

    @field_validator("isGroup", "isReadOnly", "archived", "pinned", "isLocked", "isMuted", mode="before")
    @classmethod
    def coerce_bool(cls, v: Any) -> bool:
        if v is None:
            return False
        return bool(v)


class WahaAck(int, Enum):
    """
    WhatsApp delivery acknowledgement codes (WAHA `message.ack`):
      -1 ERROR     : delivery failed
       0 PENDING   : not yet sent (queued on this device)
       1 SERVER    : sent — accepted by WhatsApp server
       2 DEVICE    : delivered — single check on the recipient's device
       3 READ      : read — the recipient opened the chat (the famous double blue check)
       4 PLAYED    : audio/video message played by the recipient
    Source: WAHA docs (https://waha.devlike.pro/docs/how-to/messages/#ack-status)
    """
    ERROR = -1
    PENDING = 0
    SERVER = 1
    DEVICE = 2
    READ = 3
    PLAYED = 4


class WahaMessage(BaseModel):
    id: str
    timestamp: int = 0    # Unix epoch seconds; 0 means unknown
    from_: str = Field(alias="from", default="")
    fromMe: bool = False
    to: Optional[str] = None
    body: Optional[str] = None
    hasMedia: bool = False
    type: str = "unknown"  # "chat", "image", "video", "audio", "ptt", "document", etc.
    ack: Optional[int] = None
    ackName: Optional[str] = None  # human-readable ack: "PENDING", "SERVER", "DEVICE", "READ", "PLAYED"

    model_config = {"populate_by_name": True, "extra": "ignore"}

    @model_validator(mode="before")
    @classmethod
    def extract_type_from_data(cls, data: Any) -> Any:
        """WAHA messages endpoint omits `type` at the top level; fall back to _data.type."""
        if isinstance(data, dict) and not data.get("type"):
            _data = data.get("_data")
            if isinstance(_data, dict) and _data.get("type"):
                data = dict(data)
                data["type"] = _data["type"]
        return data

    @field_validator("from_", mode="before")
    @classmethod
    def coerce_from(cls, v: Any) -> str:
        return _coerce_jid(v)

    @field_validator("timestamp", mode="before")
    @classmethod
    def coerce_timestamp(cls, v: Any) -> int:
        if v is None:
            return 0
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0
