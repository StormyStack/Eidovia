# ============================================================
# Stage 1: Build & Dependencies
# ============================================================
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build tools for compiling any C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip/setuptools/wheel in-place (no --prefix!)
RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel

# Install all packages from requirements.txt into isolated location
COPY requirements.txt .
RUN python -m pip install \
        --prefix=/install \
        --no-cache-dir \
        --timeout 1200 \
        --retries 10 \
        -r requirements.txt

# ============================================================
# Stage 2: Final Minimal Runtime
# ============================================================
FROM python:3.11-slim

WORKDIR /app

# Install curl for health check
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages directly from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/usr/local/bin:$PATH"

# Expose port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=20s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# Run the exact same command used locally
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]