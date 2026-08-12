import os
import uuid
import shutil
import asyncio
from pathlib import Path
from typing import List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import magic
from PIL import Image
import fitz  # PyMuPDF
from docx import Document
import zipfile

# Configuration
UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("outputs")
TEMP_DIR = Path("temp")

# Create directories
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)

# Job storage (in production, use Redis or database)
jobs = {}

class JobStatus(BaseModel):
    job_id: str
    status: str  # pending, processing, completed, failed
    progress: int
    message: str
    result_files: List[str] = []
    error: Optional[str] = None

class ConversionOptions(BaseModel):
    quality: int = 85  # For image compression
    dpi: int = 150     # For PDF conversion
    compress_images: bool = True

def get_file_type(file_path: Path) -> str:
    """Detect file type using python-magic"""
    mime = magic.Magic(mime=True)
    return mime.from_file(str(file_path))

def update_job_status(job_id: str, status: str, progress: int, message: str, result_files: List[str] = None, error: str = None):
    """Update job status"""
    if job_id in jobs:
        jobs[job_id].status = status
        jobs[job_id].progress = progress
        jobs[job_id].message = message
        if result_files:
            jobs[job_id].result_files = result_files
        if error:
            jobs[job_id].error = error

async def convert_docx_to_pdf_libreoffice(input_path: Path, output_path: Path) -> bool:
    """Convert DOCX to PDF using LibreOffice headless"""
    try:
        # Use libreoffice command line
        cmd = [
            "libreoffice",
            "--headless",
            "--convert-to", "pdf",
            "--outdir", str(output_path.parent),
            str(input_path)
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            # LibreOffice creates file with same name but .pdf extension
            expected_output = output_path.parent / (input_path.stem + ".pdf")
            if expected_output.exists():
                if expected_output != output_path:
                    shutil.move(str(expected_output), str(output_path))
                return True
        return False
    except Exception as e:
        print(f"LibreOffice conversion failed: {e}")
        return False

async def convert_docx_to_pdf_fallback(input_path: Path, output_path: Path) -> bool:
    """Fallback conversion using python-docx and reportlab (basic)"""
    try:
        # This is a basic fallback - for production, use LibreOffice
        doc = Document(input_path)
        # For now, we'll just create a simple PDF with text content
        # In production, you'd want a more sophisticated conversion
        import fitz
        pdf_doc = fitz.open()
        page = pdf_doc.new_page()
        
        y_position = 50
        for para in doc.paragraphs:
            if para.text.strip():
                page.insert_text((50, y_position), para.text, fontsize=11)
                y_position += 20
                if y_position > 800:  # New page
                    page = pdf_doc.new_page()
                    y_position = 50
        
        pdf_doc.save(str(output_path))
        pdf_doc.close()
        return True
    except Exception as e:
        print(f"Fallback conversion failed: {e}")
        return False

async def compress_image(input_path: Path, output_path: Path, quality: int = 85, max_dimension: int = 1920) -> dict:
    """Compress image file"""
    try:
        with Image.open(input_path) as img:
            original_size = input_path.stat().st_size
            
            # Convert RGBA to RGB if saving as JPEG
            if img.mode in ('RGBA', 'LA', 'P') and output_path.suffix.lower() in ['.jpg', '.jpeg']:
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = background
            
            # Resize if too large
            if max(img.width, img.height) > max_dimension:
                ratio = max_dimension / max(img.width, img.height)
                new_size = (int(img.width * ratio), int(img.height * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
            
            # Save with compression
            if output_path.suffix.lower() in ['.jpg', '.jpeg']:
                img.save(output_path, 'JPEG', quality=quality, optimize=True)
            elif output_path.suffix.lower() == '.png':
                img.save(output_path, 'PNG', optimize=True)
            elif output_path.suffix.lower() == '.webp':
                img.save(output_path, 'WEBP', quality=quality, method=6)
            else:
                img.save(output_path, quality=quality, optimize=True)
            
            compressed_size = output_path.stat().st_size
            return {
                "success": True,
                "original_size": original_size,
                "compressed_size": compressed_size,
                "reduction_percent": round((1 - compressed_size / original_size) * 100, 2)
            }
    except Exception as e:
        return {"success": False, "error": str(e)}

async def compress_pdf(input_path: Path, output_path: Path, quality: int = 85) -> dict:
    """Compress PDF file using PyMuPDF"""
    try:
        original_size = input_path.stat().st_size
        doc = fitz.open(str(input_path))
        
        # Compress images in PDF
        for page_num in range(len(doc)):
            page = doc[page_num]
            images = page.get_images(full=True)
            
            for img_index, img in enumerate(images):
                xref = img[0]
                pix = fitz.Pixmap(doc, xref)
                
                if pix.n < 5:  # GRAY or RGB
                    # Compress the image
                    new_pix = fitz.Pixmap(fitz.csRGB, pix.width, pix.height, pix.alpha)
                    new_pix.copy(pix, (0, 0, pix.width, pix.height))
                    doc.update_stream(xref, new_pix.tobytes("jpeg", quality=quality))
                else:  # CMYK
                    new_pix = fitz.Pixmap(fitz.csRGB, pix)
                    doc.update_stream(xref, new_pix.tobytes("jpeg", quality=quality))
        
        doc.save(str(output_path), garbage=4, deflate=True, clean=True)
        doc.close()
        
        compressed_size = output_path.stat().st_size
        return {
            "success": True,
            "original_size": original_size,
            "compressed_size": compressed_size,
            "reduction_percent": round((1 - compressed_size / original_size) * 100, 2)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

async def compress_docx(input_path: Path, output_path: Path) -> dict:
    """Compress DOCX by optimizing images inside"""
    try:
        original_size = input_path.stat().st_size
        
        # DOCX is a zip file, we can extract, compress images, and re-zip
        with zipfile.ZipFile(input_path, 'r') as zin:
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zout:
                for item in zin.infolist():
                    data = zin.read(item.filename)
                    
                    # If it's an image, compress it
                    if item.filename.startswith('word/media/') and any(
                        item.filename.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']
                    ):
                        # Compress image
                        import io
                        img = Image.open(io.BytesIO(data))
                        if img.mode in ('RGBA', 'LA', 'P'):
                            background = Image.new('RGB', img.size, (255, 255, 255))
                            if img.mode == 'P':
                                img = img.convert('RGBA')
                            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                            img = background
                        
                        output_buffer = io.BytesIO()
                        img.save(output_buffer, format='JPEG', quality=85, optimize=True)
                        data = output_buffer.getvalue()
                    
                    zout.writestr(item, data)
        
        compressed_size = output_path.stat().st_size
        return {
            "success": True,
            "original_size": original_size,
            "compressed_size": compressed_size,
            "reduction_percent": round((1 - compressed_size / original_size) * 100, 2)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

async def create_zip_archive(files: List[Path], output_path: Path) -> dict:
    """Create a ZIP archive of multiple files"""
    try:
        total_original = sum(f.stat().st_size for f in files)
        
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for file_path in files:
                zf.write(file_path, arcname=file_path.name)
        
        compressed_size = output_path.stat().st_size
        return {
            "success": True,
            "original_size": total_original,
            "compressed_size": compressed_size,
            "reduction_percent": round((1 - compressed_size / total_original) * 100, 2)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Starting DOCX to PDF Converter with File Compressor...")
    yield
    # Shutdown
    print("Shutting down...")

app = FastAPI(
    title="DOCX to PDF Converter & File Compressor",
    description="Convert DOCX to PDF and compress various file formats",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for downloads
app.mount("/downloads", StaticFiles(directory="outputs"), name="downloads")

@app.get("/")
async def root():
    return {
        "message": "DOCX to PDF Converter & File Compressor API",
        "version": "1.0.0",
        "endpoints": {
            "convert_docx_to_pdf": "POST /api/convert/docx-to-pdf",
            "compress_file": "POST /api/compress/file",
            "compress_batch": "POST /api/compress/batch",
            "job_status": "GET /api/status/{job_id}",
            "download": "GET /api/download/{file_id}"
        }
    }

@app.post("/api/convert/docx-to-pdf")
async def convert_docx_to_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    quality: int = Form(85),
    dpi: int = Form(150)
):
    """Convert DOCX file to PDF"""
    # Validate file type
    if not file.filename.lower().endswith(('.docx', '.doc')):
        raise HTTPException(status_code=400, detail="Only DOCX/DOC files are supported")
    
    # Create job
    job_id = str(uuid.uuid4())
    job = JobStatus(
        job_id=job_id,
        status="pending",
        progress=0,
        message="Job created"
    )
    jobs[job_id] = job
    
    # Save uploaded file
    input_path = UPLOAD_DIR / f"{job_id}_{file.filename}"
    with open(input_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    output_filename = f"{Path(file.filename).stem}.pdf"
    output_path = OUTPUT_DIR / f"{job_id}_{output_filename}"
    
    # Process in background
    background_tasks.add_task(
        process_docx_conversion,
        job_id, input_path, output_path, output_filename
    )
    
    return {"job_id": job_id, "message": "Conversion started"}

async def process_docx_conversion(job_id: str, input_path: Path, output_path: Path, output_filename: str):
    """Background task for DOCX to PDF conversion"""
    try:
        update_job_status(job_id, "processing", 10, "Starting conversion...")
        
        # Try LibreOffice first
        update_job_status(job_id, "processing", 30, "Converting with LibreOffice...")
        success = await convert_docx_to_pdf_libreoffice(input_path, output_path)
        
        if not success:
            update_job_status(job_id, "processing", 50, "LibreOffice failed, trying fallback...")
            success = await convert_docx_to_pdf_fallback(input_path, output_path)
        
        if success and output_path.exists():
            update_job_status(job_id, "completed", 100, "Conversion completed", [output_filename])
        else:
            update_job_status(job_id, "failed", 0, "Conversion failed", error="Both conversion methods failed")
    
    except Exception as e:
        update_job_status(job_id, "failed", 0, "Conversion failed", error=str(e))
    finally:
        # Cleanup input file
        if input_path.exists():
            input_path.unlink()

@app.post("/api/compress/file")
async def compress_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    quality: int = Form(85),
    max_dimension: int = Form(1920)
):
    """Compress a single file (image, PDF, DOCX, or create ZIP)"""
    job_id = str(uuid.uuid4())
    job = JobStatus(
        job_id=job_id,
        status="pending",
        progress=0,
        message="Job created"
    )
    jobs[job_id] = job
    
    # Save uploaded file
    input_path = UPLOAD_DIR / f"{job_id}_{file.filename}"
    with open(input_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    # Determine output filename
    file_type = get_file_type(input_path)
    output_filename = f"compressed_{file.filename}"
    output_path = OUTPUT_DIR / f"{job_id}_{output_filename}"
    
    background_tasks.add_task(
        process_file_compression,
        job_id, input_path, output_path, output_filename, file_type, quality, max_dimension
    )
    
    return {"job_id": job_id, "message": "Compression started"}

async def process_file_compression(
    job_id: str, 
    input_path: Path, 
    output_path: Path, 
    output_filename: str,
    file_type: str,
    quality: int,
    max_dimension: int
):
    """Background task for file compression"""
    try:
        update_job_status(job_id, "processing", 10, "Analyzing file...")
        
        result = {"success": False}
        
        if file_type.startswith('image/'):
            update_job_status(job_id, "processing", 30, "Compressing image...")
            result = await compress_image(input_path, output_path, quality, max_dimension)
        
        elif file_type == 'application/pdf':
            update_job_status(job_id, "processing", 30, "Compressing PDF...")
            result = await compress_pdf(input_path, output_path, quality)
        
        elif file_type in ['application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                          'application/msword']:
            update_job_status(job_id, "processing", 30, "Compressing DOCX...")
            result = await compress_docx(input_path, output_path)
        
        else:
            # For other files, create ZIP
            update_job_status(job_id, "processing", 30, "Creating ZIP archive...")
            result = await create_zip_archive([input_path], output_path)
            output_filename = f"{Path(output_filename).stem}.zip"
            output_path = OUTPUT_DIR / f"{job_id}_{output_filename}"
        
        if result.get("success") and output_path.exists():
            update_job_status(
                job_id, "completed", 100, "Compression completed", 
                [output_filename],
                error=None
            )
            # Add compression info to job
            jobs[job_id].message += f" | Reduced by {result.get('reduction_percent', 0)}%"
        else:
            update_job_status(job_id, "failed", 0, "Compression failed", error=result.get("error", "Unknown error"))
    
    except Exception as e:
        update_job_status(job_id, "failed", 0, "Compression failed", error=str(e))
    finally:
        if input_path.exists():
            input_path.unlink()

@app.post("/api/compress/batch")
async def compress_batch(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    quality: int = Form(85),
    create_zip: bool = Form(True)
):
    """Compress multiple files"""
    job_id = str(uuid.uuid4())
    job = JobStatus(
        job_id=job_id,
        status="pending",
        progress=0,
        message="Job created"
    )
    jobs[job_id] = job
    
    input_paths = []
    for file in files:
        input_path = UPLOAD_DIR / f"{job_id}_{file.filename}"
        with open(input_path, "wb") as f:
            content = await file.read()
            f.write(content)
        input_paths.append(input_path)
    
    if create_zip:
        output_filename = f"compressed_batch_{job_id[:8]}.zip"
        output_path = OUTPUT_DIR / f"{job_id}_{output_filename}"
        background_tasks.add_task(
            process_batch_compression,
            job_id, input_paths, output_path, output_filename, quality, True
        )
    else:
        # Process each file individually
        background_tasks.add_task(
            process_batch_compression,
            job_id, input_paths, None, None, quality, False
        )
    
    return {"job_id": job_id, "message": "Batch compression started"}

async def process_batch_compression(
    job_id: str,
    input_paths: List[Path],
    output_path: Path,
    output_filename: str,
    quality: int,
    create_zip: bool
):
    """Background task for batch compression"""
    try:
        update_job_status(job_id, "processing", 10, f"Processing {len(input_paths)} files...")
        
        result_files = []
        total_original = 0
        total_compressed = 0
        
        if create_zip:
            # Create single ZIP
            result = await create_zip_archive(input_paths, output_path)
            if result.get("success"):
                result_files = [output_filename]
                total_original = result.get("original_size", 0)
                total_compressed = result.get("compressed_size", 0)
        else:
            # Compress each file individually
            for i, input_path in enumerate(input_paths):
                file_type = get_file_type(input_path)
                out_filename = f"compressed_{input_path.name}"
                out_path = OUTPUT_DIR / f"{job_id}_{out_filename}"
                
                if file_type.startswith('image/'):
                    result = await compress_image(input_path, out_path, quality)
                elif file_type == 'application/pdf':
                    result = await compress_pdf(input_path, out_path, quality)
                elif file_type in ['application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                                  'application/msword']:
                    result = await compress_docx(input_path, out_path)
                else:
                    result = await create_zip_archive([input_path], out_path)
                    out_filename = f"{Path(out_filename).stem}.zip"
                    out_path = OUTPUT_DIR / f"{job_id}_{out_filename}"
                
                if result.get("success") and out_path.exists():
                    result_files.append(out_filename)
                    total_original += result.get("original_size", 0)
                    total_compressed += result.get("compressed_size", 0)
                
                progress = 10 + int((i + 1) / len(input_paths) * 80)
                update_job_status(job_id, "processing", progress, f"Processed {i+1}/{len(input_paths)} files")
        
        if result_files:
            reduction = round((1 - total_compressed / total_original) * 100, 2) if total_original > 0 else 0
            update_job_status(
                job_id, "completed", 100, 
                f"Batch compression completed. Reduced by {reduction}%",
                result_files
            )
        else:
            update_job_status(job_id, "failed", 0, "All compressions failed")
    
    except Exception as e:
        update_job_status(job_id, "failed", 0, "Batch compression failed", error=str(e))
    finally:
        for p in input_paths:
            if p.exists():
                p.unlink()

@app.get("/api/status/{job_id}")
async def get_job_status(job_id: str):
    """Get job status"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]

@app.get("/api/download/{file_id}")
async def download_file(file_id: str):
    """Download processed file"""
    # Find file in outputs directory
    for file_path in OUTPUT_DIR.glob(f"{file_id}_*"):
        if file_path.is_file():
            return FileResponse(
                path=str(file_path),
                filename=file_path.name.replace(f"{file_id}_", ""),
                media_type='application/octet-stream'
            )
    raise HTTPException(status_code=404, detail="File not found")

@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "service": "docx-pdf-converter"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)