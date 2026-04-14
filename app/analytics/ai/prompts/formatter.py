"""
Format a NormalizedConversation into AI-readable text.
"""
from app.models.enums import MessageDirection, MessageType
from app.models.normalized import NormalizedConversation, NormalizedMessage

_MAX_MESSAGES = 100

_MEDIA_LABELS = {
    MessageType.IMAGE: "[Image]",
    MessageType.VIDEO: "[Video]",
    MessageType.AUDIO: "[Audio]",
    MessageType.DOCUMENT: "[Document]",
    MessageType.LOCATION: "[Location]",
    MessageType.CONTACT: "[Contact]",
    MessageType.STICKER: "[Sticker]",
    MessageType.UNKNOWN: "[Media]",
}


def _format_message(msg: NormalizedMessage) -> str:
    ts = msg.timestamp.strftime("%Y-%m-%d %H:%M")
    if msg.direction == MessageDirection.OUTBOUND:
        role = "BUSINESS"
    elif msg.direction == MessageDirection.INBOUND:
        role = "CUSTOMER"
    else:
        return ""  # skip system messages

    if msg.message_type == MessageType.TEXT:
        content = msg.text_content or ""
    else:
        media_label = _MEDIA_LABELS.get(msg.message_type, "[Media]")
        content = f"{media_label}" + (f" {msg.text_content}" if msg.text_content else "")

    return f"[{ts}] {role}: {content}"


def format_conversation(conv: NormalizedConversation) -> str:
    """Format a NormalizedConversation into a readable transcript for the AI."""
    messages = [m for m in conv.messages if m.direction != MessageDirection.SYSTEM]
    total = len(messages)

    if total > _MAX_MESSAGES:
        messages = messages[-_MAX_MESSAGES:]
        header = f"[Conversation truncated — showing last {_MAX_MESSAGES} of {total} messages]\n\n"
    else:
        header = ""

    lines = [_format_message(m) for m in messages]
    body = "\n".join(line for line in lines if line)
    return header + body
