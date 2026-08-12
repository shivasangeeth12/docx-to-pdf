# 🚀 Deployment Guide for DOCX to PDF Converter

This guide covers multiple deployment options for the DOCX to PDF Converter with File Compression.

## 📋 Prerequisites

- GitHub account
- Docker & Docker Compose (for containerized deployment)
- Node.js 20+ (for frontend development)
- Python 3.11+ (for backend development)

---

## 🌐 Option 1: GitHub Pages (Frontend Only) + External Backend

### Frontend Deployment to GitHub Pages

1. **Enable GitHub Pages:**
   - Go to your repository Settings → Pages
   - Source: "GitHub Actions"
   - Save

2. **Configure Repository Secrets:**
   - Go to Settings → Secrets and variables → Actions
   - Add `VITE_API_URL` with your backend URL (e.g., `https://your-backend.railway.app`)

3. **Deploy:**
   - Push to main branch
   - GitHub Actions will automatically build and deploy

### Backend Deployment Options

#### Railway (Recommended - Free tier available)
```bash
# 1. Install Railway CLI
npm install -g @railway/cli

# 2. Login and deploy
railway login
railway init
railway up
```

#### Render (Free tier available)
1. Connect GitHub repo to Render
2. Create Web Service
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add environment variables

#### Fly.io
```bash
# 1. Install flyctl
curl -L https://fly.io/install.sh | sh

# 2. Deploy
fly launch
fly deploy
```

#### DigitalOcean App Platform
1. Create new App from GitHub
2. Select backend directory
3. Configure build/run commands

---

## 🐳 Option 2: Full Docker Deployment (Recommended for Production)

### Using Docker Compose (Local/Server)

```bash
# 1. Clone repository
git clone https://github.com/yourusername/docx-pdf-converter.git
cd docx-pdf-converter

# 2. Create environment file
cp .env.example .env
# Edit .env with your settings

# 3. Deploy
docker-compose up -d --build

# 4. Access
# Frontend: http://localhost
# Backend API: http://localhost:8000
# API Docs: http://localhost:8000/docs
```

### Using GitHub Container Registry

1. **Enable GitHub Packages** in repository settings
2. **Push to registry:**
   ```bash
   # Login
   echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin
   
   # Build and push
   docker build -t ghcr.io/username/docx-pdf-converter .
   docker push ghcr.io/username/docx-pdf-converter
   ```

3. **Deploy from registry:**
   ```bash
   docker-compose -f docker-compose.prod.yml up -d
   ```

---

## ☁️ Option 3: Cloud Provider Deployment

### AWS (ECS/Fargate)
```bash
# 1. Build and push to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account>.dkr.ecr.us-east-1.amazonaws.com

docker build -t docx-pdf-converter .
docker tag docx-pdf-converter:latest <account>.dkr.ecr.us-east-1.amazonaws.com/docx-pdf-converter:latest
docker push <account>.dkr.ecr.us-east-1.amazonaws.com/docx-pdf-converter:latest

# 2. Create ECS service with task definition
```

### Google Cloud Run
```bash
# 1. Build and push
gcloud builds submit --tag gcr.io/PROJECT_ID/docx-pdf-converter

# 2. Deploy
gcloud run deploy --image gcr.io/PROJECT_ID/docx-pdf-converter --platform managed
```

### Azure Container Instances
```bash
# 1. Build and push to ACR
az acr build --registry myregistry --image docx-pdf-converter .

# 2. Deploy
az container create --resource-group myResourceGroup --name docx-pdf-converter --image myregistry.azurecr.io/docx-pdf-converter
```

---

## 🔧 Option 4: GitHub Codespaces (Development/Demo)

1. **Open in Codespaces:**
   - Click "Code" → "Codespaces" → "Create codespace on main"

2. **Auto-configuration:**
   - `.devcontainer/devcontainer.json` will set up everything
   - Ports 3000 (frontend) and 8000 (backend) auto-forwarded

3. **Access:**
   - Frontend: Forwarded port 3000
   - Backend: Forwarded port 8000

---

## 📦 Option 5: Kubernetes Deployment

### Using Helm (Create `helm-chart/` directory)

```yaml
# values.yaml
replicaCount: 2

frontend:
  image: ghcr.io/username/docx-pdf-converter-frontend:latest
  port: 80

backend:
  image: ghcr.io/username/docx-pdf-converter-backend:latest
  port: 8000
  env:
    - name: MAX_FILE_SIZE
      value: "52428800"

ingress:
  enabled: true
  hosts:
    - host: converter.yourdomain.com
      paths: ["/"]
```

```bash
helm install docx-pdf-converter ./helm-chart
```

---

## 🔐 Environment Variables

### Backend (.env)
```env
# Server
HOST=0.0.0.0
PORT=8000
WORKERS=4

# File Processing
MAX_FILE_SIZE=52428800
UPLOAD_DIR=/app/data/uploads
OUTPUT_DIR=/app/data/outputs
TEMP_DIR=/app/data/temp

# LibreOffice
LIBREOFFICE_PATH=/usr/bin/libreoffice
LIBREOFFICE_TIMEOUT=300

# Compression Settings
DEFAULT_IMAGE_QUALITY=85
DEFAULT_PDF_DPI=150
MAX_CONCURRENT_JOBS=4

# Security
SECRET_KEY=your-secret-key-here
CORS_ORIGINS=["https://yourdomain.com"]

# Logging
LOG_LEVEL=INFO
LOG_FILE=/app/logs/app.log
```

### Frontend (.env)
```env
VITE_API_URL=http://localhost:8000
VITE_MAX_FILE_SIZE=52428800
VITE_APP_TITLE=DOCX to PDF Converter
```

---

## 🔄 CI/CD Pipeline

### GitHub Actions Workflows Included:

1. **`.github/workflows/deploy.yml`** - Deploys frontend to GitHub Pages
2. **`.github/workflows/docker.yml`** - Builds and pushes Docker images to GHCR

### Required Secrets:
- `VITE_API_URL` - Backend API URL for frontend
- `GITHUB_TOKEN` - Auto-provided for GHCR

### Triggering Deployments:
```bash
# Deploy frontend
git push origin main

# Deploy Docker images
git push origin main
# Or create a release tag
git tag v1.0.0
git push origin v1.0.0
```

---

## 🏥 Health Checks & Monitoring

### Backend Health Endpoint
```bash
curl http://localhost:8000/health
# Returns: {"status": "healthy", "version": "1.0.0"}
```

### Docker Health Checks
```yaml
# In docker-compose.yml
healthcheck:
  test: ["CMD", "wget", "-q", "--spider", "http://localhost:8000/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

### Logs
```bash
# View logs
docker-compose logs -f backend
docker-compose logs -f frontend

# Or in Kubernetes
kubectl logs -f deployment/docx-pdf-converter-backend
```

---

## 🔒 Security Considerations

1. **File Upload Limits** - Configured via `MAX_FILE_SIZE`
2. **CORS** - Restrict to your domain in production
3. **Rate Limiting** - Add via nginx or API gateway
4. **HTTPS** - Use reverse proxy (nginx/Traefik) with SSL
5. **Secrets** - Never commit `.env` files, use GitHub Secrets

---

## 📊 Scaling Considerations

### Horizontal Scaling
- Backend: Stateless, can run multiple replicas
- Frontend: Static files, serve via CDN
- File Storage: Use shared volume (NFS, EFS) or object storage (S3)

### Resource Requirements
| Component | CPU | Memory | Storage |
|-----------|-----|--------|---------|
| Backend | 1-2 cores | 2-4 GB | 10 GB + uploads |
| Frontend | 0.1 core | 128 MB | 50 MB |
| LibreOffice | 1 core | 1-2 GB | 2 GB |

---

## 🐛 Troubleshooting

### Common Issues

**LibreOffice not found:**
```bash
# In Dockerfile, ensure:
RUN apt-get update && apt-get install -y libreoffice libreoffice-writer
```

**Permission denied on uploads:**
```bash
# Fix permissions
chmod 755 backend/data/uploads backend/data/outputs backend/data/temp
```

**Large file timeout:**
```bash
# Increase timeouts in nginx.conf and uvicorn
# nginx: proxy_read_timeout 300s;
# uvicorn: --timeout-keep-alive 300
```

**Memory issues with LibreOffice:**
```bash
# Limit LibreOffice memory
export LIBREOFFICE_MEMORY_LIMIT=1024
```

---

## 📞 Support

- **Issues**: GitHub Issues
- **Discussions**: GitHub Discussions
- **Documentation**: `/docs` folder
- **API Docs**: `/docs` endpoint when running

---

## 🎯 Quick Start Commands

```bash
# Local development
git clone https://github.com/yourusername/docx-pdf-converter.git
cd docx-pdf-converter

# Backend
cd backend
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
uvicorn main:app --reload

# Frontend (new terminal)
cd frontend
npm install
npm run dev

# Docker (production-like)
docker-compose up --build

# Deploy to GitHub Pages
git push origin main
```

---

*Happy Deploying! 🚀*