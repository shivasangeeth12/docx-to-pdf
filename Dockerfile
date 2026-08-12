# Multi-stage build for DOCX to PDF Converter
# Stage 1: Backend with Python and LibreOffice
FROM python:3.11-slim as backend

# Install system dependencies for LibreOffice and file processing
RUN apt-get update && apt-get install -y \
    libreoffice \
    libreoffice-writer \
    poppler-utils \
    ghostscript \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# Stage 2: Frontend build
FROM node:20-alpine as frontend-builder

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ .
RUN npm run build

# Stage 3: Production with nginx
FROM nginx:alpine as production

# Install Python and dependencies for backend
RUN apk add --no-cache python3 py3-pip libreoffice libreoffice-writer poppler-utils ghostscript libmagic

# Copy backend from backend stage
COPY --from=backend /app/backend /app/backend
COPY --from=backend /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=backend /usr/local/bin/uvicorn /usr/local/bin/uvicorn

# Copy frontend build
COPY --from=frontend-builder /app/frontend/dist /usr/share/nginx/html

# Copy nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Create startup script
RUN echo '#!/bin/sh\n\
cd /app/backend\n\
uvicorn main:app --host 0.0.0.0 --port 8000 &\n\
nginx -g "daemon off;"\n' > /start.sh && chmod +x /start.sh

EXPOSE 80

CMD ["/start.sh"]