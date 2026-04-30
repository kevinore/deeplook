FROM python:3.12-slim

# ── System runtime dependencies ────────────────────────────────────────────
# WeasyPrint needs Pango, Cairo, Harfbuzz + real fonts at RUNTIME.
# Key packages:
#   fonts-dejavu-core  → actual fonts; without this PDFs have blank text
#   libharfbuzz0b      → text shaping required by Pango on Bookworm
#   libffi8            → runtime libffi (cffi/cryptography need this)
#   libjpeg62-turbo    → JPEG runtime (WeasyPrint/Pillow image support)
#   libopenjp2-7       → JPEG2000 support for embedded images in PDFs
# Using runtime libs (not -dev) keeps the image ~20 MB smaller.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz0b \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi8 \
    libjpeg62-turbo \
    libopenjp2-7 \
    fontconfig \
    fonts-dejavu-core \
    fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -fv

# ── Environment ────────────────────────────────────────────────────────────
# Agg = headless matplotlib backend (no GUI/display server needed).
# PYTHONUNBUFFERED = logs appear immediately in Coolify without buffering.
# PYTHONDONTWRITEBYTECODE = no .pyc clutter in the container filesystem.
ENV MPLBACKEND=Agg \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# ── Python dependencies (cached layer) ────────────────────────────────────
# Copy requirements first → Docker caches this expensive layer separately.
# Rebuilt only when requirements.txt changes, not on every code change.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Application source ─────────────────────────────────────────────────────
COPY . .

# Install the app package itself without reinstalling its dependencies.
RUN pip install --no-cache-dir --no-deps .

# ── Non-root user (security best practice) ────────────────────────────────
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
