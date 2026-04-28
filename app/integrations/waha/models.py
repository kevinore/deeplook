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


class WahaChatOverview(BaseModel):
    id: str           # "5730012345@c.us" (DM) or "xxx@g.us" (group)
    name: Optional[str] = None
    lastMessage: Optional[dict] = None

    @field_validator("id", mode="before")
    @classmethod
    def coerce_id(cls, v: Any) -> str:
        return _coerce_jid(v)


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

    model_config = {"populate_by_name": True}

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
