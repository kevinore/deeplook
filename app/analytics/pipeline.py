"""
Full pipeline: ingest → store → analyze → deliver.
Used by the background worker.
"""
import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.engine import AnalyticsEngine
from app.analytics.ai.provider import AIProvider
from app.models.database import AnalysisJob, ConversationAnalysis, Conversation
from app.models.normalized import NormalizedBatch, NormalizedConversation
from app.models.schemas import ConversationAnalysisResult
from app.repositories.analysis_repo import AnalysisJobRepository, ConversationAnalysisRepository
from app.repositories.conversation_repo import (
    ContactRepository,
    ConversationRepository,
    MessageRepository,
)

logger = logging.getLogger(__name__)


async def store_batch(
    batch: NormalizedBatch,
    session: AsyncSession,
) -> list[tuple[NormalizedConversation, str]]:
    """
    Persist a NormalizedBatch to the database.
    Returns list of (NormalizedConversation, conversation_db_id) pairs.
    """
    contact_repo = ContactRepository(session)
    conv_repo = ConversationRepository(session)
    msg_repo = MessageRepository(session)

    pairs: list[tuple[NormalizedConversation, str]] = []

    for norm_conv in batch.conversations:
        # Get or create contact
        contact = await contact_repo.get_or_create(
            client_id=batch.client_id,
            phone=norm_conv.contact_phone,
            name=norm_conv.contact_name,
        )

        # Determine timestamps
        timestamps = [m.timestamp for m in norm_conv.messages]
        started_at = min(timestamps) if timestamps else datetime.utcnow()
        last_message_at = max(timestamps) if timestamps else None

        inbound = sum(1 for m in norm_conv.messages if m.direction.value == "inbound")
        outbound = sum(1 for m in norm_conv.messages if m.direction.value == "outbound")

        # Create conversation
        filename = batch.raw_metadata.get("filename")
        db_conv = await conv_repo.create(
            client_id=batch.client_id,
            contact_id=contact.id,
            started_at=started_at,
            last_message_at=last_message_at,
            message_count=len(norm_conv.messages),
            inbound_count=inbound,
            outbound_count=outbound,
            source=norm_conv.source,
            source_filename=filename,
        )

        # Bulk create messages
        msg_dicts = [
            {
                "conversation_id": db_conv.id,
                "source_id": m.source_id,
                "timestamp": m.timestamp,
                "direction": m.direction.value,
                "sender_phone": m.sender_phone,
                "sender_name": m.sender_name,
                "message_type": m.message_type.value,
                "text_content": m.text_content,
                "media_url": m.media_url,
                "extra_data": m.metadata,
            }
            for m in norm_conv.messages
        ]
        if msg_dicts:
            await msg_repo.bulk_create(msg_dicts)

        pairs.append((norm_conv, db_conv.id))

    await session.commit()
    return pairs
