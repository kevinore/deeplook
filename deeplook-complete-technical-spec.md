# DeepLook — Complete Technical Specification
## WhatsApp Conversation Analytics Platform
### Version 1.0 — MVP

---

## Table of Contents

1. Product Overview
2. Architecture Overview & Diagram
3. Technology Stack
4. Project Setup & Configuration
5. Project Structure
6. Database Design (Supabase)
7. Data Models & Schemas (Pydantic)
8. Ingestion Layer — Detailed Specification
9. Analytics Core — Detailed Specification
10. AI Provider Abstraction — Detailed Specification
11. Delivery Layer — Detailed Specification
12. API Endpoints — Full Specification
13. Background Processing
14. Error Handling Strategy
15. Testing Strategy
16. Deployment & Infrastructure
17. Build Order (Sprint Plan)

---

## 1. Product Overview

DeepLook is a SaaS tool that analyzes WhatsApp Business conversations to give small businesses actionable insights. Businesses upload their WhatsApp chat exports (.txt files) or connect via Meta Cloud API, and receive analysis including: response times, customer sentiment, conversation topics, quality scores, lost sales opportunities, and specific recommendations to improve.

### Core user flow (MVP)

1. Client signs up and uploads one or more WhatsApp chat export .txt files
2. Client provides their business name/identifiers so the system knows which messages are theirs
3. System parses files into structured data
4. System runs deterministic metrics (response times, volumes, patterns)
5. System runs AI analysis (sentiment, topics, quality, conversion detection)
6. System generates a PDF report with all findings and recommendations
7. Client downloads the report or receives it via email

### Key constraints

- The analytics core must be completely independent of the data source. It processes NormalizedMessage objects and does not know if they came from a .txt file or from Meta webhooks.
- The AI layer must support multiple providers (OpenAI, Anthropic, Google Gemini, Mistral) through an abstraction. Switching providers is a configuration change, not a code change.
- Parsing of .txt files must be deterministic — no AI used for parsing. Regex and rule-based logic only.
- The system must handle both single file and multi-file uploads. Each .txt file represents one conversation thread.

---

## 2. Architecture Overview

The system is organized into four distinct layers. Data flows downward through them. No layer has direct knowledge of the layers above it.

### Layer 1: Ingestion Layer
Responsible for receiving data from any source and converting it into the unified NormalizedMessage format. Contains parsers for each data source. Exposes upload endpoints and webhook receivers. Output is always a NormalizedBatch containing NormalizedConversation objects, each containing NormalizedMessage objects.

### Layer 2: Persistence Layer
Supabase (PostgreSQL). Stores clients, contacts, conversations, messages, analysis results, and aggregated metrics. All tables are accessed through a repository pattern — no direct database queries in route handlers or analytics code.

### Layer 3: Analytics Core
The product's brain. Split into two sub-systems:
- Metrics Engine: Pure mathematical calculations on message data. No AI, no external calls. Calculates response times, message volumes, activity patterns, unanswered message counts.
- AI Analysis Engine: Sends conversation text to an AI provider through the abstraction layer. Extracts sentiment, topics, quality scores, conversion status, summaries, and key points.
- Insights Generator: Combines metrics and AI results into a health score, actionable recommendations, and alerts.

### Layer 4: Delivery Layer
Takes analysis results and presents them to clients. Contains PDF report generator, dashboard API endpoints, and email notification system.

### Architecture Diagram (ASCII)

```
CLIENTS
  │
  ├── Browser: Upload .txt files ──────────────────┐
  ├── Meta Cloud API: Webhooks (Phase 2) ──────────┤
  └── Future: Dualhook, other sources ─────────────┤
                                                    ▼
┌──────────────────────────────────────────────────────────────┐
│ LAYER 1: INGESTION                                           │
│                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────┐ │
│  │ TxtParser    │  │ MetaWebhook  │  │ Future parsers      │ │
│  │              │  │ Parser       │  │ (implement          │ │
│  │ Pass 1:      │  │              │  │  BaseParser)        │ │
│  │  Classify    │  │ Structured   │  │                     │ │
│  │  each line   │  │ JSON mapping │  │                     │ │
│  │ Pass 2:      │  │              │  │                     │ │
│  │  Assemble    │  │              │  │                     │ │
│  │  messages    │  │              │  │                     │ │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬──────────┘ │
│         │                 │                     │            │
│         └─────────────────┼─────────────────────┘            │
│                           ▼                                  │
│              ┌────────────────────────┐                      │
│              │ Normalizer             │                      │
│              │                        │                      │
│              │ Input: any raw data    │                      │
│              │ Output: NormalizedBatch │                      │
│              │  └─ NormalizedConv[]    │                      │
│              │      └─ NormalizedMsg[] │                      │
│              └────────────┬───────────┘                      │
│                           │                                  │
│              ┌────────────────────────┐                      │
│              │ ParseQualityReport     │                      │
│              │ (validation + stats)   │                      │
│              └────────────────────────┘                      │
└───────────────────────────┼──────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ LAYER 2: PERSISTENCE (Supabase PostgreSQL)                   │
│                                                              │
│  clients ─── contacts ─── conversations ─── messages         │
│                                │                             │
│                          analysis_jobs                       │
│                                │                             │
│                     conversation_analysis                    │
│                                │                             │
│                         daily_metrics                        │
│                                                              │
│  Accessed via Repository classes (not direct queries)        │
└───────────────────────────┼──────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ LAYER 3: ANALYTICS CORE                                      │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ AnalyticsEngine (orchestrator)                       │    │
│  │                                                      │    │
│  │  1. Receives NormalizedConversation[]                 │    │
│  │  2. Runs MetricsEngine (pure math)                   │    │
│  │  3. Runs AIAnalysisEngine (via provider abstraction)  │    │
│  │  4. Runs InsightsGenerator (combines both)           │    │
│  │  5. Returns ConversationAnalysisResult[]              │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌────────────────┐  ┌────────────────┐  ┌───────────────┐  │
│  │ MetricsEngine  │  │ AIAnalysis     │  │ Insights      │  │
│  │                │  │ Engine         │  │ Generator     │  │
│  │ • Response     │  │                │  │               │  │
│  │   times        │  │ • Sentiment    │  │ • Health      │  │
│  │ • Volumes      │  │ • Topics       │  │   score       │  │
│  │ • Activity     │  │ • Quality      │  │ • Recommend-  │  │
│  │   patterns     │  │ • Conversion   │  │   ations      │  │
│  │ • Unanswered   │  │ • Summary      │  │ • Alerts      │  │
│  │ • Duration     │  │ • Key points   │  │ • Trends      │  │
│  │                │  │                │  │               │  │
│  │ NO AI          │  │ Uses AI only   │  │ NO AI         │  │
│  │ NO external    │  │                │  │ Rule-based    │  │
│  │ calls          │  │                │  │ logic         │  │
│  └────────────────┘  └───────┬────────┘  └───────────────┘  │
│                              │                               │
│                 ┌────────────▼────────────┐                  │
│                 │ AI Provider Abstraction │                  │
│                 │                         │                  │
│                 │  ┌──────┐ ┌──────────┐  │                  │
│                 │  │OpenAI│ │Anthropic │  │                  │
│                 │  └──────┘ └──────────┘  │                  │
│                 │  ┌──────┐ ┌──────────┐  │                  │
│                 │  │Gemini│ │ Mistral  │  │                  │
│                 │  └──────┘ └──────────┘  │                  │
│                 └────────────────────────┘                   │
└───────────────────────────┼──────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ LAYER 4: DELIVERY                                            │
│                                                              │
│  ┌────────────────┐  ┌────────────────┐  ┌───────────────┐  │
│  │ PDF Report     │  │ Dashboard API  │  │ Email/Alerts  │  │
│  │ Generator      │  │ (Phase 2)      │  │ (Phase 2)     │  │
│  │                │  │                │  │               │  │
│  │ HTML template  │  │ REST endpoints │  │ SMTP sender   │  │
│  │ + WeasyPrint   │  │ for frontend   │  │ Alert rules   │  │
│  └────────────────┘  └────────────────┘  └───────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. Technology Stack

### Runtime & Framework
- Python 3.12+
- FastAPI as the web framework
- Uvicorn as the ASGI server
- Pydantic v2 for data validation and serialization

### Database
- Supabase (hosted PostgreSQL)
- SQLAlchemy 2.0 as ORM (async mode with asyncpg driver)
- Alembic for database migrations

### AI Providers (abstracted)
- openai Python SDK for OpenAI models
- anthropic Python SDK for Claude models
- google-generativeai SDK for Gemini models (future)
- httpx for any REST-based providers (Mistral, local)

### PDF Generation
- WeasyPrint for HTML-to-PDF conversion
- Jinja2 for HTML report templates

### Background Processing
- FastAPI BackgroundTasks for simple async processing (MVP)
- Upgrade to Celery + Redis if needed at scale

### API Documentation
- Swagger UI (built into FastAPI, available at /docs)
- ReDoc (built into FastAPI, available at /redoc)

### Testing
- pytest with pytest-asyncio for async tests
- httpx for API integration tests
- pytest-cov for coverage reporting

### Additional Libraries
- python-multipart for file upload handling
- python-dotenv for environment variable loading
- email-validator for email validation
- uuid for generating unique identifiers
- aiofiles for async file operations

### Development Tools
- Ruff for linting and formatting
- mypy for type checking
- pre-commit hooks for code quality

---

## 4. Project Setup & Configuration

### Step 1: Initialize the project

Create a new Python project using pyproject.toml (not requirements.txt). The project name is "deeplook". Use src layout is not required — flat app/ layout is preferred for FastAPI projects.

### Step 2: Install dependencies

Core dependencies:
- fastapi[standard] (includes uvicorn, python-multipart, email-validator)
- sqlalchemy[asyncio] with asyncpg driver
- alembic
- pydantic-settings (for configuration management)
- supabase (Supabase Python client, for storage/auth features if needed)
- openai
- anthropic
- jinja2
- weasyprint
- aiofiles
- httpx

Dev dependencies:
- pytest
- pytest-asyncio
- pytest-cov
- ruff
- mypy

### Step 3: Environment variables

Create a .env file and a .env.example file. The .env.example must be committed to git; .env must be in .gitignore.

Required environment variables:

```
# App
APP_NAME=DeepLook
APP_ENV=development
DEBUG=true
API_SECRET_KEY=<random-32-char-string>
CORS_ORIGINS=http://localhost:3000,http://localhost:8000

# Supabase
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=eyJhbGciOiJI...
DATABASE_URL=postgresql+asyncpg://postgres:password@db.xxxxx.supabase.co:5432/postgres

# AI Providers (only the active one is required)
AI_PROVIDER=openai
AI_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# File Upload
MAX_UPLOAD_SIZE_MB=50
MAX_FILES_PER_UPLOAD=100

# Meta WhatsApp (Phase 2 — optional for MVP)
META_VERIFY_TOKEN=
META_ACCESS_TOKEN=
META_PHONE_NUMBER_ID=
META_APP_SECRET=
```

### Step 4: Configuration class

Create a Settings class using pydantic-settings that reads from .env. All settings must have types and defaults where appropriate. The settings class must be instantiated once as a module-level singleton and imported wherever needed.

### Step 5: FastAPI application setup

The main FastAPI application must be configured with:
- Title: "DeepLook API"
- Description: "WhatsApp Conversation Analytics Platform"
- Version: "1.0.0"
- Swagger UI available at /docs
- ReDoc available at /redoc
- CORS middleware configured to allow origins from the CORS_ORIGINS setting
- A /health endpoint that returns {"status": "ok", "version": "1.0.0"}
- Routers organized by domain: ingestion router, analytics router, delivery router, clients router
- All routers prefixed with /api/v1
- OpenAPI tags for grouping endpoints in Swagger: "Ingestion", "Analytics", "Delivery", "Clients"
- Exception handlers for custom application errors
- Startup event that verifies database connectivity
- Startup event that verifies AI provider connectivity (optional, log warning if fails)

---

## 5. Project Structure

```
deeplook/
├── app/
│   ├── __init__.py
│   ├── main.py                          # FastAPI app, middleware, startup events
│   ├── config.py                        # Settings class with pydantic-settings
│   ├── dependencies.py                  # Dependency injection: get_db, get_ai_provider
│   ├── exceptions.py                    # Custom exception classes
│   │
│   ├── models/                          # Database models + Pydantic schemas
│   │   ├── __init__.py
│   │   ├── database.py                  # SQLAlchemy ORM models (Client, Contact, Conversation, Message, etc.)
│   │   ├── schemas.py                   # Pydantic request/response schemas for API
│   │   ├── normalized.py                # NormalizedMessage, NormalizedConversation, NormalizedBatch
│   │   └── enums.py                     # MessageDirection, MessageType, AnalysisStatus, etc.
│   │
│   ├── repositories/                    # Data access layer (DB queries)
│   │   ├── __init__.py
│   │   ├── base.py                      # Base repository with common CRUD operations
│   │   ├── client_repo.py              # Client table operations
│   │   ├── conversation_repo.py        # Conversation + Message table operations
│   │   └── analysis_repo.py            # Analysis results + daily metrics operations
│   │
│   ├── ingestion/                       # Layer 1: Data ingestion
│   │   ├── __init__.py
│   │   ├── router.py                    # API endpoints: POST /upload, POST /webhook
│   │   ├── normalizer.py               # NormalizedMessage/Batch definitions and validation
│   │   ├── validators.py               # File validation: size, extension, encoding
│   │   ├── parsers/
│   │   │   ├── __init__.py
│   │   │   ├── base.py                  # Abstract BaseParser interface
│   │   │   ├── txt_parser.py            # WhatsApp .txt export parser (the complex one)
│   │   │   ├── txt_timestamp.py         # Timestamp extraction logic (separated for testability)
│   │   │   ├── txt_classifier.py        # Line classification logic (Pass 1)
│   │   │   ├── txt_assembler.py         # Message assembly logic (Pass 2)
│   │   │   ├── txt_direction.py         # Business vs Customer detection
│   │   │   ├── txt_media.py             # Media message detection
│   │   │   ├── txt_system.py            # System message detection and filtering
│   │   │   └── meta_webhook.py          # Meta Cloud API webhook parser (Phase 2)
│   │   └── quality.py                   # ParseQualityReport generation
│   │
│   ├── analytics/                       # Layer 3: Analytics core
│   │   ├── __init__.py
│   │   ├── engine.py                    # AnalyticsEngine orchestrator
│   │   ├── pipeline.py                  # Full pipeline: ingest → store → analyze → deliver
│   │   ├── metrics/
│   │   │   ├── __init__.py
│   │   │   ├── response_time.py         # Response time calculations
│   │   │   ├── volume.py                # Message volume metrics
│   │   │   ├── activity.py              # Peak hours, busiest days, patterns
│   │   │   └── conversations.py         # Conversation-level stats (duration, msg count)
│   │   ├── ai/
│   │   │   ├── __init__.py
│   │   │   ├── provider.py              # Abstract AIProvider interface + AIResponse model
│   │   │   ├── factory.py               # Provider factory: returns correct provider from config
│   │   │   ├── providers/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── openai_provider.py   # OpenAI implementation
│   │   │   │   ├── anthropic_provider.py # Anthropic Claude implementation
│   │   │   │   └── mock_provider.py     # Mock provider for testing (returns deterministic results)
│   │   │   ├── prompts/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── combined.py          # Single combined prompt for full analysis
│   │   │   │   ├── formatter.py         # Formats NormalizedConversation into AI-readable text
│   │   │   │   └── response_parser.py   # Parses AI JSON response into typed objects
│   │   │   └── cost_tracker.py          # Tracks AI usage costs per client
│   │   └── insights/
│   │       ├── __init__.py
│   │       ├── health_score.py          # Business health score (0-100) calculator
│   │       ├── recommendations.py       # Rule-based recommendation engine
│   │       └── alerts.py               # Anomaly detection and alert generation
│   │
│   ├── delivery/                        # Layer 4: Output delivery
│   │   ├── __init__.py
│   │   ├── router.py                    # API endpoints: GET /reports, GET /dashboard
│   │   ├── reports/
│   │   │   ├── __init__.py
│   │   │   ├── pdf_generator.py         # Orchestrates PDF creation
│   │   │   ├── chart_generator.py       # Creates chart images for the PDF
│   │   │   └── templates/
│   │   │       ├── base.html            # Base HTML template with CSS
│   │   │       ├── report.html          # Full report template
│   │   │       └── styles.css           # Report styling
│   │   └── notifications/
│   │       ├── __init__.py
│   │       └── email.py                 # Email sender (Phase 2)
│   │
│   ├── clients/                         # Client management
│   │   ├── __init__.py
│   │   └── router.py                   # API endpoints: CRUD for clients
│   │
│   └── workers/                         # Background job processing
│       ├── __init__.py
│       └── analysis_worker.py          # Async analysis job processor
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                      # Shared fixtures, test DB setup
│   ├── fixtures/                        # Sample data files for testing
│   │   ├── sample_chat_spanish.txt      # Real Spanish WhatsApp export
│   │   ├── sample_chat_english.txt      # Real English WhatsApp export
│   │   ├── sample_chat_multiline.txt    # Chat with multi-line messages
│   │   ├── sample_chat_media.txt        # Chat with media indicators
│   │   ├── sample_chat_minimal.txt      # 2-3 message chat
│   │   ├── sample_meta_webhook.json     # Meta webhook payload sample
│   │   └── sample_meta_history.json     # Meta history webhook sample
│   ├── test_ingestion/
│   │   ├── test_txt_parser.py
│   │   ├── test_txt_timestamp.py
│   │   ├── test_txt_classifier.py
│   │   ├── test_txt_direction.py
│   │   ├── test_txt_system.py
│   │   └── test_quality_report.py
│   ├── test_analytics/
│   │   ├── test_response_time.py
│   │   ├── test_volume.py
│   │   ├── test_activity.py
│   │   ├── test_health_score.py
│   │   └── test_engine.py
│   ├── test_ai/
│   │   ├── test_provider_abstraction.py
│   │   ├── test_prompt_formatting.py
│   │   └── test_response_parsing.py
│   └── test_api/
│       ├── test_upload_endpoint.py
│       ├── test_health_endpoint.py
│       └── test_report_endpoint.py
│
├── alembic/                             # Database migrations
│   ├── env.py
│   ├── alembic.ini
│   └── versions/
│
├── .env.example
├── .gitignore
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml                   # For local development
└── README.md
```

---

## 6. Database Design (Supabase PostgreSQL)

### Table: clients

Stores businesses that use DeepLook.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK, default gen_random_uuid() | Unique identifier |
| name | VARCHAR(255) | NOT NULL | Contact person name |
| email | VARCHAR(255) | UNIQUE, NOT NULL | Login email |
| phone | VARCHAR(50) | NULLABLE | Contact phone |
| business_name | VARCHAR(255) | NOT NULL | Business display name |
| business_type | VARCHAR(100) | NULLABLE | Industry: restaurant, clinic, salon, etc. |
| business_identifiers | JSONB | DEFAULT '[]' | List of names/phones the business uses in WhatsApp. Used to detect which messages are from the business. Example: ["Wellness By Diego Omar", "+57 313 4859647", "Valentina"] |
| plan | VARCHAR(50) | DEFAULT 'free' | Subscription plan: free, basic, pro |
| waba_id | VARCHAR(100) | NULLABLE | WhatsApp Business Account ID (for API clients, Phase 2) |
| phone_number_id | VARCHAR(100) | NULLABLE | Meta phone number ID (for API clients, Phase 2) |
| onboarded_via | VARCHAR(50) | DEFAULT 'file_upload' | How the client connected: file_upload, meta_api, dualhook |
| is_active | BOOLEAN | DEFAULT true | Soft delete flag |
| created_at | TIMESTAMPTZ | DEFAULT NOW() | Record creation |
| updated_at | TIMESTAMPTZ | DEFAULT NOW() | Last update |

### Table: contacts

Stores unique customer contacts per client. A contact is someone who has chatted with the business.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | Unique identifier |
| client_id | UUID | FK → clients(id) ON DELETE CASCADE | Which business this contact belongs to |
| phone | VARCHAR(50) | NOT NULL | Contact phone number (or "unknown" for .txt imports without phone) |
| name | VARCHAR(255) | NULLABLE | Contact display name |
| first_seen_at | TIMESTAMPTZ | NULLABLE | First message timestamp |
| last_seen_at | TIMESTAMPTZ | NULLABLE | Most recent message timestamp |
| total_conversations | INT | DEFAULT 0 | Count of conversations with this contact |
| tags | JSONB | DEFAULT '[]' | User-defined or auto-generated tags |
| created_at | TIMESTAMPTZ | DEFAULT NOW() | Record creation |

Unique constraint: (client_id, phone) — one contact per phone per business. For .txt imports where the phone is unknown, use the sender name as the phone field to maintain uniqueness.

### Table: conversations

One conversation thread between a business and a contact.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | Unique identifier |
| client_id | UUID | FK → clients(id) ON DELETE CASCADE | Which business |
| contact_id | UUID | FK → contacts(id) ON DELETE CASCADE | Which customer |
| started_at | TIMESTAMPTZ | NOT NULL | Timestamp of first message |
| last_message_at | TIMESTAMPTZ | NULLABLE | Timestamp of last message |
| message_count | INT | DEFAULT 0 | Total messages in this conversation |
| inbound_count | INT | DEFAULT 0 | Messages from customer |
| outbound_count | INT | DEFAULT 0 | Messages from business |
| status | VARCHAR(50) | DEFAULT 'active' | active, closed, stale |
| source | VARCHAR(50) | NOT NULL | txt_upload, meta_api, meta_history |
| source_filename | VARCHAR(500) | NULLABLE | Original filename if from .txt upload |
| created_at | TIMESTAMPTZ | DEFAULT NOW() | Record creation |

Indexes: (client_id), (client_id, started_at), (client_id, source)

### Table: messages

Individual messages within conversations.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | Unique identifier |
| conversation_id | UUID | FK → conversations(id) ON DELETE CASCADE | Parent conversation |
| source_id | VARCHAR(255) | NULLABLE | Original message ID from source. Used for deduplication. |
| timestamp | TIMESTAMPTZ | NOT NULL | When the message was sent |
| direction | VARCHAR(20) | NOT NULL | inbound, outbound, system |
| sender_phone | VARCHAR(50) | NULLABLE | Phone of sender |
| sender_name | VARCHAR(255) | NULLABLE | Display name of sender |
| message_type | VARCHAR(50) | DEFAULT 'text' | text, image, video, audio, document, location, contact, sticker, unknown |
| text_content | TEXT | NULLABLE | Message text body. NULL for media-only messages. |
| media_url | TEXT | NULLABLE | Media URL if applicable |
| metadata | JSONB | DEFAULT '{}' | Source-specific extra data |
| created_at | TIMESTAMPTZ | DEFAULT NOW() | Record creation |

Indexes: (conversation_id), (conversation_id, timestamp)
Deduplication index: UNIQUE (conversation_id, source_id) WHERE source_id IS NOT NULL

### Table: analysis_jobs

Tracks analysis processing jobs.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | Unique identifier |
| client_id | UUID | FK → clients(id) ON DELETE CASCADE | Which business |
| status | VARCHAR(50) | DEFAULT 'pending' | pending, processing, completed, failed |
| job_type | VARCHAR(50) | NOT NULL | full_analysis, incremental, single_conversation |
| total_conversations | INT | DEFAULT 0 | Total conversations to analyze |
| processed_conversations | INT | DEFAULT 0 | Conversations analyzed so far |
| ai_provider | VARCHAR(50) | NULLABLE | Which AI provider was used |
| ai_model | VARCHAR(100) | NULLABLE | Which model was used |
| total_tokens_used | INT | DEFAULT 0 | Sum of all tokens consumed |
| total_cost_usd | FLOAT | DEFAULT 0 | Estimated total AI cost |
| error_message | TEXT | NULLABLE | Error details if failed |
| started_at | TIMESTAMPTZ | NULLABLE | Processing start time |
| completed_at | TIMESTAMPTZ | NULLABLE | Processing end time |
| created_at | TIMESTAMPTZ | DEFAULT NOW() | Record creation |

### Table: conversation_analysis

AI analysis results per conversation per job. One row per conversation per analysis run.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | Unique identifier |
| conversation_id | UUID | FK → conversations(id) ON DELETE CASCADE | Which conversation |
| analysis_job_id | UUID | FK → analysis_jobs(id) ON DELETE SET NULL | Which job produced this |
| sentiment | VARCHAR(20) | NULLABLE | positive, neutral, negative |
| sentiment_score | FLOAT | NULLABLE | -1.0 (very negative) to 1.0 (very positive) |
| sentiment_reason | TEXT | NULLABLE | Why this sentiment was assigned |
| primary_topic | VARCHAR(100) | NULLABLE | Main conversation topic |
| secondary_topics | JSONB | DEFAULT '[]' | Other topics mentioned |
| quality_score | FLOAT | NULLABLE | 0-10 overall quality rating |
| quality_breakdown | JSONB | DEFAULT '{}' | {helpfulness, tone, completeness, speed_perception} each 0-10 |
| conversion_status | VARCHAR(50) | NULLABLE | converted, lost, pending, not_applicable |
| conversion_reason | TEXT | NULLABLE | Why the conversion status was assigned |
| summary | TEXT | NULLABLE | 2-3 sentence conversation summary |
| key_points | JSONB | DEFAULT '[]' | List of key takeaways |
| ai_provider | VARCHAR(50) | NULLABLE | Provider used |
| ai_model | VARCHAR(100) | NULLABLE | Model used |
| tokens_used | INT | DEFAULT 0 | Tokens consumed for this analysis |
| analysis_cost_usd | FLOAT | DEFAULT 0 | Estimated cost |
| analyzed_at | TIMESTAMPTZ | DEFAULT NOW() | When analysis was performed |

Unique constraint: (conversation_id, analysis_job_id)

### Table: daily_metrics

Pre-aggregated daily metrics per client. Computed by a background job.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | Unique identifier |
| client_id | UUID | FK → clients(id) ON DELETE CASCADE | Which business |
| date | DATE | NOT NULL | The date these metrics represent |
| total_conversations | INT | DEFAULT 0 | Conversations active on this day |
| total_messages | INT | DEFAULT 0 | Messages sent/received on this day |
| inbound_messages | INT | DEFAULT 0 | Customer messages |
| outbound_messages | INT | DEFAULT 0 | Business messages |
| unique_contacts | INT | DEFAULT 0 | Distinct customers |
| avg_response_time_seconds | FLOAT | NULLABLE | Average business response time |
| median_response_time_seconds | FLOAT | NULLABLE | Median business response time |
| p95_response_time_seconds | FLOAT | NULLABLE | 95th percentile response time |
| unanswered_count | INT | DEFAULT 0 | Messages without business response |
| positive_count | INT | DEFAULT 0 | Positive sentiment conversations |
| neutral_count | INT | DEFAULT 0 | Neutral sentiment conversations |
| negative_count | INT | DEFAULT 0 | Negative sentiment conversations |
| converted_count | INT | DEFAULT 0 | Conversations that converted |
| lost_count | INT | DEFAULT 0 | Conversations that were lost |
| top_topics | JSONB | DEFAULT '[]' | [{topic: "pricing", count: 12}, ...] |
| health_score | FLOAT | NULLABLE | 0-100 overall health score |
| computed_at | TIMESTAMPTZ | DEFAULT NOW() | When metrics were computed |

Unique constraint: (client_id, date)

---

## 7. Data Models & Schemas (Pydantic)

### Normalized Models (the contract between layers)

These models live in app/models/normalized.py and represent the unified data format.

**NormalizedMessage**: Represents a single message from any source. Fields: source_id (str), timestamp (datetime), direction (MessageDirection enum), sender_phone (str or None), sender_name (str or None), recipient_phone (str or None), message_type (MessageType enum), text_content (str or None), media_url (str or None), metadata (dict, default empty).

**NormalizedConversation**: A thread of messages. Fields: contact_phone (str), contact_name (str or None), messages (list of NormalizedMessage), source (str: "txt_upload", "meta_api", "meta_history").

**NormalizedBatch**: A complete ingestion batch. Fields: client_id (str), source (str), ingested_at (datetime), conversations (list of NormalizedConversation), raw_metadata (dict, default empty).

### Enums (app/models/enums.py)

**MessageDirection**: INBOUND = "inbound", OUTBOUND = "outbound", SYSTEM = "system"

**MessageType**: TEXT, IMAGE, VIDEO, AUDIO, DOCUMENT, LOCATION, CONTACT, STICKER, UNKNOWN

**AnalysisStatus**: PENDING, PROCESSING, COMPLETED, FAILED

**ConversionStatus**: CONVERTED, LOST, PENDING, NOT_APPLICABLE

**Sentiment**: POSITIVE, NEUTRAL, NEGATIVE

### API Request/Response Schemas (app/models/schemas.py)

**UploadRequest** (multipart form): files (list of UploadFile), business_name (str, required), business_identifiers (list of str, required — names and/or phones the business uses in WhatsApp chats)

**UploadResponse**: job_id (UUID), files_received (int), conversations_parsed (int), parse_errors (list of {file: str, error: str}), parse_quality (ParseQualityReport), status (str: "processing")

**JobStatusResponse**: job_id (UUID), status (AnalysisStatus), total_conversations (int), processed_conversations (int), progress_percent (float), error_message (str or None), report_url (str or None — available when completed)

**AnalysisResultResponse**: Full analysis results including all metrics, AI analysis, insights, and health score. Used by the dashboard and report generator.

**ClientCreateRequest**: name (str), email (str), business_name (str), business_type (str, optional), business_identifiers (list of str)

**ClientResponse**: All client fields minus sensitive data.

**ParseQualityReport**: total_lines (int), parsed_messages (int), system_messages_filtered (int), continuation_lines_merged (int), empty_lines_skipped (int), unparseable_lines (int), unparseable_samples (list of str, max 5), unique_senders (list of str), detected_business (str or None), detected_customers (list of str), date_range_start (datetime or None), date_range_end (datetime or None), message_type_counts (dict), direction_counts (dict), confidence_score (float 0-1), warnings (list of str).

---

## 8. Ingestion Layer — Detailed Specification

### 8.1 File Upload Endpoint

Path: POST /api/v1/upload
Content-Type: multipart/form-data
Tags: Ingestion

Accepts one or more .txt files plus form fields for business_name and business_identifiers.

Validation rules:
- Each file must have .txt extension
- Each file must be under MAX_UPLOAD_SIZE_MB (default 50MB)
- Maximum MAX_FILES_PER_UPLOAD files per request (default 100)
- Files must be UTF-8 or Latin-1 encoded. Try UTF-8 first; if decode fails, try Latin-1. If both fail, return error for that specific file.
- Total batch size must not exceed 200MB

Processing flow:
1. Validate all files (extension, size, encoding)
2. Parse each file independently using TxtParser
3. Generate ParseQualityReport for the batch
4. Store all conversations and messages in database
5. Create an analysis_job record with status "pending"
6. Queue the analysis job for background processing
7. Return UploadResponse with job_id and parse quality info

Error handling:
- If some files fail to parse, still process the successful ones. Return errors for failed files in the parse_errors array.
- If ALL files fail, return HTTP 422 with details.
- If database storage fails, return HTTP 500.

### 8.2 WhatsApp .txt Parser — Full Specification

The parser uses a two-pass approach for reliability and debuggability.

**Pass 1: Line Classification**

Every line in the file is classified into one of four types:
- MESSAGE_START: Line has a valid timestamp, a separator " - ", a sender name/phone, a colon-space ": ", and content
- SYSTEM_MESSAGE: Line has a valid timestamp and separator but no sender (system notification)
- CONTINUATION: Line does not start with a timestamp pattern. It is a continuation of the previous message.
- EMPTY: Line is blank or whitespace only

The classifier must handle these timestamp formats, all of which have been observed in real WhatsApp exports:

1. Spanish Android 12h: `1/11/25, 10:39 a. m.` (note spaces in "a. m.")
2. Spanish Android 12h variant: `1/11/25, 10:39 a.m.` (no space)
3. Spanish Android 12h variant: `01/11/2025, 10:39 a. m.` (4-digit year)
4. English Android 12h: `1/11/25, 10:39 AM`
5. Android 24h: `1/11/25, 22:39`
6. iOS Spanish: `[1/11/25, 10:39:00 a. m.]` (brackets, seconds)
7. iOS English: `[1/11/25, 10:39:00 AM]`

The timestamp extractor must be a separate module (txt_timestamp.py) so it can be tested independently with dozens of format variations.

Date ambiguity: When both day and month are 12 or less (e.g., 1/11/25 could be Jan 11 or Nov 1), assume DD/MM/YY format because the target market is Colombia/LATAM. This is a configurable default.

AM/PM handling: The Spanish "a. m." and "p. m." variants are the trickiest. The regex must handle: "a. m.", "a.m.", "AM", "am", "p. m.", "p.m.", "PM", "pm". When AM/PM is present, convert to 24h format. When no AM/PM marker is found, assume 24h format.

Two-digit year handling: If year < 100, add 2000.

**Pass 2: Message Assembly**

After all lines are classified, assemble them into complete messages:
- When a MESSAGE_START is found, save the previous message (if any) and start a new one
- When a CONTINUATION is found, append its content to the current message with a newline separator
- When a SYSTEM_MESSAGE is found, save the current message and discard the system message
- When EMPTY is found, ignore it (do not break the current message)
- After processing all lines, save the last message

Multi-line messages are critical to handle correctly. In the sample data, the facial cleaning service description spans 10+ lines with bullet points. All those lines must be concatenated into a single message.

**System Message Detection**

A comprehensive list of system message indicators must be maintained in both Spanish and English. The list includes but is not limited to:
- Encryption notices
- Group creation/modification notices
- Member add/remove notices
- Ad/Facebook integration notices
- Security code changes
- Disappearing message notices
- Pinned message notices
- Any line containing HTML tags like `<b>` or `</b>`

System messages must be completely excluded from the analysis. They are not from either the business or the customer.

**Business vs Customer Direction Detection**

The client provides business_identifiers at upload time. These are strings that identify the business in chat exports — the business display name, phone numbers, or team member names.

Direction classification logic:
1. Compare the sender against each business_identifier using case-insensitive partial matching
2. For phone numbers, normalize both sides (remove spaces, dashes, parentheses, country code prefix) and compare the last 10 digits
3. If any identifier matches, the message direction is OUTBOUND (business sent it)
4. If no identifier matches, the message direction is INBOUND (customer sent it)

If business_identifiers are not provided, use auto-detection heuristic: the sender who uses a display name (not a phone number) and sends the most messages is likely the business. Flag this as lower confidence in the ParseQualityReport.

**Media Message Detection**

Messages that contain media indicators (in Spanish or English) must have their message_type set accordingly. The text content should be set to None for media-only messages, or preserved if the message has both text and a media indicator (e.g., a caption with an image).

Known media indicators must cover both Spanish and English WhatsApp variations, including: "imagen omitida", "image omitted", "<Media omitted>", "video omitido", "audio omitido", "sticker omitido", "documento omitido", "archivo omitido", "ubicación:", "location:", and file attachment patterns like ".jpg (file attached)".

### 8.3 Parse Quality Report

After parsing, generate a ParseQualityReport that includes:
- Counts: total lines, parsed messages, filtered system messages, merged continuation lines, empty lines, unparseable lines
- Samples of unparseable lines (first 5) for debugging
- List of unique senders found
- Which sender was detected as the business
- Which senders were detected as customers
- Date range (first and last message timestamps)
- Message type distribution (how many text, image, audio, etc.)
- Direction distribution (how many inbound vs outbound)
- Confidence score (0.0 to 1.0): starts at 1.0, reduced by 0.1 for each warning condition found
- Warnings: list of issues like "Business auto-detected (no identifiers provided)", "High ratio of unparseable lines (>5%)", "Only one sender found (expected two)", "No outbound messages detected"

### 8.4 Meta Webhook Parser (Phase 2)

This parser handles structured JSON from Meta Cloud API webhooks. Three webhook types:

1. messages: Standard incoming customer messages. Map directly to NormalizedMessage with direction=INBOUND.
2. smb_message_echoes: Messages the business sends from their WhatsApp app. Map to NormalizedMessage with direction=OUTBOUND.
3. history: Historical messages from Coexistence sync. Contains threads with multiple messages. Map each thread to a NormalizedConversation.

Since this is structured JSON, no regex is needed. Direct field mapping with type checking. Parse errors should be rare but must be logged with the full webhook payload for debugging.

Webhook verification: The GET /webhook endpoint must handle Meta's verification challenge by echoing back the hub.challenge parameter when the hub.verify_token matches.

---

## 9. Analytics Core — Detailed Specification

### 9.1 AnalyticsEngine (Orchestrator)

The AnalyticsEngine class is the main entry point for analysis. It receives NormalizedConversation objects and an AIProvider, and returns ConversationAnalysisResult objects.

It orchestrates three sub-systems in sequence:
1. MetricsEngine — runs first, always, no external calls
2. AIAnalysisEngine — runs second, calls the AI provider
3. InsightsGenerator — runs last, combines results from 1 and 2

The engine has two main methods:
- analyze_conversation(conversation): Analyzes a single conversation
- analyze_batch(conversations, on_progress): Analyzes multiple conversations with progress callback

The engine must be stateless. It does not access the database directly. It receives data and returns results. The caller (pipeline.py or analysis_worker.py) handles storage.

### 9.2 MetricsEngine — Pure Math Calculations

All metric calculators are pure functions. They take a list of NormalizedMessage objects and return numbers. No AI, no database, no external calls.

**ResponseTimeCalculator**

Calculates how fast the business responds to customer messages.

Logic: Iterate through messages in chronological order. When an INBOUND message is found, record its timestamp. When the next OUTBOUND message is found after an INBOUND, calculate the difference in seconds. Collect all such response times.

Methods:
- average(messages) → float or None: Mean response time in seconds
- median(messages) → float or None: Median response time
- percentile_95(messages) → float or None: 95th percentile
- max_response_time(messages) → float or None: Slowest response
- unanswered_count(messages) → int: Customer messages that never got a business reply (the conversation ended with the customer's message)
- by_hour(messages) → dict[int, float]: Average response time grouped by hour of day (0-23). Useful for finding when the business is slow.

Edge cases:
- Consecutive INBOUND messages without OUTBOUND: only the first INBOUND starts the timer. The second INBOUND does not reset it — the business still hasn't replied.
- Consecutive OUTBOUND messages without INBOUND: ignore — the business is sending follow-ups, not responding.
- Single message conversation: return None for all response time metrics.
- Messages with identical timestamps: treat response time as 0 seconds.

**VolumeCalculator**

Counts messages and conversations.

Methods:
- total_messages(messages) → int
- by_direction(messages) → dict: {"inbound": N, "outbound": M}
- by_type(messages) → dict: {"text": N, "image": M, ...}
- by_date(messages) → dict[date, int]: Messages per calendar day
- messages_per_conversation(conversations) → float: Average messages per conversation

**ActivityCalculator**

Finds patterns in when messages are sent.

Methods:
- by_hour(messages) → dict[int, int]: Message count per hour (0-23)
- by_day_of_week(messages) → dict[str, int]: Message count per day name
- peak_hour(messages) → int: Hour with most messages
- quiet_hours(messages) → list[int]: Hours with zero or near-zero messages
- busiest_day(messages) → str: Day of week with most activity
- first_message_time(messages) → datetime: Earliest message
- last_message_time(messages) → datetime: Latest message
- conversation_duration_minutes(messages) → float: Time from first to last message

### 9.3 AI Analysis Engine

Takes a NormalizedConversation, formats it into readable text, sends it to the AI provider with a carefully engineered prompt, and parses the structured JSON response.

**Conversation Formatter**

Converts a NormalizedConversation into a text transcript that the AI can read:

```
[2025-01-11 10:39] CUSTOMER: ¡Hola! Me gustaría agendar una cita de valoración...
[2025-01-11 10:39] CUSTOMER: Limpieza facial Bnos días
[2025-01-11 10:59] BUSINESS: ¡Hola, buen día! Soy Valentina Ávila...
```

Rules for formatting:
- Use BUSINESS and CUSTOMER labels, not names or phones (protect privacy in AI calls)
- Include timestamps in ISO-like format
- Include text messages only (skip media-only messages, note them as "[Image]", "[Audio]", etc.)
- Truncate very long conversations to the last 100 messages to stay within AI token limits
- If truncated, prepend a note: "[Conversation truncated — showing last 100 of N messages]"

**Combined Analysis Prompt**

Use a single prompt that extracts all analysis fields at once. This is 5x cheaper and faster than separate calls for sentiment, topics, quality, etc.

The system prompt must instruct the AI to:
- Analyze from the business perspective (how well did the business handle this?)
- Return valid JSON only, no other text
- Use the exact field names and value types specified
- Be specific in reasoning (especially conversion_reason and sentiment_reason)
- Score quality considering all dimensions, not just tone

The expected JSON response structure:
```
{
  "sentiment": "positive|neutral|negative",
  "sentiment_score": -1.0 to 1.0,
  "sentiment_reason": "string",
  "primary_topic": "string",
  "secondary_topics": ["string"],
  "quality_score": 0.0 to 10.0,
  "quality_breakdown": {
    "helpfulness": 0.0 to 10.0,
    "tone": 0.0 to 10.0,
    "completeness": 0.0 to 10.0,
    "speed_perception": 0.0 to 10.0
  },
  "conversion_status": "converted|lost|pending|not_applicable",
  "conversion_reason": "string or null",
  "summary": "string (2-3 sentences)",
  "key_points": ["string"]
}
```

**Response Parser**

Parse the AI's JSON response into a typed Pydantic model. Handle edge cases:
- AI returns invalid JSON: retry once with a simplified prompt. If still invalid, log the raw response and mark the analysis as failed for this conversation.
- AI returns unexpected field values (e.g., sentiment = "very positive"): normalize to the closest valid value.
- AI returns missing fields: use defaults (sentiment = "neutral", quality_score = 5.0, etc.)
- AI returns extra fields: ignore them.

### 9.4 Insights Generator

Combines metrics and AI analysis results into actionable insights. This is rule-based logic, not AI.

**Health Score Calculator (0-100)**

Weighted formula:
- Response time score (25%): Based on average response time. Under 5 min = 100, under 15 min = 80, under 30 min = 60, under 1 hour = 40, under 2 hours = 20, over 2 hours = 0. Linear interpolation between thresholds.
- Sentiment score (25%): Percentage of positive conversations × 100. A business with 80% positive gets 80.
- Quality score (25%): Average quality_score across conversations, multiplied by 10 to get 0-100.
- Conversion score (25%): Percentage of conversations that converted (excluding not_applicable). If all applicable conversations converted = 100.

The health score must handle missing data gracefully. If no conversations have sentiment analysis yet (AI hasn't run), that component gets a neutral 50 and the weight is redistributed.

**Recommendation Engine**

Generate 3-5 specific, actionable recommendations based on the analysis results. Rules:

- If avg_response_time > 30 minutes: "Tu tiempo promedio de respuesta es {X}. Los clientes esperan respuesta en menos de 15 minutos. Considera configurar respuestas automáticas para las preguntas más frecuentes."
- If unanswered_count > 0: "Tienes {N} mensajes de clientes sin responder. Cada mensaje sin respuesta es una venta potencial perdida."
- If negative_sentiment_percent > 20%: "El {X}% de tus conversaciones tienen sentimiento negativo. Los temas principales de insatisfacción son: {topics}."
- If a single topic dominates (>40% of conversations): "El {X}% de tus clientes preguntan sobre {topic}. Considera crear una respuesta rápida o un catálogo con esta información."
- If response time varies significantly by hour: "Respondes más lento entre las {hour1} y {hour2}. Considera asignar a alguien para cubrir ese horario."
- If lost_count > 20% of applicable conversations: "Estás perdiendo {X}% de los leads. Las principales razones son: {reasons}."
- If quality_score < 6 average: "La calidad promedio de tus respuestas es {X}/10. Las áreas de mejora son: {lowest_quality_dimensions}."

Recommendations must be in Spanish for LATAM market.

**Alert Generator**

Detect situations that need immediate attention:
- Response time spike: average for the current period is >50% higher than the previous period
- Negative sentiment spike: more than 3 consecutive negative conversations
- Unanswered messages: any message older than 4 hours without a response
- Quality drop: quality score drops below 4.0 for any conversation

---

## 10. AI Provider Abstraction — Detailed Specification

### Abstract Interface (AIProvider)

An abstract base class that all providers must implement. Methods:

- analyze(system_prompt: str, user_prompt: str, temperature: float, max_tokens: int, response_format: str) → AIResponse
  - temperature default: 0.3 (low creativity, more consistent)
  - max_tokens default: 2000
  - response_format: "json" or "text"
  - Must return an AIResponse object regardless of provider

- analyze_batch(prompts: list[dict], temperature: float) → list[AIResponse]
  - Each dict has "system" and "user" keys
  - Default implementation: sequential calls to analyze(). Providers can override with native batch APIs.

- estimate_cost(input_tokens: int, output_tokens: int) → float
  - Returns estimated cost in USD based on the provider's pricing

- provider_name property → str
- model_name property → str

### AIResponse Model

- content: str (the AI's response text)
- model: str (model identifier used)
- provider: str (provider name)
- tokens_input: int
- tokens_output: int
- cost_usd: float (estimated cost)

### OpenAI Provider

Uses the openai Python SDK with async client. Supports models: gpt-4o-mini (default, cheapest), gpt-4o (higher quality). When response_format is "json", pass response_format={"type": "json_object"} to the API. Track token usage from response.usage. Calculate cost based on per-million-token pricing for the specific model.

### Anthropic Provider

Uses the anthropic Python SDK with async client. Supports models: claude-haiku-4-5-20251001 (cheapest), claude-sonnet-4-20250514 (higher quality). The system prompt goes in the system parameter, not in messages. There is no native JSON mode — instruct JSON output in the system prompt and parse the response. Track token usage from response.usage. Calculate cost based on per-million-token pricing.

### Mock Provider (for testing)

Returns deterministic, realistic-looking responses without making any API calls. Used in tests and development. Always returns the same analysis for the same input (hash-based). Cost is always 0. This provider must produce valid JSON that matches the expected schema so downstream code can be tested without API keys.

### Provider Factory

A function that reads AI_PROVIDER and AI_MODEL from settings and returns the appropriate provider instance. Raises a clear error if the provider is unknown or if the required API key is missing.

---

## 11. Delivery Layer — Detailed Specification

### 11.1 PDF Report Generator

Takes analysis results for a client's batch of conversations and produces a branded PDF report.

Technology: Jinja2 HTML templates rendered to PDF with WeasyPrint. Charts generated with matplotlib and embedded as base64 images in the HTML.

**Report sections:**

1. Cover page: DeepLook logo, client business name, analysis period, generation date
2. Executive summary: Health score (large number, color-coded), total conversations analyzed, key headline metrics (avg response time, sentiment split, conversion rate)
3. Response time analysis: Average, median, P95. Chart showing response times by hour of day. List of slowest responses.
4. Sentiment analysis: Pie chart (positive/neutral/negative split). Trend if multi-day data available. Top 3 most negative conversations with summaries.
5. Topic analysis: Bar chart of top 10 topics. For each top topic, count and example summary.
6. Conversation quality: Average quality score. Breakdown by dimension (helpfulness, tone, completeness, speed perception). Lowest-scoring conversations with summaries.
7. Conversion analysis: Conversion rate. Lost lead count. Top reasons for lost leads. Example lost lead conversations with summaries.
8. Recommendations: 3-5 actionable recommendations from the InsightsGenerator.
9. Appendix: ParseQualityReport summary, data period, files processed count, AI model used, disclaimer.

**Chart generation:**

Use matplotlib with a clean, professional style. Color palette: teal (#0F6E56, #1D9E75, #5DCAA5) for positive/main data, coral (#D85A30) for negative/alert data, gray (#888780) for neutral. No gridlines. Clean sans-serif font. Export charts as PNG at 200 DPI, embed in HTML as base64 data URIs.

Charts needed:
- Sentiment pie chart
- Response time by hour bar chart
- Topics horizontal bar chart
- Quality breakdown radar/spider chart (or horizontal bars if radar is complex)
- Messages per day line chart (if multi-day data)

### 11.2 Report Download Endpoint

Path: GET /api/v1/reports/{job_id}/download
Returns: PDF file as application/pdf
Tags: Delivery

The report is generated on-demand when first requested, then cached. Subsequent requests return the cached version. Reports are stored in Supabase Storage or local filesystem.

### 11.3 Dashboard API (Phase 2 — endpoint stubs only in MVP)

Define the endpoint signatures and response schemas now, but implement them in Phase 2. This way the Swagger documentation shows the full API surface.

Endpoints:
- GET /api/v1/dashboard/overview — summary stats for a client
- GET /api/v1/dashboard/sentiment?period=7d|30d|90d — sentiment over time
- GET /api/v1/dashboard/response-times?period=7d|30d|90d — response time trends
- GET /api/v1/dashboard/topics?period=7d|30d|90d — topic breakdown
- GET /api/v1/dashboard/conversations?status=lost|converted|all — conversation list with filters
- GET /api/v1/dashboard/alerts — active alerts

---

## 12. API Endpoints — Full Specification

All endpoints are prefixed with /api/v1. Swagger UI is available at /docs. ReDoc is available at /redoc.

### Health

| Method | Path | Description | Tags |
|--------|------|-------------|------|
| GET | /health | Returns app status and version | System |

Response: {"status": "ok", "version": "1.0.0", "ai_provider": "openai", "ai_model": "gpt-4o-mini"}

### Clients

| Method | Path | Description | Tags |
|--------|------|-------------|------|
| POST | /api/v1/clients | Create a new client | Clients |
| GET | /api/v1/clients | List all clients | Clients |
| GET | /api/v1/clients/{id} | Get client details | Clients |
| PATCH | /api/v1/clients/{id} | Update client | Clients |
| DELETE | /api/v1/clients/{id} | Soft-delete client | Clients |

### Ingestion

| Method | Path | Description | Tags |
|--------|------|-------------|------|
| POST | /api/v1/upload | Upload .txt files for analysis | Ingestion |
| POST | /api/v1/webhook | Meta Cloud API webhook receiver (Phase 2) | Ingestion |
| GET | /api/v1/webhook | Meta webhook verification (Phase 2) | Ingestion |

### Analytics

| Method | Path | Description | Tags |
|--------|------|-------------|------|
| GET | /api/v1/jobs/{job_id} | Get analysis job status | Analytics |
| GET | /api/v1/jobs/{job_id}/results | Get full analysis results | Analytics |
| POST | /api/v1/analyze/{conversation_id} | Re-analyze a single conversation | Analytics |

### Delivery

| Method | Path | Description | Tags |
|--------|------|-------------|------|
| GET | /api/v1/reports/{job_id}/download | Download PDF report | Delivery |
| GET | /api/v1/reports/{job_id}/status | Check if report is ready | Delivery |
| GET | /api/v1/dashboard/overview | Dashboard summary (Phase 2) | Dashboard |
| GET | /api/v1/dashboard/sentiment | Sentiment over time (Phase 2) | Dashboard |
| GET | /api/v1/dashboard/response-times | Response times (Phase 2) | Dashboard |
| GET | /api/v1/dashboard/topics | Topic breakdown (Phase 2) | Dashboard |
| GET | /api/v1/dashboard/conversations | Conversation list (Phase 2) | Dashboard |

---

## 13. Background Processing

Analysis is CPU and API-call intensive. It must not block the upload endpoint.

### Flow:
1. Upload endpoint receives files, parses them, stores in DB, creates an analysis_job with status "pending"
2. Upload endpoint queues a background task and returns immediately with the job_id
3. Background worker picks up the job, sets status to "processing"
4. Worker iterates through conversations, calling AnalyticsEngine.analyze_conversation() for each
5. After each conversation, worker updates processed_conversations count and stores the ConversationAnalysisResult in the conversation_analysis table
6. When all conversations are done, worker computes daily_metrics aggregates
7. Worker sets job status to "completed"
8. If any error occurs, worker sets status to "failed" with the error_message

### MVP Implementation:
Use FastAPI's BackgroundTasks. This runs in the same process as the web server. Simple but sufficient for MVP volumes (< 100 conversations per batch).

### Rate Limiting:
AI providers have rate limits. The worker must respect them:
- OpenAI: default 500 RPM for gpt-4o-mini. Add a 150ms delay between calls to stay under limit.
- Anthropic: default 50 RPM for Claude. Add a 1.5s delay between calls.
- Make the delay configurable per provider in settings.

### Failure Handling:
- If a single conversation analysis fails (AI returns garbage, API error), log the error, mark that conversation as failed, continue with the next one. Do not fail the entire job.
- If the AI API is down (HTTP 500, timeout), retry up to 3 times with exponential backoff (2s, 4s, 8s). If still failing, mark the job as failed.
- Store partial results. If 80 of 100 conversations were analyzed before failure, those 80 results are still valuable.

---

## 14. Error Handling Strategy

### Custom Exception Classes

- ParseError: Raised when a file cannot be parsed. Contains: filename, line_number (if applicable), reason.
- ValidationError: Raised for invalid input. Contains: field, reason.
- AIProviderError: Raised when the AI provider fails. Contains: provider, model, status_code, message.
- AnalysisError: Raised when analysis fails. Contains: conversation_id, reason.
- ReportGenerationError: Raised when PDF generation fails.

### Global Exception Handler

FastAPI exception handlers that convert custom exceptions into appropriate HTTP responses:
- ParseError → 422 with details
- ValidationError → 400 with details
- AIProviderError → 502 with retry-after header
- AnalysisError → 500 with job_id for reference
- Generic Exception → 500 with a generic message (never expose internal details)

All errors must be logged with full context (request ID, client ID, stack trace) using Python's logging module.

---

## 15. Testing Strategy

### Unit Tests

Every module in the analytics core and ingestion layer must have unit tests. Target: 90% coverage on these modules.

Parser tests are the most critical. Each test function should test one specific behavior with a focused input. Use the sample .txt files in tests/fixtures/.

Test categories:
- Timestamp parsing: one test per format variation (Spanish AM/PM with spaces, English AM/PM, 24h, iOS brackets, 2-digit year, 4-digit year)
- Line classification: test each LineType with real examples
- Multi-line message assembly: verify that continuation lines are correctly merged
- System message filtering: verify that all known system message patterns are excluded
- Business direction detection: test with name match, phone match, auto-detection
- Media detection: test each media indicator in Spanish and English
- Response time calculation: test with various message patterns, edge cases
- Edge cases: empty file, single message file, file with only system messages, file with no business messages

### Integration Tests

Test the full pipeline from upload to analysis results. Use the mock AI provider to avoid real API calls. Verify that:
- Uploading a file returns a valid job_id
- Job status progresses from pending to processing to completed
- Analysis results contain all expected fields
- PDF report is generated and downloadable
- Multiple file upload creates multiple conversations

### Test Fixtures

Create realistic test fixture files based on the real sample data provided. Include:
- A minimal conversation (3 messages)
- A typical conversation (20-30 messages with media indicators)
- A multi-line message conversation (service descriptions with bullet points)
- A conversation with system messages mixed in
- The exact format from the Wellness By Diego Omar sample

---

## 16. Deployment & Infrastructure

### Local Development

Use docker-compose with:
- App service: Python 3.12, FastAPI on port 8000
- The database is hosted on Supabase (no local DB container needed)

Run with: uvicorn app.main:app --reload --port 8000

### Production Deployment

Options (in order of simplicity):
1. Railway.app — simplest, supports Python, auto-deploys from GitHub
2. Render.com — similar to Railway, free tier available
3. DigitalOcean App Platform — more control, slightly more complex
4. VPS with Docker — most control, most complex

Required production configuration:
- HTTPS (provided by the platform)
- Environment variables set in platform dashboard (never in code)
- At least 512MB RAM (WeasyPrint needs memory for PDF generation)
- Persistent storage for generated reports (use Supabase Storage)

### Supabase Setup

1. Create a Supabase project
2. Get the database connection string (Settings → Database → Connection string → URI)
3. Use the asyncpg connection string format: postgresql+asyncpg://...
4. Run Alembic migrations to create tables
5. Enable Row Level Security on all tables (configure policies as needed)
6. Create a storage bucket "reports" for PDF files

---

## 17. Build Order (Sprint Plan)

### Sprint 1 (Days 1-5): Foundation

Day 1: Project scaffold
- Initialize project with pyproject.toml
- Install all dependencies
- Create config.py with Settings class
- Create main.py with FastAPI app, CORS, /health endpoint
- Verify Swagger UI works at /docs
- Create .env.example

Day 2: Database setup
- Create Supabase project
- Create all SQLAlchemy models in models/database.py
- Set up Alembic and create initial migration
- Run migration to create all tables
- Create base repository with common CRUD operations
- Test database connectivity

Day 3: Pydantic schemas + Normalized models
- Create all enums in enums.py
- Create NormalizedMessage, NormalizedConversation, NormalizedBatch in normalized.py
- Create all API request/response schemas in schemas.py
- Create ParseQualityReport model

Day 4-5: WhatsApp .txt parser
- Create txt_timestamp.py with all format handlers
- Create txt_classifier.py (Pass 1)
- Create txt_system.py with system message indicators
- Create txt_assembler.py (Pass 2)
- Create txt_direction.py for business/customer detection
- Create txt_media.py for media message detection
- Create txt_parser.py that orchestrates all components
- Create quality.py for ParseQualityReport generation
- Write unit tests for each component
- Test with real sample data

### Sprint 2 (Days 6-12): Analytics Core

Day 6-7: Metrics engine
- Create response_time.py calculator
- Create volume.py calculator
- Create activity.py calculator
- Write unit tests for all calculators

Day 8-9: AI provider abstraction
- Create AIProvider abstract class and AIResponse model
- Implement OpenAI provider
- Implement Anthropic provider
- Implement Mock provider
- Create provider factory
- Write tests (using mock provider)

Day 10-11: AI analysis
- Create conversation formatter
- Create combined analysis prompt
- Create response parser with error handling
- Create cost tracker
- Wire into AnalyticsEngine
- Test with real conversations (using real AI calls)

Day 12: Insights generator
- Create health score calculator
- Create recommendation engine
- Create alert generator
- Write tests

### Sprint 3 (Days 13-17): Upload + Report + End-to-End

Day 13: Upload endpoint
- Create ingestion router with POST /upload
- Handle single and multiple file uploads
- Wire parser → database storage → job creation
- Write integration tests

Day 14-15: PDF report
- Create HTML report template with Jinja2
- Create chart generator (matplotlib)
- Create PDF generator (WeasyPrint)
- Create report download endpoint
- Test with real analysis results

Day 16: Background processing
- Create analysis worker
- Wire upload → background task → analysis → results
- Create job status endpoint
- Test end-to-end flow

Day 17: Integration testing + polish
- Test complete flow: upload → parse → analyze → report download
- Fix edge cases found during testing
- Clean up Swagger documentation
- Update README

### Sprint 4 (Days 18-22): Deploy + First Clients

Day 18-19: Deployment
- Create Dockerfile
- Deploy to Railway or Render
- Configure environment variables
- Test in production

Day 20-22: First clients
- Create a simple landing page
- Test with 3-5 real businesses
- Collect feedback
- Iterate on report content and recommendations
