# ============================================================
# Stage 1 - Build frontend
# ============================================================

FROM node:20-bookworm-slim AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package*.json ./

RUN npm ci

COPY frontend/ .

RUN npm run build


# ============================================================
# Stage 2 - Production
# ============================================================

FROM python:3.11-slim-bookworm AS production

WORKDIR /app

# ============================================================
# Install system dependencies
# ============================================================

RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    libreoffice \
    libreoffice-writer \
    poppler-utils \
    ghostscript \
    libmagic1 \
    wget \
    && rm -rf /var/lib/apt/lists/*


# ============================================================
# Python dependencies
# ============================================================

COPY backend/requirements.txt /app/requirements.txt

RUN pip install \
    --no-cache-dir \
    -r /app/requirements.txt


# ============================================================
# Backend
# ============================================================

COPY backend/ /app/backend/


# ============================================================
# Frontend
# ============================================================

COPY --from=frontend-builder \
    /app/frontend/dist \
    /usr/share/nginx/html


# ============================================================
# Nginx
# ============================================================

COPY nginx.conf \
    /etc/nginx/conf.d/default.conf


# Remove default nginx config if necessary
RUN rm -f /etc/nginx/sites-enabled/default


# ============================================================
# Application directories
# ============================================================

RUN mkdir -p \
    /app/backend/uploads \
    /app/backend/outputs \
    /app/backend/temp


# ============================================================
# Environment
# ============================================================

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV LIBREOFFICE_PATH=/usr/bin/libreoffice


# ============================================================
# Startup script
# ============================================================

RUN printf '#!/bin/sh\n\
set -e\n\
\n\
cd /app/backend\n\
\n\
uvicorn main:app --host 0.0.0.0 --port 8000 &\n\
\n\
exec nginx -g "daemon off;"\n' > /start.sh \
    && chmod +x /start.sh


# ============================================================
# Port
# ============================================================

EXPOSE 80


# ============================================================
# Health check
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
    http://localhost/health \
    || exit 1


# ============================================================
# Start
# ============================================================

CMD ["/start.sh"]
