"""
WhatsApp .txt export parser — orchestrates all components.
"""
from collections import Counter

from app.ingestion.parsers.base import BaseParser
from app.ingestion.parsers.txt_assembler import assemble_messages
from app.ingestion.parsers.txt_classifier import LineType, classify_lines
from app.ingestion.parsers.txt_direction import auto_detect_business, detect_direction
from app.ingestion.parsers.txt_media import process_media_content
from app.models.enums import MessageDirection, MessageType
from app.models.normalized import NormalizedBatch, NormalizedConversation, NormalizedMessage
from app.models.schemas import ParseQualityReport

_ENCODINGS = ["utf-8", "latin-1"]


def _decode(data: bytes) -> str:
    for enc in _ENCODINGS:
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, ValueError):
            continue
    raise ValueError("File could not be decoded as UTF-8 or Latin-1.")


class TxtParser(BaseParser):
    async def parse(self, data: bytes | dict, **kwargs) -> NormalizedBatch:
        """
        Parse a single WhatsApp .txt export file.

        kwargs:
            client_id (str): required
            business_identifiers (list[str]): names/phones the business uses
            filename (str): original filename for metadata
        """
        client_id = kwargs.get("client_id", "")
        business_identifiers = kwargs.get("business_identifiers", [])
        filename = kwargs.get("filename", "unknown.txt")

        text = _decode(data)
        lines = text.splitlines()

        # Pass 1: classify all lines
        classified = classify_lines(lines)

        # Collect stats for quality report
        total_lines = len(classified)
        empty_count = sum(1 for c in classified if c.line_type == LineType.EMPTY)
        system_count = sum(1 for c in classified if c.line_type == LineType.SYSTEM_MESSAGE)
        unparseable = [c.original for c in classified if c.line_type == LineType.CONTINUATION and not any(
            prev.line_type == LineType.MESSAGE_START
            for prev in classified[: classified.index(c)]
            if prev.line_type != LineType.EMPTY
        )]

        # Pass 2: assemble messages
        raw_messages, continuation_count = assemble_messages(classified)

        if not raw_messages:
            return NormalizedBatch(
                client_id=client_id,
                source="txt_upload",
                conversations=[],
                raw_metadata={"filename": filename},
            )

        # Collect all senders
        all_senders = [m.sender for m in raw_messages]
        unique_senders = list(dict.fromkeys(all_senders))  # preserve order, deduplicate

        # Determine business sender
        if business_identifiers:
            business_sender = next(
                (s for s in unique_senders if detect_direction(s, business_identifiers) == "outbound"),
                None,
            )
            auto_detected = False
        else:
            business_sender, auto_detected = auto_detect_business(all_senders)

        # Build normalized messages
        normalized: list[NormalizedMessage] = []
        type_counts: Counter = Counter()
        direction_counts: Counter = Counter()

        for raw in raw_messages:
            if business_identifiers:
                direction_str = detect_direction(raw.sender, business_identifiers)
            else:
                direction_str = "outbound" if raw.sender == business_sender else "inbound"

            msg_direction = MessageDirection(direction_str)
            msg_type, text_content = process_media_content(raw.content)

            normalized.append(
                NormalizedMessage(
                    timestamp=raw.timestamp,
                    direction=msg_direction,
                    sender_name=raw.sender,
                    message_type=msg_type,
                    text_content=text_content,
                    metadata={"filename": filename},
                )
            )
            type_counts[msg_type.value] += 1
            direction_counts[direction_str] += 1

        # Determine contact info (non-business sender)
        customers = [s for s in unique_senders if s != business_sender]
        contact_name = customers[0] if customers else (unique_senders[0] if unique_senders else "unknown")
        contact_phone = contact_name  # .txt files don't have reliable phone numbers

        conversation = NormalizedConversation(
            contact_phone=contact_phone,
            contact_name=contact_name,
            messages=normalized,
            source="txt_upload",
        )

        # Build quality report
        unparseable_lines = sum(
            1 for c in classified
            if c.line_type == LineType.CONTINUATION and c == classified[0]
        )
        actual_unparseable = [
            c.original for c in classified[:5]
            if c.line_type == LineType.CONTINUATION
            and classified.index(c) == 0
        ]

        quality = _build_quality_report(
            total_lines=total_lines,
            parsed_messages=len(raw_messages),
            system_filtered=system_count,
            continuation_merged=continuation_count,
            empty_skipped=empty_count,
            unique_senders=unique_senders,
            business_sender=business_sender,
            customers=customers,
            messages=normalized,
            type_counts=dict(type_counts),
            direction_counts=dict(direction_counts),
            auto_detected=auto_detected,
        )

        batch = NormalizedBatch(
            client_id=client_id,
            source="txt_upload",
            conversations=[conversation],
            raw_metadata={"filename": filename, "quality_report": quality.model_dump()},
        )
        return batch


def _build_quality_report(
    *,
    total_lines: int,
    parsed_messages: int,
    system_filtered: int,
    continuation_merged: int,
    empty_skipped: int,
    unique_senders: list[str],
    business_sender: str | None,
    customers: list[str],
    messages: list[NormalizedMessage],
    type_counts: dict,
    direction_counts: dict,
    auto_detected: bool,
) -> ParseQualityReport:
    warnings: list[str] = []
    confidence = 1.0

    if auto_detected:
        warnings.append("Business auto-detected (no identifiers provided)")
        confidence -= 0.1

    if total_lines > 0:
        unparseable_ratio = (total_lines - parsed_messages - system_filtered - empty_skipped - continuation_merged) / total_lines
        if unparseable_ratio > 0.05:
            warnings.append(f"High ratio of unparseable lines ({unparseable_ratio:.0%})")
            confidence -= 0.1

    if len(unique_senders) < 2:
        warnings.append("Only one sender found (expected two)")
        confidence -= 0.15

    if direction_counts.get("outbound", 0) == 0:
        warnings.append("No outbound messages detected")
        confidence -= 0.2

    ts_sorted = sorted([m.timestamp for m in messages])
    date_start = ts_sorted[0] if ts_sorted else None
    date_end = ts_sorted[-1] if ts_sorted else None

    return ParseQualityReport(
        total_lines=total_lines,
        parsed_messages=parsed_messages,
        system_messages_filtered=system_filtered,
        continuation_lines_merged=continuation_merged,
        empty_lines_skipped=empty_skipped,
        unique_senders=unique_senders,
        detected_business=business_sender,
        detected_customers=customers,
        date_range_start=date_start,
        date_range_end=date_end,
        message_type_counts=type_counts,
        direction_counts=direction_counts,
        confidence_score=max(0.0, confidence),
        warnings=warnings,
    )
