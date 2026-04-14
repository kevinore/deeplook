"""
Meta Cloud API webhook parser (Phase 2).
Stub implementation for MVP — not used in Phase 1.
"""
import logging
from datetime import datetime

from app.ingestion.parsers.base import BaseParser
from app.models.enums import MessageDirection, MessageType
from app.models.normalized import NormalizedBatch, NormalizedConversation, NormalizedMessage

logger = logging.getLogger(__name__)


class MetaWebhookParser(BaseParser):
    async def parse(self, data: bytes | dict, **kwargs) -> NormalizedBatch:
        client_id = kwargs.get("client_id", "")
        payload = data if isinstance(data, dict) else {}

        conversations: list[NormalizedConversation] = []

        try:
            entry = payload.get("entry", [])
            for e in entry:
                for change in e.get("changes", []):
                    value = change.get("value", {})
                    webhook_type = change.get("field", "")

                    if webhook_type == "messages":
                        conv = self._parse_message_webhook(value)
                        if conv:
                            conversations.append(conv)
                    elif webhook_type == "history":
                        conversations.extend(self._parse_history_webhook(value))

        except Exception as exc:
            logger.error("MetaWebhookParser error: %s | payload: %s", exc, payload)

        return NormalizedBatch(
            client_id=client_id,
            source="meta_api",
            conversations=conversations,
        )

    def _parse_message_webhook(self, value: dict) -> NormalizedConversation | None:
        messages = value.get("messages", [])
        if not messages:
            return None

        contact_info = (value.get("contacts") or [{}])[0]
        contact_phone = contact_info.get("wa_id", "unknown")
        contact_name = (contact_info.get("profile") or {}).get("name")

        normalized = []
        for msg in messages:
            normalized.append(self._map_message(msg, MessageDirection.INBOUND))

        # smb_message_echoes (outbound from business)
        for msg in value.get("statuses", []):
            pass  # statuses are delivery receipts, not messages

        return NormalizedConversation(
            contact_phone=contact_phone,
            contact_name=contact_name,
            messages=normalized,
            source="meta_api",
        )

    def _parse_history_webhook(self, value: dict) -> list[NormalizedConversation]:
        conversations = []
        for thread in value.get("threads", []):
            contact_phone = thread.get("contact_wa_id", "unknown")
            msgs = []
            for msg in thread.get("messages", []):
                direction = (
                    MessageDirection.OUTBOUND
                    if msg.get("from_me")
                    else MessageDirection.INBOUND
                )
                msgs.append(self._map_message(msg, direction))
            if msgs:
                conversations.append(
                    NormalizedConversation(
                        contact_phone=contact_phone,
                        messages=msgs,
                        source="meta_history",
                    )
                )
        return conversations

    @staticmethod
    def _map_message(msg: dict, direction: MessageDirection) -> NormalizedMessage:
        ts = msg.get("timestamp")
        if isinstance(ts, (int, float)):
            timestamp = datetime.utcfromtimestamp(ts)
        else:
            timestamp = datetime.utcnow()

        msg_type_str = msg.get("type", "text")
        try:
            msg_type = MessageType(msg_type_str)
        except ValueError:
            msg_type = MessageType.UNKNOWN

        text_content = None
        if msg_type == MessageType.TEXT:
            text_content = (msg.get("text") or {}).get("body")

        return NormalizedMessage(
            source_id=msg.get("id"),
            timestamp=timestamp,
            direction=direction,
            sender_phone=msg.get("from"),
            message_type=msg_type,
            text_content=text_content,
            metadata={"raw": msg},
        )
