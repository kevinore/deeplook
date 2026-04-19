import uuid

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


def _uuid():
    return str(uuid.uuid4())


class Client(Base):
    __tablename__ = "clients"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    phone = Column(String(50), nullable=True)
    business_name = Column(String(255), nullable=False)
    business_type = Column(String(100), nullable=True)
    business_identifiers = Column(JSONB, default=list, nullable=False)
    plan = Column(String(50), default="free", nullable=False)
    average_transaction_value = Column(Float, nullable=True)
    waba_id = Column(String(100), nullable=True)
    phone_number_id = Column(String(100), nullable=True)
    onboarded_via = Column(String(50), default="file_upload", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    contacts = relationship("Contact", back_populates="client", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="client", cascade="all, delete-orphan")
    analysis_jobs = relationship("AnalysisJob", back_populates="client", cascade="all, delete-orphan")
    daily_metrics = relationship("DailyMetrics", back_populates="client", cascade="all, delete-orphan")


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    client_id = Column(UUID(as_uuid=False), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    phone = Column(String(50), nullable=False)
    name = Column(String(255), nullable=True)
    first_seen_at = Column(DateTime(timezone=True), nullable=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    total_conversations = Column(Integer, default=0, nullable=False)
    tags = Column(JSONB, default=list, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    client = relationship("Client", back_populates="contacts")
    conversations = relationship("Conversation", back_populates="contact")

    __table_args__ = (
        UniqueConstraint("client_id", "phone", name="uq_contacts_client_phone"),
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    client_id = Column(UUID(as_uuid=False), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    contact_id = Column(UUID(as_uuid=False), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False)
    last_message_at = Column(DateTime(timezone=True), nullable=True)
    message_count = Column(Integer, default=0, nullable=False)
    inbound_count = Column(Integer, default=0, nullable=False)
    outbound_count = Column(Integer, default=0, nullable=False)
    status = Column(String(50), default="active", nullable=False)
    source = Column(String(50), nullable=False)
    source_filename = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    client = relationship("Client", back_populates="conversations")
    contact = relationship("Contact", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    analyses = relationship("ConversationAnalysis", back_populates="conversation", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_conversations_client_id", "client_id"),
        Index("ix_conversations_client_started", "client_id", "started_at"),
        Index("ix_conversations_client_source", "client_id", "source"),
    )


class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    conversation_id = Column(UUID(as_uuid=False), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    source_id = Column(String(255), nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    direction = Column(String(20), nullable=False)
    sender_phone = Column(String(50), nullable=True)
    sender_name = Column(String(255), nullable=True)
    message_type = Column(String(50), default="text", nullable=False)
    text_content = Column(Text, nullable=True)
    media_url = Column(Text, nullable=True)
    extra_data = Column(JSONB, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    conversation = relationship("Conversation", back_populates="messages")

    __table_args__ = (
        Index("ix_messages_conversation_id", "conversation_id"),
        Index("ix_messages_conversation_timestamp", "conversation_id", "timestamp"),
        # Partial unique index: only enforce uniqueness when source_id is not NULL
        Index(
            "uq_messages_conversation_source",
            "conversation_id",
            "source_id",
            unique=True,
            postgresql_where=text("source_id IS NOT NULL"),
        ),
    )


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    client_id = Column(UUID(as_uuid=False), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(50), default="pending", nullable=False)
    job_type = Column(String(50), nullable=False)
    total_conversations = Column(Integer, default=0, nullable=False)
    processed_conversations = Column(Integer, default=0, nullable=False)
    ai_provider = Column(String(50), nullable=True)
    ai_model = Column(String(100), nullable=True)
    total_tokens_input = Column(Integer, default=0, nullable=False)
    total_tokens_output = Column(Integer, default=0, nullable=False)
    total_tokens_used = Column(Integer, default=0, nullable=False)
    total_cost_usd = Column(Float, default=0.0, nullable=False)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    client = relationship("Client", back_populates="analysis_jobs")
    analyses = relationship("ConversationAnalysis", back_populates="job")


class ConversationAnalysis(Base):
    __tablename__ = "conversation_analysis"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    conversation_id = Column(UUID(as_uuid=False), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    analysis_job_id = Column(UUID(as_uuid=False), ForeignKey("analysis_jobs.id", ondelete="SET NULL"), nullable=True)
    sentiment = Column(String(20), nullable=True)
    sentiment_score = Column(Float, nullable=True)
    sentiment_reason = Column(Text, nullable=True)
    primary_topic = Column(String(100), nullable=True)
    secondary_topics = Column(JSONB, default=list, nullable=False)
    quality_score = Column(Float, nullable=True)
    quality_breakdown = Column(JSONB, default=dict, nullable=False)
    conversion_status = Column(String(50), nullable=True)
    conversion_reason = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    key_points = Column(JSONB, default=list, nullable=False)
    customer_questions = Column(JSONB, default=list, nullable=False)
    ai_provider = Column(String(50), nullable=True)
    ai_model = Column(String(100), nullable=True)
    tokens_input = Column(Integer, default=0, nullable=False)
    tokens_output = Column(Integer, default=0, nullable=False)
    tokens_used = Column(Integer, default=0, nullable=False)
    analysis_cost_usd = Column(Float, default=0.0, nullable=False)
    analyzed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # Computed metrics persisted from the analytics engine
    first_response_time_seconds = Column(Float, nullable=True)
    avg_response_time_seconds = Column(Float, nullable=True)
    median_response_time_seconds = Column(Float, nullable=True)
    p95_response_time_seconds = Column(Float, nullable=True)
    unanswered_count = Column(Integer, default=0, nullable=False)
    total_messages = Column(Integer, default=0, nullable=False)
    inbound_count = Column(Integer, default=0, nullable=False)
    outbound_count = Column(Integer, default=0, nullable=False)
    duration_minutes = Column(Float, nullable=True)
    response_time_by_hour = Column(JSONB, nullable=True)

    conversation = relationship("Conversation", back_populates="analyses")
    job = relationship("AnalysisJob", back_populates="analyses")

    __table_args__ = (
        UniqueConstraint("conversation_id", "analysis_job_id", name="uq_analysis_conversation_job"),
    )


class DailyMetrics(Base):
    __tablename__ = "daily_metrics"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    client_id = Column(UUID(as_uuid=False), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False)
    total_conversations = Column(Integer, default=0, nullable=False)
    total_messages = Column(Integer, default=0, nullable=False)
    inbound_messages = Column(Integer, default=0, nullable=False)
    outbound_messages = Column(Integer, default=0, nullable=False)
    unique_contacts = Column(Integer, default=0, nullable=False)
    avg_response_time_seconds = Column(Float, nullable=True)
    median_response_time_seconds = Column(Float, nullable=True)
    p95_response_time_seconds = Column(Float, nullable=True)
    unanswered_count = Column(Integer, default=0, nullable=False)
    positive_count = Column(Integer, default=0, nullable=False)
    neutral_count = Column(Integer, default=0, nullable=False)
    negative_count = Column(Integer, default=0, nullable=False)
    converted_count = Column(Integer, default=0, nullable=False)
    lost_count = Column(Integer, default=0, nullable=False)
    top_topics = Column(JSONB, default=list, nullable=False)
    health_score = Column(Float, nullable=True)
    computed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    client = relationship("Client", back_populates="daily_metrics")

    __table_args__ = (
        UniqueConstraint("client_id", "date", name="uq_daily_metrics_client_date"),
    )
