# ── Stage 1: build wheels ────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build-time system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Build all wheels into /wheels.
# PyTorch CPU-only wheel is fetched from the official CPU index.
RUN pip wheel --no-cache-dir --wheel-dir /wheels \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        -r requirements.txt

# ── Stage 2: runtime image ───────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Install runtime system dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
        tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Copy pre-built wheels and requirements from builder, then install offline
COPY --from=builder /wheels /wheels
COPY --from=builder /build/requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links /wheels -r requirements.txt \
    && rm -rf /wheels

# Remove test/doc/example bloat from installed packages
RUN find /usr/local/lib/python3.11/site-packages -type d \
        \( -name "tests" -o -name "test" -o -name "docs" -o -name "examples" -o -name "__pycache__" \) \
        -exec rm -rf {} + 2>/dev/null || true

COPY . /app/backend

ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
