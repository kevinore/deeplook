"""
Pass 2 of the WhatsApp .txt parser: assemble classified lines into messages.
"""
from dataclasses import dataclass, field
from datetime import datetime

from app.ingestion.parsers.txt_classifier import ClassifiedLine, LineType


@dataclass
class RawMessage:
    timestamp: datetime
    sender: str
    content: str
    continuation_count: int = 0


def assemble_messages(classified_lines: list[ClassifiedLine]) -> tuple[list[RawMessage], int]:
    """
    Assemble classified lines into complete messages.

    Returns:
        (list_of_raw_messages, continuation_lines_merged_count)

    Rules:
    - MESSAGE_START: save previous message, start new one
    - CONTINUATION: append to current message with newline
    - SYSTEM_MESSAGE: save current message, discard system
    - EMPTY: ignore (do not break current message)
    """
    messages: list[RawMessage] = []
    current: RawMessage | None = None
    continuation_count = 0

    for cl in classified_lines:
        if cl.line_type == LineType.EMPTY:
            continue

        elif cl.line_type == LineType.SYSTEM_MESSAGE:
            if current is not None:
                messages.append(current)
                current = None

        elif cl.line_type == LineType.MESSAGE_START:
            if current is not None:
                messages.append(current)
            current = RawMessage(
                timestamp=cl.timestamp,
                sender=cl.sender or "",
                content=cl.content or "",
            )

        elif cl.line_type == LineType.CONTINUATION:
            if current is not None:
                current.content = current.content + "\n" + (cl.content or cl.original)
                current.continuation_count += 1
                continuation_count += 1
            # If no current message yet, this is an orphan line — skip

    if current is not None:
        messages.append(current)

    return messages, continuation_count
