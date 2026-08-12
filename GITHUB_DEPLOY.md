# 🚀 Quick GitHub Deployment Guide

Your DOCX to PDF Converter is now ready for GitHub deployment! Here's how to push it to GitHub and deploy.

## 📤 Step 1: Create GitHub Repository

1. Go to [GitHub.com](https://github.com) and create a new repository
2. Name it: `docx-pdf-converter` (or your preferred name)
3. **Don't** initialize with README, .gitignore, or license (we already have them)
4. Copy the repository URL (e.g., `https://github.com/yourusername/docx-pdf-converter.git`)

## 🔗 Step 2: Connect and Push

```bash
# Navigate to project
cd c:\Users\b7993\OneDrive\Desktop\docx-pdf-converter

# Add GitHub remote (replace with your URL)
git remote add origin https://github.com/YOUR_USERNAME/docx-pdf-converter.git

# Push to GitHub
git branch -M main
git push -u origin main
```

## 🌐 Step 3: Deploy Frontend to GitHub Pages

1. **Enable GitHub Pages:**
   - Go to your repo → Settings → Pages
   - Source: "GitHub Actions"
   - Save

2. **Add Backend URL Secret:**
   - Settings → Secrets and variables → Actions → New repository secret
   - Name: `VITE_API_URL`
   - Value: Your backend URL (e.g., `https://your-backend.railway.app`)

3. **Auto-deploy:** Push to main branch triggers deployment!

## 🐳 Step 4: Deploy Backend (Choose One)

### Option A: Railway (Easiest - Free Tier)
```bash
# 1. Install CLI
npm install -g @railway/cli

# 2. Deploy
railway login
railway init
railway up
```

### Option B: Render (Free Tier)
1. Go to [render.com](https://render.com) → New Web Service
2. Connect GitHub repo
3. Root Directory: `backend`
4. Build: `pip install -r requirements.txt`
5. Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`

### Option C: Fly.io
```bash
curl -L https://fly.io/install.sh | sh
fly launch
fly deploy
```

### Option D: Docker on Any VPS
```bash
# On your server
git clone https://github.com/yourusername/docx-pdf-converter.git
cd docx-pdf-converter
docker-compose up -d --build
```

## 🔧 Step 5: Configure GitHub Actions for Docker (Optional)

The workflows are already set up! They will:
- Build and push Docker images to `ghcr.io/yourusername/docx-pdf-converter`
- Deploy frontend to GitHub Pages

**To enable:**
1. Go to Settings → Actions → General
2. Enable "Allow GitHub Actions to create and approve pull requests"
3. Save

## 📋 Repository Structure

```
docx-pdf-converter/
├── .github/workflows/
│   ├── deploy.yml      # GitHub Pages deployment
│   └── docker.yml      # Docker image builds
├── backend/
│   ├── main.py         # FastAPI application
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml  # Full stack deployment
├── nginx.conf          # Reverse proxy config
├── DEPLOYMENT.md       # Detailed deployment guide
└── README.md           # Project documentation
```

## ✅ Verification Checklist

After deployment, verify:
- [ ] Frontend loads at `https://yourusername.github.io/docx-pdf-converter`
- [ ] Backend API responds at `https://your-backend-url/health`
- [ ] File upload works
- [ ] DOCX to PDF conversion works
- [ ] File compression works
- [ ] Download functionality works

## 🆘 Troubleshooting

**GitHub Pages not updating?**
- Check Actions tab for build logs
- Ensure `VITE_API_URL` secret is set correctly

**Backend deployment fails?**
- Check logs in your hosting platform
- Ensure LibreOffice is installed (included in Dockerfile)
- Check port configuration

**CORS errors?**
- Update `CORS_ORIGINS` in backend `.env` to include your frontend URL

## 🎉 You're Live!

Once deployed, your application will be accessible at:
- **Frontend**: `https://yourusername.github.io/docx-pdf-converter`
- **Backend API**: `https://your-backend-url`
- **API Docs**: `https://your-backend-url/docs`

---

**Need help?** Check the [DEPLOYMENT.md](DEPLOYMENT.md) for detailed instructions or open a GitHub Issue!