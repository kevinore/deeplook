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
    clerk_user_id = Column(String(255), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    phone = Column(String(50), nullable=True)
    business_name = Column(String(255), nullable=False)
    business_type = Column(String(100), nullable=True)
    business_identifiers = Column(JSONB, default=list, nullable=False)
    plan = Column(String(50), default="free", nullable=False)
    plan_started_at = Column(DateTime(timezone=True), nullable=True)
    plan_expires_at = Column(DateTime(timezone=True), nullable=True)
    subscription_status = Column(String(30), default="inactive", nullable=False)
    last_renewal_email_sent_at = Column(DateTime(timezone=True), nullable=True)
    last_renewal_email_stage = Column(String(10), nullable=True)
    average_transaction_value = Column(Float, nullable=True)
    waba_id = Column(String(100), nullable=True)
    phone_number_id = Column(String(100), nullable=True)
    onboarded_via = Column(String(50), default="file_upload", nullable=False)
    # Habeas Data (Ley 1581/2012): timestamp at which the user explicitly accepted
    # the Privacy Policy and Terms of Service. Captured at onboarding.
    policies_accepted_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    contacts = relationship("Contact", back_populates="client", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="client", cascade="all, delete-orphan")
    analysis_jobs = relationship("AnalysisJob", back_populates="client", cascade="all, delete-orphan")
    daily_metrics = relationship("DailyMetrics", back_populates="client", cascade="all, delete-orphan")
    whatsapp_connection = relationship("WhatsAppConnection", back_populates="client", uselist=False, cascade="all, delete-orphan")
    payment_sessions = relationship("PaymentSession", back_populates="client", cascade="all, delete-orphan")


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
    analyses = relationship("ConversationAnalysis", back_populates="conversation", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_conversations_client_id", "client_id"),
        Index("ix_conversations_client_started", "client_id", "started_at"),
        Index("ix_conversations_client_source", "client_id", "source"),
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
    # `unanswered_count` is now boolean-per-conversation (0|1).
    unanswered_count = Column(Integer, default=0, nullable=False)
    trailing_inbound_messages = Column(Integer, default=0, nullable=False)
    total_messages = Column(Integer, default=0, nullable=False)
    inbound_count = Column(Integer, default=0, nullable=False)
    outbound_count = Column(Integer, default=0, nullable=False)
    duration_minutes = Column(Float, nullable=True)
    response_time_by_hour = Column(JSONB, nullable=True)
    # Deterministic ack-derived metrics (WAHA-only; null for .txt uploads)
    delivery_rate = Column(Float, nullable=True)
    read_rate = Column(Float, nullable=True)
    is_ghosted = Column(Boolean, default=False, nullable=False)
    last_business_msg_ack = Column(Integer, nullable=True)
    # Operational coverage (% of in-hours inbound answered within 1h)
    operational_coverage_score = Column(Float, nullable=True)
    out_of_hours_inbound_pct = Column(Float, nullable=True)
    # WAHA chat metadata (cross-validation)
    wa_unread_count = Column(Integer, nullable=True)
    wa_is_muted = Column(Boolean, default=False, nullable=False)
    wa_is_archived = Column(Boolean, default=False, nullable=False)

    conversation = relationship("Conversation", back_populates="analyses")
    job = relationship("AnalysisJob", back_populates="analyses")

    __table_args__ = (
        UniqueConstraint("conversation_id", "analysis_job_id", name="uq_analysis_conversation_job"),
    )


class WhatsAppConnection(Base):
    __tablename__ = "whatsapp_connections"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    client_id = Column(UUID(as_uuid=False), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, unique=True)
    waha_session_name = Column(String(64), nullable=False, unique=True)
    status = Column(String(30), default="STOPPED", nullable=False)
    phone_number = Column(String(50), nullable=True)
    push_name = Column(String(255), nullable=True)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_sync_job_id = Column(UUID(as_uuid=False), ForeignKey("analysis_jobs.id", ondelete="SET NULL"), nullable=True)
    sync_frequency = Column(String(20), default="monthly", nullable=False)
    next_scheduled_sync_at = Column(DateTime(timezone=True), nullable=True)
    # Last time we successfully touched the WAHA session (sync OR keepalive).
    # Drives the keepalive job — bumped to "now" whenever we wake the session
    # to prevent WhatsApp's 14-day idle device-unlink rule.
    last_session_active_at = Column(DateTime(timezone=True), nullable=True)
    # True = WhatsApp Business, False = personal, None = not yet checked.
    is_business_account = Column(Boolean, nullable=True)
    last_reconnect_email_sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    client = relationship("Client", back_populates="whatsapp_connection")
    last_sync_job = relationship("AnalysisJob")

    __table_args__ = (
        Index("ix_whatsapp_connections_next_sync", "next_scheduled_sync_at", "status"),
        Index("ix_whatsapp_connections_keepalive", "last_session_active_at", "status"),
    )


class PaymentSession(Base):
    __tablename__ = "payment_sessions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    client_id = Column(UUID(as_uuid=False), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    plan = Column(String(50), nullable=False)
    amount_in_cents = Column(Integer, nullable=False)
    reference = Column(String(200), unique=True, nullable=False)
    # pending → approved | declined | voided | error
    status = Column(String(30), default="pending", nullable=False)
    wompi_transaction_id = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    client = relationship("Client", back_populates="payment_sessions")

    __table_args__ = (
        Index("ix_payment_sessions_reference", "reference"),
        Index("ix_payment_sessions_client_id", "client_id"),
    )


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    client_id = Column(UUID(as_uuid=False), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    type = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False, nullable=False)
    job_id = Column(UUID(as_uuid=False), ForeignKey("analysis_jobs.id", ondelete="SET NULL"), nullable=True)
    extra_data = Column(JSONB, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    client = relationship("Client")
    job = relationship("AnalysisJob")

    __table_args__ = (
        Index("ix_notifications_client_created", "client_id", "created_at"),
        Index("ix_notifications_client_unread", "client_id", "is_read"),
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
