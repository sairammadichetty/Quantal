# --- Stage 1: Build dependencies ---
    FROM python:3.11-slim as builder

    WORKDIR /build
    
    # Install build essentials if you have any C-based dependencies
    RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        && rm -rf /var/lib/apt/lists/*
    
    # Install dependencies to a local folder
    COPY requirements.txt .
    RUN pip install --no-cache-dir --prefix=/install -r requirements.txt
    
    # --- Stage 2: Final Runtime ---
    FROM python:3.11-slim
    
    WORKDIR /app
    
    # Copy only the installed packages from the builder stage
    COPY --from=builder /install /usr/local
    
    # Create a non-privileged user for security (Production best practice)
    RUN adduser --disabled-password --gecos '' orbitaluser
    USER orbitaluser
    
    # Copy application code
    COPY ./app /app/app
    
    # Set environment variables
    ENV PYTHONDONTWRITEBYTECODE=1
    ENV PYTHONUNBUFFERED=1
    ENV PYTHONPATH=/app
    
    # Expose the port FastAPI runs on
    EXPOSE 8000
    
    # Run the application using uvicorn
    CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
    