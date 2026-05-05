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

## Trial codes

Single-use codes that grant a client a temporary `basic` plan without going through Wompi. Each client can redeem at most one code (lifetime), and each code can be claimed by at most one client.

The user redeems via the **"¿Tienes un código de prueba?"** card inside the Plan Selection modal in the dashboard.

### Mint codes

```bash
# 5 random codes (e.g. K7N3MX9PQR), 30-day basic trial
.venv/bin/python scripts/gen_trial_codes.py 5

# A specific memorable code
.venv/bin/python scripts/gen_trial_codes.py --code DEEPLOOK-VIP

# 10 codes for a campaign — tagged for easy filtering later
.venv/bin/python scripts/gen_trial_codes.py 10 --note "Lanzamiento mayo"

# A 60-day plus-plan trial
.venv/bin/python scripts/gen_trial_codes.py --code FRIENDS-VIP --plan plus --days 60
```

### Flags

| Flag              | Default      | Purpose                                                                              |
| ----------------- | ------------ | ------------------------------------------------------------------------------------ |
| `--days`          | 30           | Trial duration **after redemption** — how long the user keeps the plan               |
| `--valid-for-days`| same as `--days` | **Redemption window** — how long the code itself can be redeemed for. `0` = never expires |
| `--plan`          | basic        | Plan granted (`basic` / `plus` / `enterprise`)                                       |
| `--note`          | none         | Internal label (e.g. campaign name) — never user-facing                              |
| `--code`          | random       | Mint exactly this code instead of random (count is ignored)                          |
| `--length`        | 10           | Length of random codes                                                                |

**Two clocks per code, don't confuse them:**
- `--valid-for-days` is when the code stops being redeemable (after this, no one can redeem it).
- `--days` is how long the user keeps the trial plan after they redeem.

Example: `--days 15 --valid-for-days 7` mints a code that must be redeemed within 7 days, and once redeemed gives 15 days of access.

### What happens on redemption

`POST /api/v1/billing/redeem-trial` does (in one transaction):

1. Atomically claims the code (`is_active=true` + `redeemed_by_client_id IS NULL`).
2. Sets the client's `plan`, `plan_started_at=now`, `plan_expires_at=now+duration_days`, `subscription_status='trial'`, `trial_redeemed_at=now`.

When the period ends, `enforce_expiry()` downgrades the client back to `free` automatically — no separate cleanup job needed.

### Inspect / revoke codes

```sql
-- List unredeemed codes for a campaign
SELECT code, plan, duration_days, created_at FROM trial_codes
WHERE redeemed_by_client_id IS NULL AND note = 'Lanzamiento mayo';

-- Disable a leaked code
UPDATE trial_codes SET is_active = false WHERE code = 'LEAKED-CODE';
```

---

## Analytics with Metabase

Self-hosted Metabase service in `docker-compose.yml` for tracking platform growth — signups, paid plans, revenue, AI costs, etc. — all powered by your existing Supabase data.

### Start Metabase

```bash
docker compose up -d metabase
# Then open http://localhost:3001
```

The container stores its dashboards in a Docker volume (`metabase-data`), so they persist across restarts. First boot takes ~1 min while it initializes its embedded H2 database.

### Connect Metabase to Supabase

In the first-run wizard:

- **Database type:** PostgreSQL
- **Host:** `db.YOUR_PROJECT_REF.supabase.co` (use the **direct** host, not the pooler — Metabase's connection pool breaks against pgbouncer's transaction mode)
- **Port:** `5432`
- **Database name:** `postgres`
- **Username:** `postgres`
- **Password:** your Supabase DB password
- **SSL:** required (set `sslmode=require` under "Advanced options" if asked)

Metabase will scan the schema and you're ready to write Questions.

### Ready-to-paste queries

All SQL Questions for the dashboard live in [`analytics/`](analytics/), grouped by topic:

| File                            | Covers                                                                |
| ------------------------------- | --------------------------------------------------------------------- |
| [`analytics/growth.sql`](analytics/growth.sql)             | Active clients, signups/day, plan distribution, onboarding funnel     |
| [`analytics/revenue.sql`](analytics/revenue.sql)           | Lifetime revenue, monthly revenue, MRR, conversion %, failed payments |
| [`analytics/product_usage.sql`](analytics/product_usage.sql) | Reports generated, AI cost vs revenue, WhatsApp health                |
| [`analytics/trial_codes.sql`](analytics/trial_codes.sql)   | Codes minted/redeemed, per-campaign redemption rate, trial → paid     |
| [`analytics/churn.sql`](analytics/churn.sql)               | Expired without renewal, winback list, cohort retention               |

Each query has a header comment explaining what it shows and which Metabase visualization fits best (Scalar, Line, Bar, etc.). See [`analytics/README.md`](analytics/README.md) for usage notes.

> **Tip:** Numeric/date fields render automatically — pick "line chart" for time-series queries and "scalar" for single-row metrics.

### Going further

- **Want it accessible from anywhere, not just localhost?** Move the same `metabase` service to a $5/mo VPS (Hetzner, Railway, Fly.io) and front it with a reverse proxy + auth. The dashboards and credentials live in the `metabase-data` volume, so back that volume up.
- **Concerned about resource use?** Metabase needs ~512MB RAM idle. Stop the container when not actively analyzing: `docker compose stop metabase`.

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
