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


# --- Analysis Results ---

class QualityBreakdown(BaseModel):
    helpfulness: float = 5.0
    tone: float = 5.0
    completeness: float = 5.0
    speed_perception: float = 5.0


class ConversationAnalysisResult(BaseModel):
    conversation_id: str
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
    # Metrics
    first_response_time_seconds: float | None = None
    avg_response_time_seconds: float | None = None
    median_response_time_seconds: float | None = None
    p95_response_time_seconds: float | None = None
    unanswered_count: int = 0
    total_messages: int = 0
    inbound_count: int = 0
    outbound_count: int = 0
    duration_minutes: float | None = None
    response_time_by_hour: dict[str, float] | None = None
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
