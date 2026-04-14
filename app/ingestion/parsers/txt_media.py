"""
Media message detection for WhatsApp .txt exports.
"""
import re

from app.models.enums import MessageType

_MEDIA_PATTERNS: list[tuple[re.Pattern, MessageType]] = [
    # Images
    (re.compile(r"imagen omitida", re.IGNORECASE), MessageType.IMAGE),
    (re.compile(r"image omitted", re.IGNORECASE), MessageType.IMAGE),
    (re.compile(r"<Media omitted>", re.IGNORECASE), MessageType.IMAGE),
    (re.compile(r"\.(jpg|jpeg|png|gif|webp)\s*\(file attached\)", re.IGNORECASE), MessageType.IMAGE),
    # Videos
    (re.compile(r"video omitido", re.IGNORECASE), MessageType.VIDEO),
    (re.compile(r"video omitted", re.IGNORECASE), MessageType.VIDEO),
    (re.compile(r"\.(mp4|mov|avi|mkv)\s*\(file attached\)", re.IGNORECASE), MessageType.VIDEO),
    # Audio
    (re.compile(r"audio omitido", re.IGNORECASE), MessageType.AUDIO),
    (re.compile(r"audio omitted", re.IGNORECASE), MessageType.AUDIO),
    (re.compile(r"\.(opus|mp3|ogg|wav|m4a)\s*\(file attached\)", re.IGNORECASE), MessageType.AUDIO),
    # Documents
    (re.compile(r"documento omitido", re.IGNORECASE), MessageType.DOCUMENT),
    (re.compile(r"document omitted", re.IGNORECASE), MessageType.DOCUMENT),
    (re.compile(r"archivo omitido", re.IGNORECASE), MessageType.DOCUMENT),
    (re.compile(r"\.(pdf|docx?|xlsx?|pptx?|txt|zip|rar)\s*\(file attached\)", re.IGNORECASE), MessageType.DOCUMENT),
    # Stickers
    (re.compile(r"sticker omitido", re.IGNORECASE), MessageType.STICKER),
    (re.compile(r"sticker omitted", re.IGNORECASE), MessageType.STICKER),
    # Location
    (re.compile(r"^ubicación:\s*https?://", re.IGNORECASE), MessageType.LOCATION),
    (re.compile(r"^location:\s*https?://", re.IGNORECASE), MessageType.LOCATION),
    # Contact card
    (re.compile(r"tarjeta de contacto omitida", re.IGNORECASE), MessageType.CONTACT),
    (re.compile(r"contact card omitted", re.IGNORECASE), MessageType.CONTACT),
]


def detect_media_type(text: str) -> MessageType | None:
    """
    Return the MessageType if the text looks like a media indicator, else None.
    """
    for pattern, media_type in _MEDIA_PATTERNS:
        if pattern.search(text):
            return media_type
    return None


def process_media_content(text: str) -> tuple[MessageType, str | None]:
    """
    Given message text, determine type and whether to keep text content.

    Returns (MessageType, text_content_or_None).
    For pure media indicators (no caption), text_content is None.
    For messages with both text and media (captions), text_content is preserved.
    """
    media_type = detect_media_type(text)
    if media_type is None:
        return MessageType.TEXT, text

    # Check if there's additional caption text beyond the media indicator
    # by stripping the media indicator and seeing if anything meaningful remains
    cleaned = text.strip()
    for pattern, _ in _MEDIA_PATTERNS:
        cleaned = pattern.sub("", cleaned).strip()

    text_content = cleaned if cleaned else None
    return media_type, text_content
