FROM python:3.12-slim

# ── System dependencies ────────────────────────────────────────────────────
# WeasyPrint needs Pango, Cairo, Harfbuzz and font packages.
# Without fonts-dejavu and fontconfig, PDFs render with blank/missing text.
# Without libharfbuzz0b, Pango crashes on startup with newer versions.
# libopenjp2-7 is needed by Pillow (used internally by WeasyPrint).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz0b \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    libjpeg-dev \
    libopenjp2-7 \
    fontconfig \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# ── Environment ────────────────────────────────────────────────────────────
# Agg = non-interactive backend. Without this, matplotlib tries to open a
# GUI display on a headless server and the first chart generation crashes.
ENV MPLBACKEND=Agg \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# ── Python dependencies (cached layer) ────────────────────────────────────
# Copy requirements first so Docker caches this expensive layer separately
# from the source code. Only rebuilt when requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Application source ─────────────────────────────────────────────────────
COPY . .

# Install the app package itself (non-editable, no deps reinstalled).
# --no-deps: deps already installed above, avoid redundant resolution.
RUN pip install --no-cache-dir --no-deps .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
