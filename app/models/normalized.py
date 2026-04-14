from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import MessageDirection, MessageType


class NormalizedMessage(BaseModel):
    source_id: str | None = None
    timestamp: datetime
    direction: MessageDirection
    sender_phone: str | None = None
    sender_name: str | None = None
    recipient_phone: str | None = None
    message_type: MessageType = MessageType.TEXT
    text_content: str | None = None
    media_url: str | None = None
    metadata: dict = Field(default_factory=dict)


class NormalizedConversation(BaseModel):
    contact_phone: str
    contact_name: str | None = None
    messages: list[NormalizedMessage] = Field(default_factory=list)
    source: str  # "txt_upload", "meta_api", "meta_history"


class NormalizedBatch(BaseModel):
    client_id: str
    source: str
    ingested_at: datetime = Field(default_factory=datetime.utcnow)
    conversations: list[NormalizedConversation] = Field(default_factory=list)
    raw_metadata: dict = Field(default_factory=dict)
