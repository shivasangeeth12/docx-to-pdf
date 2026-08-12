# 📄 DOCX to PDF Converter with File Compression

A modern, full-stack web application for converting DOCX/DOC files to PDF and compressing various file formats (images, PDFs, documents) with a beautiful drag-and-drop interface.

## ✨ Features

### 🔄 DOCX to PDF Conversion
- Convert single or multiple DOCX/DOC files to PDF
- High-quality conversion using LibreOffice headless
- Configurable DPI (72-300) and quality settings
- Preserves formatting, images, tables, and layouts

### 🗜️ File Compression
- **Images**: JPG, PNG, WebP, GIF, BMP, TIFF compression with quality control
- **PDFs**: Ghostscript-powered PDF compression
- **Documents**: DOCX/DOC optimization
- **Batch Processing**: Compress multiple files at once with optional ZIP archive

### 🎨 Modern UI/UX
- Drag & drop file upload with visual feedback
- Real-time progress tracking
- Responsive design (mobile-friendly)
- Dark/light theme support
- File preview with icons and sizes

### 🚀 Deployment Ready
- Docker multi-stage build
- Nginx reverse proxy
- Health checks
- Development and production configurations

## 🛠️ Tech Stack

### Backend
- **FastAPI** - Modern, fast Python web framework
- **LibreOffice** - Headless document conversion
- **Pillow (PIL)** - Image processing
- **PyMuPDF (fitz)** - PDF manipulation
- **python-docx** - DOCX processing
- **Ghostscript** - PDF compression

### Frontend
- **React 18** - Modern React with hooks
- **Vite** - Fast build tool
- **Axios** - HTTP client
- **Vanilla CSS** - Custom styling (no framework dependencies)

### Infrastructure
- **Docker** - Containerization
- **Nginx** - Reverse proxy & static file serving
- **Docker Compose** - Multi-service orchestration

## 📦 Quick Start

### Option 1: Docker (Recommended)

```bash
# Clone and navigate
cd docx-pdf-converter

# Build and run production
docker-compose up -d --build

# Access at http://localhost
```

### Option 2: Development Mode

```bash
# Start development servers with hot reload
docker-compose --profile dev up -d --build

# Frontend: http://localhost:3000
# Backend API: http://localhost:8000
```

### Option 3: Local Development

#### Backend
```bash
cd backend
pip install -r requirements.txt

# Install system dependencies (Ubuntu/Debian)
sudo apt-get install libreoffice libreoffice-writer poppler-utils ghostscript

# Install system dependencies (macOS)
brew install libreoffice poppler ghostscript

uvicorn main:app --reload --port 8000
```

#### Frontend
```bash
cd frontend
npm install
npm run dev
```

## 📁 Project Structure

```
docx-pdf-converter/
├── backend/
│   ├── main.py              # FastAPI application
│   ├── requirements.txt     # Python dependencies
│   ├── converters/          # Conversion modules
│   │   ├── docx_to_pdf.py   # DOCX to PDF conversion
│   │   ├── image_compressor.py  # Image compression
│   │   ├── pdf_compressor.py    # PDF compression
│   │   └── document_compressor.py # Document compression
│   └── utils/
│       ├── file_handler.py  # File operations
│       └── job_manager.py   # Background job management
├── frontend/
│   ├── src/
│   │   ├── App.jsx          # Main React component
│   │   ├── main.jsx         # Entry point
│   │   └── index.css        # Styles
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── nginx.conf               # Nginx configuration
├── Dockerfile               # Production Dockerfile
├── Dockerfile.dev           # Development Dockerfile
├── docker-compose.yml       # Docker Compose
└── README.md
```

## 🔌 API Endpoints

### Conversion
```
POST   /api/convert/docx-to-pdf     # Convert DOCX to PDF
GET    /api/status/{job_id}         # Check job status
GET    /api/download/{job_id}       # Download result
```

### Compression
```
POST   /api/compress/file           # Compress single file
POST   /api/compress/batch          # Batch compress multiple files
GET    /api/status/{job_id}         # Check job status
GET    /api/download/{job_id}       # Download result
```

### Health
```
GET    /health                      # Health check
```

## ⚙️ Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LIBREOFFICE_PATH` | `/usr/bin/libreoffice` | Path to LibreOffice executable |
| `MAX_FILE_SIZE` | `104857600` | Max upload size (100MB) |
| `TEMP_DIR` | `/tmp/docx-converter` | Temporary file directory |
| `RESULT_TTL` | `3600` | Result file TTL in seconds |

### Frontend Configuration (vite.config.js)
```javascript
export default defineConfig({
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
})
```

## 📖 Usage Examples

### Convert DOCX to PDF (cURL)
```bash
curl -X POST http://localhost/api/convert/docx-to-pdf \
  -F "file=@document.docx" \
  -F "quality=90" \
  -F "dpi=200"
```

### Compress Image (cURL)
```bash
curl -X POST http://localhost/api/compress/file \
  -F "file=@image.jpg" \
  -F "quality=85" \
  -F "max_dimension=1920"
```

### Batch Compress (cURL)
```bash
curl -X POST http://localhost/api/compress/batch \
  -F "files=@file1.jpg" \
  -F "files=@file2.pdf" \
  -F "files=@file3.docx" \
  -F "quality=80" \
  -F "create_zip=true"
```

## 🔧 Advanced Features

### Job Management
- All operations run asynchronously
- Real-time progress updates via polling
- Automatic cleanup of temporary files
- Configurable result retention

### File Type Detection
- Automatic MIME type detection using python-magic
- Extension-based fallback
- Validates file content, not just extension

### Compression Algorithms

#### Images
- **JPEG**: Quality-based compression (10-100%)
- **PNG**: Lossless optimization + optional quality reduction
- **WebP**: Modern format with superior compression
- **Resize**: Max dimension constraint with aspect ratio preservation

#### PDFs
- **Ghostscript**: `/screen`, `/ebook`, `/printer`, `/prepress` quality levels
- **Downsampling**: Image resolution reduction
- **Font embedding**: Subset fonts to reduce size

#### Documents
- **DOCX**: Remove metadata, compress images, optimize XML
- **Structure**: Remove unused styles, optimize relationships

## 🐳 Docker Deployment

### Production
```bash
# Build
docker build -t docx-pdf-converter .

# Run
docker run -d \
  -p 80:80 \
  -v $(pwd)/data:/app/backend/data \
  -v $(pwd)/logs:/app/backend/logs \
  --name docx-converter \
  docx-pdf-converter
```

### With Docker Compose
```bash
# Production
docker-compose up -d

# Development
docker-compose --profile dev up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

### Kubernetes (Example)
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: docx-pdf-converter
spec:
  replicas: 3
  selector:
    matchLabels:
      app: docx-pdf-converter
  template:
    metadata:
      labels:
        app: docx-pdf-converter
    spec:
      containers:
      - name: app
        image: docx-pdf-converter:latest
        ports:
        - containerPort: 80
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
---
apiVersion: v1
kind: Service
metadata:
  name: docx-pdf-converter
spec:
  selector:
    app: docx-pdf-converter
  ports:
  - port: 80
    targetPort: 80
  type: LoadBalancer
```

## 🧪 Testing

### Backend Tests
```bash
cd backend
pytest tests/ -v
```

### Frontend Tests
```bash
cd frontend
npm test
```

### Manual Testing Checklist
- [ ] Upload DOCX file → Convert to PDF
- [ ] Upload multiple DOCX files → Batch convert
- [ ] Upload JPG/PNG → Compress image
- [ ] Upload PDF → Compress PDF
- [ ] Upload mixed files → Batch compress with ZIP
- [ ] Test progress tracking
- [ ] Test download functionality
- [ ] Test error handling (invalid files, oversized files)
- [ ] Test responsive design on mobile

## 🔒 Security Considerations

- File size limits (100MB default)
- Temporary file cleanup
- No persistent storage of user files
- CORS configuration for production
- Rate limiting (recommended for production)
- Input validation on all endpoints

## 📊 Performance

### Benchmarks (Typical)
| Operation | File Size | Time |
|-----------|-----------|------|
| DOCX → PDF | 5MB | ~3-5s |
| Image Compress | 10MB | ~1-2s |
| PDF Compress | 20MB | ~5-10s |
| Batch (5 files) | 50MB | ~15-30s |

### Optimization Tips
- Use SSD for temp directory
- Increase worker processes for high load
- Enable nginx caching for static assets
- Consider Redis for job queue at scale

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## 📝 License

MIT License - see LICENSE file for details.

## 🙏 Acknowledgments

- [LibreOffice](https://www.libreoffice.org/) - Document conversion
- [Ghostscript](https://www.ghostscript.com/) - PDF processing
- [FastAPI](https://fastapi.tiangolo.com/) - Backend framework
- [React](https://reactjs.org/) - Frontend framework
- [Vite](https://vitejs.dev/) - Build tool

## 📞 Support

- **Issues**: GitHub Issues
- **Discussions**: GitHub Discussions
- **Email**: support@example.com

---

**Built with ❤️ for efficient document processing**