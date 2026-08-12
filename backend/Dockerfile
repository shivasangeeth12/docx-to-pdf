# ============================================================
# Backend Dockerfile - DOCX to PDF Converter
# Multi-stage production build
# ============================================================


# ============================================================
# Stage 1: Builder
# ============================================================

FROM python:3.11-slim AS builder

WORKDIR /app

# System packages required to build Python dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy Python dependencies
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt


# ============================================================
# Stage 2: Production
# ============================================================

FROM python:3.11-slim AS production

WORKDIR /app


# ============================================================
# Install runtime system dependencies
# ============================================================

RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice \
    libreoffice-writer \
    poppler-utils \
    ghostscript \
    libmagic1 \
    wget \
    && rm -rf /var/lib/apt/lists/*


# ============================================================
# Copy Python dependencies from builder
# ============================================================

COPY --from=builder /root/.local /root/.local


# ============================================================
# Copy backend application
# ============================================================

COPY . .


# ============================================================
# Create application directories
# ============================================================

RUN mkdir -p \
    uploads \
    outputs \
    temp


# ============================================================
# Python PATH
# ============================================================

ENV PATH=/root/.local/bin:$PATH


# ============================================================
# Python settings
# ============================================================

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1


# ============================================================
# Expose FastAPI port
# ============================================================

EXPOSE 8000


# ============================================================
# Health Check
# ============================================================

HEALTHCHECK \
    --interval=30s \
    --timeout=10s \
    --start-period=40s \
    --retries=3 \
    CMD wget \
    --no-verbose \
    --tries=1 \
    --spider \
    http://localhost:8000/health \
    || exit 1


# ============================================================
# Start FastAPI application
# ============================================================

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
