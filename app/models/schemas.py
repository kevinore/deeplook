from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import AnalysisStatus, ConversionStatus, MessageDirection, MessageType, Sentiment


# --- Parse Quality Report ---

class ParseQualityReport(BaseModel):
    total_lines: int = 0
    parsed_messages: int = 0
    system_messages_filtered: int = 0
    continuation_lines_merged: int = 0
    empty_lines_skipped: int = 0
    unparseable_lines: int = 0
    unparseable_samples: list[str] = Field(default_factory=list)
    unique_senders: list[str] = Field(default_factory=list)
    detected_business: str | None = None
    detected_customers: list[str] = Field(default_factory=list)
    date_range_start: datetime | None = None
    date_range_end: datetime | None = None
    message_type_counts: dict[str, int] = Field(default_factory=dict)
    direction_counts: dict[str, int] = Field(default_factory=dict)
    confidence_score: float = 1.0
    warnings: list[str] = Field(default_factory=list)


# --- Upload ---

class UploadResponse(BaseModel):
    job_id: UUID
    files_received: int
    conversations_parsed: int
    parse_errors: list[dict] = Field(default_factory=list)
    parse_quality: ParseQualityReport
    status: str = "processing"


# --- Job Status ---

class JobStatusResponse(BaseModel):
    job_id: UUID
    status: AnalysisStatus
    total_conversations: int
    processed_conversations: int
    progress_percent: float
    error_message: str | None = None
    report_url: str | None = None
    created_at: datetime | None = None
    total_tokens_used: int = 0
    total_cost_usd: float = 0.0
    ai_provider: str | None = None
    ai_model: str | None = None
    connection_id: str | None = None
    connection_name: str | None = None


# --- Analysis Results ---

class QualityBreakdown(BaseModel):
    """
    Quality dimensions evaluated by the AI on a 0–10 scale.

    `speed_perception` is DEPRECATED but retained for backward compatibility with
    existing DB rows. The current prompt no longer asks the AI for it; instead,
    the deterministic `first_response_time_seconds` is the single source of truth
    for response speed (Health Score's "Response Speed" component).

    `quality_score` (the aggregate the rest of the system uses) is the average of
    helpfulness/tone/completeness only — see `response_parser.parse_ai_response`.
    """
    helpfulness: float = 5.0
    tone: float = 5.0
    completeness: float = 5.0
    speed_perception: float = 5.0  # DEPRECATED — kept for schema/DB compat; not averaged anymore


class ConversationAnalysisResult(BaseModel):
    conversation_id: str
    # Identity fields (in-memory only — populated by the delivery layer when
    # loading rows for the PDF; not persisted on this model). Used to:
    #   • Deduplicate sessions of the same chat for the "Sin Responder" KPI
    #   • Render readable references on the conversation cards in the PDF
    contact_phone: str | None = None
    contact_name: str | None = None
    started_at: datetime | None = None
    sentiment: Sentiment | None = None
    sentiment_score: float | None = None
    sentiment_reason: str | None = None
    primary_topic: str | None = None
    secondary_topics: list[str] = Field(default_factory=list)
    quality_score: float | None = None
    quality_breakdown: QualityBreakdown = Field(default_factory=QualityBreakdown)
    conversion_status: ConversionStatus | None = None
    conversion_reason: str | None = None
    summary: str | None = None
    key_points: list[str] = Field(default_factory=list)
    customer_questions: list[str] = Field(default_factory=list)
    # Metrics — response time / volume
    first_response_time_seconds: float | None = None
    avg_response_time_seconds: float | None = None
    median_response_time_seconds: float | None = None
    p95_response_time_seconds: float | None = None
    avg_response_time_bh_seconds: float | None = None  # business-hours-adjusted avg RT
    # `unanswered_count` is now boolean-per-conversation (0|1) — sum across results
    # equals the number of conversations awaiting a business reply.
    unanswered_count: int = 0
    # Diagnostic: how many trailing INBOUND messages pile up on an unanswered chat.
    # Useful to spot "screaming" customers (multiple unanswered messages in a row).
    trailing_inbound_messages: int = 0
    total_messages: int = 0
    inbound_count: int = 0
    outbound_count: int = 0
    duration_minutes: float | None = None
    response_time_by_hour: dict[str, float] | None = None
    # Deterministic ack-based metrics (WAHA only — None for .txt uploads)
    delivery_rate: float | None = None        # % of outbound messages delivered to WhatsApp servers
    read_rate: float | None = None            # % of outbound messages read by the customer
    is_ghosted: bool = False                  # last business msg READ but no reply within 24h
    last_business_msg_ack: int | None = None  # WAHA ack of most recent outbound (-1..4)
    # Operational coverage — % of in-hours customer messages answered within 1h
    operational_coverage_score: float | None = None
    out_of_hours_inbound_pct: float | None = None
    # WAHA chat metadata (cross-validation)
    wa_unread_count: int | None = None
    wa_is_muted: bool = False
    wa_is_archived: bool = False
    # Client relationship — new vs returning
    # "new"       first-time client (no prior messages in WAHA history)
    # "returning" client has had previous conversations with this business
    # "internal"  collaborator, supplier, or internal contact (not a customer)
    # "uncertain" insufficient signals to classify
    client_relationship: str | None = None
    # "deterministic" = WAHA confirmed (pre-window message check)
    # "ai"            = AI inferred from conversation text
    # "both"          = both deterministic and AI agree
    client_relationship_source: str | None = None
    client_relationship_signals: list[str] = Field(default_factory=list)
    # Commercial proposal funnel
    has_purchase_intent: bool = False
    intent_stage: str | None = None           # none/exploring/quote_requested/quoted/negotiating/converted/lost/pending
    intent_first_at: datetime | None = None
    quote_requested_at: datetime | None = None
    quote_sent_at: datetime | None = None
    quote_response_time_seconds: int | None = None
    post_quote_followup_count: int | None = None
    followup_delay_hours: float | None = None
    lost_reason: str | None = None            # price/competition/timing/no_reply/changed_mind/other
    lost_reason_detail: str | None = None
    # Health / Insights
    health_score: float | None = None
    recommendations: list[str] = Field(default_factory=list)
    alerts: list[str] = Field(default_factory=list)
    # Meta
    ai_provider: str | None = None
    ai_model: str | None = None
    tokens_input: int = 0
    tokens_output: int = 0
    tokens_used: int = 0
    analysis_cost_usd: float = 0.0


class AnalysisResultResponse(BaseModel):
    job_id: str
    client_id: str
    status: AnalysisStatus
    total_conversations: int
    conversations: list[ConversationAnalysisResult] = Field(default_factory=list)
    overall_health_score: float | None = None
    overall_recommendations: list[str] = Field(default_factory=list)
    overall_alerts: list[str] = Field(default_factory=list)
    total_tokens_used: int = 0
    total_cost_usd: float = 0.0


# --- Client CRUD ---

class ClientCreateRequest(BaseModel):
    name: str
    email: EmailStr
    business_name: str
    business_type: str | None = None
    business_identifiers: list[str] = Field(default_factory=list)
    phone: str | None = None
    average_transaction_value: float | None = None
    # Habeas Data (Ley 1581/2012): explicit acceptance of Privacy Policy +
    # Terms of Service. The route enforces this must be True.
    policies_accepted: bool = False


class ClientUpdateRequest(BaseModel):
    name: str | None = None
    business_name: str | None = None
    business_type: str | None = None
    business_identifiers: list[str] | None = None
    phone: str | None = None
    plan: str | None = None
    average_transaction_value: float | None = None


class ClientResponse(BaseModel):
    id: UUID
    name: str
    email: str
    phone: str | None
    business_name: str
    business_type: str | None
    business_identifiers: list
    plan: str
    subscription_status: str
    onboarded_via: str
    is_active: bool
    average_transaction_value: float | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Dashboard (Phase 2 stubs) ---

class DashboardOverview(BaseModel):
    total_conversations: int = 0
    total_messages: int = 0
    avg_response_time_seconds: float | None = None
    health_score: float | None = None
    sentiment_breakdown: dict[str, int] = Field(default_factory=dict)
    conversion_rate: float | None = None


# --- Trends ---

class JobTrendPoint(BaseModel):
    job_id: str
    date: str
    label: str
    health_score: float | None = None
    total_conversations: int = 0
    avg_response_time_min: float | None = None
    first_response_time_min: float | None = None
    positive_pct: float = 0.0
    neutral_pct: float = 0.0
    negative_pct: float = 0.0
    conversion_rate: float | None = None
    avg_quality_score: float | None = None
    converted_count: int = 0
    applicable_count: int = 0
    top_topics: list[str] = Field(default_factory=list)


class HealthDimension(BaseModel):
    name: str
    key: str
    raw_score: float
    weight: float
    max_points: int
    obtained_points: float
    pct_of_max: float
    color: str
    is_strength: bool
    is_critical: bool


class TopicFrequency(BaseModel):
    label: str
    count: int
    pct: float


class TrendsSummary(BaseModel):
    total_reports: int = 0
    total_conversations: int = 0
    latest_health_score: float | None = None
    latest_label: str | None = None
    avg_health_score: float | None = None
    trend_direction: str = "stable"
    health_breakdown: list[HealthDimension] = Field(default_factory=list)
    top_topics: list[TopicFrequency] = Field(default_factory=list)


class TrendsResponse(BaseModel):
    jobs: list[JobTrendPoint] = Field(default_factory=list)
    summary: TrendsSummary
