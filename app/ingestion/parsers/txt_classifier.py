"""
Pass 1 of the WhatsApp .txt parser: classify each line.
"""
import re
from dataclasses import dataclass
from enum import Enum

from app.ingestion.parsers.txt_timestamp import extract_timestamp, has_timestamp
from app.ingestion.parsers.txt_system import is_system_message

# Matches "Sender Name: " or "+57 311 2345678: "
_SENDER_COLON = re.compile(r"^(.+?):\s(.*)$", re.DOTALL)


class LineType(str, Enum):
    MESSAGE_START = "message_start"
    SYSTEM_MESSAGE = "system_message"
    CONTINUATION = "continuation"
    EMPTY = "empty"


@dataclass
class ClassifiedLine:
    line_type: LineType
    original: str
    timestamp: object = None   # datetime | None
    sender: str | None = None
    content: str | None = None


def classify_line(line: str) -> ClassifiedLine:
    """Classify a single line from a WhatsApp .txt export."""
    stripped = line.rstrip("\n").rstrip("\r")

    if not stripped.strip():
        return ClassifiedLine(line_type=LineType.EMPTY, original=stripped)

    if not has_timestamp(stripped):
        return ClassifiedLine(line_type=LineType.CONTINUATION, original=stripped, content=stripped)

    ts, remainder = extract_timestamp(stripped)

    if ts is None:
        # Has a timestamp-like prefix but couldn't parse — treat as continuation
        return ClassifiedLine(line_type=LineType.CONTINUATION, original=stripped, content=stripped)

    # Check for system message (no sender colon pattern, or known system text)
    sender_match = _SENDER_COLON.match(remainder)

    if sender_match is None:
        # No "Sender: content" pattern → system message
        return ClassifiedLine(
            line_type=LineType.SYSTEM_MESSAGE,
            original=stripped,
            timestamp=ts,
            content=remainder.strip(),
        )

    sender = sender_match.group(1).strip()
    content = sender_match.group(2)

    # Also check if the content (after the sender) is a known system phrase
    if is_system_message(content):
        return ClassifiedLine(
            line_type=LineType.SYSTEM_MESSAGE,
            original=stripped,
            timestamp=ts,
            content=content,
        )

    return ClassifiedLine(
        line_type=LineType.MESSAGE_START,
        original=stripped,
        timestamp=ts,
        sender=sender,
        content=content,
    )


def classify_lines(lines: list[str]) -> list[ClassifiedLine]:
    """Classify all lines from a WhatsApp export file."""
    return [classify_line(line) for line in lines]
