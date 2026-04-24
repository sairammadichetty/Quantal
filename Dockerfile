# syntax=docker/dockerfile:1.6

# --- Builder ----------------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /build

# Some transitive deps occasionally need a C compiler on certain arches.
# Drop these three lines if you're sure you don't.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# --- Runtime ----------------------------------------------------------------
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY --from=builder /install /usr/local

# Non-root service account (defence in depth).
RUN adduser --system --group --no-create-home orbitaluser

# Copy source last so dependency layers stay cached on source-only changes.
COPY ./app /app/app

USER orbitaluser

EXPOSE 8000

# stdlib-only health probe, no curl dependency in the image.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request, sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
