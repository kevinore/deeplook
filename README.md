# DeepLook

WhatsApp Business conversation analytics platform. Upload `.txt` chat exports → get a PDF report with response times, sentiment analysis, quality scores, and actionable recommendations.

## Prerequisites

- Python 3.12+
- A [Supabase](https://supabase.com) project (free tier works)
- An AI provider API key (OpenAI, Anthropic, or Google Gemini)

---

## Setup from Scratch

### 1. Clone and create a virtual environment

```bash
git clone <repo-url>
cd deeplook
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in the required values:

**Database (Supabase)**

Go to your Supabase project → **Settings → Database → Connection string**.

- `DATABASE_URL` — copy the **Session mode** pooler URI (port `5432` or `6543`). Change the scheme to `postgresql+asyncpg://`.
- `DIRECT_DATABASE_URL` — copy the **Direct connection** URI (host: `db.YOUR_PROJECT_REF.supabase.co`, port `5432`). Change the scheme to `postgresql+asyncpg://`.

> **Important:** If your database password contains special characters (e.g. `@`, `#`, `%`), URL-encode them:
> `@` → `%40`, `#` → `%23`, `%` → `%25`

Example:

```
DATABASE_URL=postgresql+asyncpg://postgres.projectref:MyP%40ssword@aws-0-us-east-1.pooler.supabase.com:6543/postgres
DIRECT_DATABASE_URL=postgresql+asyncpg://postgres:MyP%40ssword@db.projectref.supabase.co:5432/postgres
```

**AI Provider** — only the active one needs a key:

```
AI_PROVIDER=openai          # openai | anthropic | gemini | mock
AI_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
```

Use `mock` as the provider to run without any AI API key (returns dummy results).

### 4. Run database migrations

```bash
# Generate the initial migration from the SQLAlchemy models
alembic revision --autogenerate -m "initial_schema"

# Apply the migration to your database
alembic upgrade head
```

A successful run looks like:

```
INFO  [alembic.runtime.migration] Running upgrade  -> abc123, initial_schema
```

### 5. Start the server

```bash
uvicorn app.main:app --reload --port 8000
```

Swagger UI: http://localhost:8000/docs

---

## Core API Flow

1. `POST /api/v1/clients` — register a business client
2. `POST /api/v1/upload` — upload one or more WhatsApp `.txt` export files
3. `GET /api/v1/jobs/{job_id}` — poll analysis job status (`pending` → `processing` → `completed`)
4. `GET /api/v1/reports/{job_id}/download` — download the PDF report

---

## Development

```bash
# Run tests
pytest tests/ -v --cov=app

# Lint
ruff check app/

# Format
ruff format app/

# Type check
mypy app/
```

---

## Docker

```bash
docker-compose up
```

This starts the API and runs migrations automatically on container start.

---

## Environment Variables Reference

| Variable              | Required           | Description                                                       |
| --------------------- | ------------------ | ----------------------------------------------------------------- |
| `DATABASE_URL`        | Yes                | Supabase pooler URL (`postgresql+asyncpg://`)                     |
| `DIRECT_DATABASE_URL` | Yes (migrations)   | Supabase direct URL, used by Alembic                              |
| `SUPABASE_URL`        | Yes                | `https://YOUR_PROJECT_REF.supabase.co`                            |
| `SUPABASE_KEY`        | Yes                | Supabase `anon` public key                                        |
| `AI_PROVIDER`         | Yes                | `openai`, `anthropic`, `gemini`, or `mock`                        |
| `AI_MODEL`            | Yes                | e.g. `gpt-4o-mini`, `claude-3-haiku-20240307`, `gemini-2.0-flash` |
| `OPENAI_API_KEY`      | If using OpenAI    |                                                                   |
| `ANTHROPIC_API_KEY`   | If using Anthropic |                                                                   |
| `GEMINI_API_KEY`      | If using Gemini    |                                                                   |
| `API_SECRET_KEY`      | Yes                | Random 32-char string for internal signing                        |

See `.env.example` for all available variables.

---

## Deployment

Supported platforms: Railway, Render, DigitalOcean App Platform.

Minimum requirements: **512MB RAM** (WeasyPrint PDF generation is memory-intensive).

Set all environment variables from the table above in your platform's config. Run migrations as a one-off job before starting the server:

```bash
alembic upgrade head
```

const token = await window.Clerk.session.getToken();  
 console.log(token);
