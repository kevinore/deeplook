# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

This project is currently **specification-only**. The sole file is `deeplook-complete-technical-spec.md`, which contains the full implementation blueprint. No source code exists yet. Implementation should strictly follow the spec.

## Project Overview

DeepLook is a WhatsApp Business conversation analytics SaaS. Businesses upload `.txt` chat exports → the system parses, analyzes, and generates a PDF report with response times, sentiment, quality scores, lost sales, and recommendations.

## Commands

Once `pyproject.toml` and source code are created (per the spec):

```bash
# Install
pip install -e ".[dev]"

# Run dev server
uvicorn app.main:app --reload --port 8000

# Database migrations
alembic upgrade head

# Tests
pytest tests/ -v --cov=app --cov-report=html

# Run a single test file
pytest tests/test_ingestion/test_parser.py -v

# Lint & format
ruff check app/
ruff format app/

# Type check
mypy app/
```

API docs are at `/docs` (Swagger) and `/redoc` once the server is running.

## Architecture

Four strictly-layered pipeline — data flows downward, no layer knows about layers above it:

```
Ingestion → Persistence → Analytics Core → Delivery
```

**Layer 1 — Ingestion** (`app/ingestion/`): Parses `.txt` WhatsApp exports into `NormalizedBatch → NormalizedConversation → NormalizedMessage` objects. Two-pass regex approach (classify lines, then assemble messages). Handles 7 timestamp formats, 50+ system message patterns in Spanish/English. **No AI in parsing — deterministic regex only.**

**Layer 2 — Persistence** (`app/repositories/`): Supabase PostgreSQL via SQLAlchemy 2.0 async. All DB access through repository classes — no direct queries in route handlers or analytics code. 7 tables: `clients`, `contacts`, `conversations`, `messages`, `analysis_jobs`, `conversation_analysis`, `daily_metrics`.

**Layer 3 — Analytics Core** (`app/analytics/`): Three sub-components:
- `MetricsEngine`: Pure math, no AI, no external calls (response times, volumes, patterns)
- `AIAnalysisEngine`: Multi-provider abstraction (OpenAI, Anthropic, Gemini, Mistral) — switching providers is a config change, not a code change
- `InsightsGenerator`: Rule-based health score (0–100) + recommendations, no AI

**Layer 4 — Delivery** (`app/delivery/`): WeasyPrint + Jinja2 HTML templates → PDF reports. Matplotlib charts embedded as base64.

## Key Constraints from the Spec

- Analytics core is **completely independent of the data source** — it only processes `NormalizedMessage` objects
- AI provider is selected via `AI_PROVIDER` env var; all providers implement the same abstract interface
- Background job processing uses `FastAPI BackgroundTasks` for MVP (Celery upgrade path defined)
- Each `.txt` file = one conversation thread

## Environment Variables

Copy `.env.example` → `.env`. Required at minimum:

```
DATABASE_URL=postgresql+asyncpg://...
AI_PROVIDER=openai          # or: anthropic
AI_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...       # or ANTHROPIC_API_KEY
API_SECRET_KEY=<32-char-random>
```

## API Structure

All routes under `/api/v1`:
- `POST /upload` — file upload, triggers background analysis job
- `GET /jobs/{job_id}` — job status
- `GET /jobs/{job_id}/results` — analysis results
- `GET /reports/{job_id}/download` — PDF download
- CRUD under `/clients/`
