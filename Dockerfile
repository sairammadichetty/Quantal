# syntax=docker/dockerfile:1.6

# --- Stage 1: Build dependencies --------------------------------------------
# We install into an isolated prefix so the runtime stage only carries the
# packages themselves, not pip/wheel/cache bloat.
FROM python:3.11-slim AS builder

WORKDIR /build

# `build-essential` is kept because some transitive deps occasionally need a
# C compiler on certain arches. If you're confident you won't need it you can
# drop these three lines to shrink the builder image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# --- Stage 2: Final runtime --------------------------------------------------
FROM python:3.11-slim

# Runtime hygiene:
#   - No .pyc cache
#   - Unbuffered stdout/stderr so container logs stream immediately
#   - PYTHONPATH includes the app so `uvicorn app.main:app` resolves
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Bring in the installed packages from the builder stage.
COPY --from=builder /install /usr/local

# Create a non-root user (defence in depth). --system on Debian avoids
# creating /home for a service account we'll never log in as.
RUN adduser --system --group --no-create-home orbitaluser

# Copy application source last so dependency layers stay cached across
# source-only changes.
COPY ./app /app/app

USER orbitaluser

EXPOSE 8000

# Simple health probe so orchestrators can restart unhealthy containers.
# Uses the Python stdlib (no curl dependency) to hit /healthz.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request, sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
