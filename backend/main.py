import asyncio
import io
import shutil
import uuid
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

import fitz  # PyMuPDF
import magic
from docx import Document
from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import BaseModel, Field


# ============================================================
# Configuration
# ============================================================

UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("outputs")
TEMP_DIR = Path("temp")

MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB
CHUNK_SIZE = 1024 * 1024  # 1 MB

ALLOWED_DOCX_EXTENSIONS = {".docx", ".doc"}

# Create directories
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# In-memory job storage
# NOTE: For production, replace this with Redis/database.
# ============================================================

jobs = {}


# ============================================================
# Models
# ============================================================

class JobStatus(BaseModel):
    job_id: str
    status: str  # pending, processing, completed, failed
    progress: int
    message: str
    result_files: List[str] = Field(default_factory=list)
    error: Optional[str] = None


class ConversionOptions(BaseModel):
    quality: int = 85
    dpi: int = 150
    compress_images: bool = True


# ============================================================
# Utility Functions
# ============================================================

def safe_filename(filename: Optional[str]) -> str:
    """
    Remove path components and unsafe filename characters.
    """
    if not filename:
        return "uploaded_file"

    filename = Path(filename).name

    # Replace potentially unsafe characters
    filename = "".join(
        char if char.isalnum() or char in "._-" else "_"
        for char in filename
    )

    return filename or "uploaded_file"


def validate_quality(quality: int):
    if quality < 1 or quality > 100:
        raise HTTPException(
            status_code=400,
            detail="Quality must be between 1 and 100"
        )


def validate_max_dimension(max_dimension: int):
    if max_dimension < 100 or max_dimension > 10000:
        raise HTTPException(
            status_code=400,
            detail="Max dimension must be between 100 and 10000"
        )


async def save_upload_file(
    file: UploadFile,
    destination: Path,
    max_size: int = MAX_FILE_SIZE,
):
    """
    Save uploaded file in chunks instead of loading the entire file
    into memory.
    """
    total_size = 0

    try:
        with open(destination, "wb") as output_file:
            while True:
                chunk = await file.read(CHUNK_SIZE)

                if not chunk:
                    break

                total_size += len(chunk)

                if total_size > max_size:
                    output_file.close()

                    if destination.exists():
                        destination.unlink()

                    raise HTTPException(
                        status_code=413,
                        detail="File size exceeds the 100 MB limit"
                    )

                output_file.write(chunk)

    finally:
        await file.close()

    return total_size


def get_file_type(file_path: Path) -> str:
    """
    Detect file MIME type using python-magic.
    """
    try:
        mime = magic.Magic(mime=True)
        return mime.from_file(str(file_path))
    except Exception:
        return "application/octet-stream"


def update_job_status(
    job_id: str,
    status: str,
    progress: int,
    message: str,
    result_files: Optional[List[str]] = None,
    error: Optional[str] = None,
):
    """
    Update job status safely.
    """
    if job_id not in jobs:
        return

    jobs[job_id].status = status
    jobs[job_id].progress = max(0, min(100, progress))
    jobs[job_id].message = message

    if result_files is not None:
        jobs[job_id].result_files = result_files

    if error is not None:
        jobs[job_id].error = error


# ============================================================
# DOCX → PDF
# ============================================================

async def convert_docx_to_pdf_libreoffice(
    input_path: Path,
    output_path: Path,
) -> bool:
    """
    Convert DOCX/DOC to PDF using LibreOffice.
    """
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        command = [
            "libreoffice",
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(output_path.parent),
            str(input_path),
        ]

        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            print(
                "LibreOffice error:",
                stderr.decode(errors="ignore")
            )
            return False

        expected_output = (
            output_path.parent /
            f"{input_path.stem}.pdf"
        )

        if not expected_output.exists():
            print("LibreOffice output file not found")
            return False

        if expected_output != output_path:
            if output_path.exists():
                output_path.unlink()

            shutil.move(
                str(expected_output),
                str(output_path)
            )

        return output_path.exists()

    except FileNotFoundError:
        print("LibreOffice is not installed or not available in PATH")
        return False

    except Exception as exc:
        print(f"LibreOffice conversion failed: {exc}")
        return False


async def convert_docx_to_pdf_fallback(
    input_path: Path,
    output_path: Path,
) -> bool:
    """
    Basic fallback for DOCX files.

    This fallback extracts text only.
    It is NOT a complete DOCX renderer.
    """
    try:
        if input_path.suffix.lower() != ".docx":
            return False

        document = Document(input_path)

        pdf_document = fitz.open()

        page = pdf_document.new_page()

        x = 50
        y = 50

        for paragraph in document.paragraphs:
            text = paragraph.text.strip()

            if not text:
                continue

            # Create new page when necessary
            if y > 750:
                page = pdf_document.new_page()
                y = 50

            page.insert_text(
                (x, y),
                text,
                fontsize=11,
            )

            y += 20

        if len(pdf_document) == 0:
            pdf_document.new_page()

        pdf_document.save(str(output_path))
        pdf_document.close()

        return output_path.exists()

    except Exception as exc:
        print(f"Fallback conversion failed: {exc}")
        return False


# ============================================================
# IMAGE COMPRESSION
# ============================================================

async def compress_image(
    input_path: Path,
    output_path: Path,
    quality: int = 85,
    max_dimension: int = 1920,
) -> dict:
    """
    Compress image while preserving the correct output format.
    """
    try:
        original_size = input_path.stat().st_size

        with Image.open(input_path) as original_image:
            img = original_image.copy()

            # Resize large images
            if max(img.width, img.height) > max_dimension:
                ratio = max_dimension / max(img.width, img.height)

                new_size = (
                    max(1, int(img.width * ratio)),
                    max(1, int(img.height * ratio)),
                )

                img = img.resize(
                    new_size,
                    Image.Resampling.LANCZOS,
                )

            extension = output_path.suffix.lower()

            # JPEG
            if extension in {".jpg", ".jpeg"}:
                if img.mode not in {"RGB", "L"}:
                    if "A" in img.getbands():
                        background = Image.new(
                            "RGB",
                            img.size,
                            "white",
                        )

                        background.paste(
                            img,
                            mask=img.getchannel("A"),
                        )

                        img = background
                    else:
                        img = img.convert("RGB")

                img.save(
                    output_path,
                    "JPEG",
                    quality=quality,
                    optimize=True,
                )

            # PNG
            elif extension == ".png":
                img.save(
                    output_path,
                    "PNG",
                    optimize=True,
                )

            # WEBP
            elif extension == ".webp":
                if img.mode == "P":
                    img = img.convert("RGBA")

                img.save(
                    output_path,
                    "WEBP",
                    quality=quality,
                    method=6,
                )

            # Other formats
            else:
                img.save(output_path)

            compressed_size = output_path.stat().st_size

            reduction = 0

            if original_size > 0:
                reduction = round(
                    (1 - compressed_size / original_size) * 100,
                    2,
                )

            return {
                "success": True,
                "original_size": original_size,
                "compressed_size": compressed_size,
                "reduction_percent": reduction,
            }

    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


# ============================================================
# PDF COMPRESSION
# ============================================================

async def compress_pdf(
    input_path: Path,
    output_path: Path,
    quality: int = 85,
) -> dict:
    """
    Compress PDF using PyMuPDF.
    """
    try:
        original_size = input_path.stat().st_size

        document = fitz.open(str(input_path))

        for page in document:
            images = page.get_images(full=True)

            for image_info in images:
                xref = image_info[0]

                try:
                    pixmap = fitz.Pixmap(
                        document,
                        xref,
                    )

                    if pixmap.width == 0 or pixmap.height == 0:
                        pixmap = None
                        continue

                    # Convert CMYK/other formats to RGB
                    if pixmap.n < 5:
                        if pixmap.alpha:
                            rgb_pixmap = fitz.Pixmap(
                                fitz.csRGB,
                                pixmap,
                            )
                        else:
                            rgb_pixmap = pixmap
                    else:
                        rgb_pixmap = fitz.Pixmap(
                            fitz.csRGB,
                            pixmap,
                        )

                    jpeg_data = rgb_pixmap.tobytes(
                        "jpeg",
                        quality=quality,
                    )

                    document.update_stream(
                        xref,
                        jpeg_data,
                    )

                    if rgb_pixmap != pixmap:
                        rgb_pixmap = None

                    pixmap = None

                except Exception as image_error:
                    print(
                        f"Could not compress PDF image: "
                        f"{image_error}"
                    )

        document.save(
            str(output_path),
            garbage=4,
            deflate=True,
            clean=True,
        )

        document.close()

        compressed_size = output_path.stat().st_size

        reduction = 0

        if original_size > 0:
            reduction = round(
                (1 - compressed_size / original_size) * 100,
                2,
            )

        return {
            "success": True,
            "original_size": original_size,
            "compressed_size": compressed_size,
            "reduction_percent": reduction,
        }

    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


# ============================================================
# DOCX COMPRESSION
# ============================================================

async def compress_docx(
    input_path: Path,
    output_path: Path,
    quality: int = 85,
) -> dict:
    """
    Compress images inside a DOCX while preserving their
    original image format.
    """
    try:
        original_size = input_path.stat().st_size

        with zipfile.ZipFile(
            input_path,
            "r",
        ) as zin:

            with zipfile.ZipFile(
                output_path,
                "w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            ) as zout:

                for item in zin.infolist():

                    data = zin.read(item.filename)

                    filename_lower = item.filename.lower()

                    is_docx_image = (
                        item.filename.startswith("word/media/")
                        and filename_lower.endswith(
                            (
                                ".jpg",
                                ".jpeg",
                                ".png",
                                ".bmp",
                                ".tiff",
                                ".webp",
                            )
                        )
                    )

                    if is_docx_image:

                        try:
                            image = Image.open(
                                io.BytesIO(data)
                            )

                            image.load()

                            output_buffer = io.BytesIO()

                            extension = Path(
                                item.filename
                            ).suffix.lower()

                            # JPEG
                            if extension in {
                                ".jpg",
                                ".jpeg",
                            }:
                                if image.mode not in {
                                    "RGB",
                                    "L",
                                }:
                                    image = image.convert(
                                        "RGB"
                                    )

                                image.save(
                                    output_buffer,
                                    format="JPEG",
                                    quality=quality,
                                    optimize=True,
                                )

                            # PNG
                            elif extension == ".png":
                                image.save(
                                    output_buffer,
                                    format="PNG",
                                    optimize=True,
                                )

                            # WEBP
                            elif extension == ".webp":
                                image.save(
                                    output_buffer,
                                    format="WEBP",
                                    quality=quality,
                                    method=6,
                                )

                            # BMP/TIFF
                            else:
                                # Don't convert these formats
                                # because doing so would require
                                # updating DOCX content types.
                                output_buffer.write(data)

                            data = output_buffer.getvalue()

                        except Exception as image_error:
                            print(
                                f"Image compression skipped: "
                                f"{image_error}"
                            )

                    zout.writestr(item, data)

        compressed_size = output_path.stat().st_size

        reduction = 0

        if original_size > 0:
            reduction = round(
                (1 - compressed_size / original_size) * 100,
                2,
            )

        return {
            "success": True,
            "original_size": original_size,
            "compressed_size": compressed_size,
            "reduction_percent": reduction,
        }

    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


# ============================================================
# ZIP CREATION
# ============================================================

async def create_zip_archive(
    files: List[Path],
    output_path: Path,
) -> dict:
    """
    Create a ZIP archive.
    """
    try:
        total_original = sum(
            file_path.stat().st_size
            for file_path in files
            if file_path.exists()
        )

        with zipfile.ZipFile(
            output_path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as zip_file:

            used_names = set()

            for file_path in files:

                if not file_path.exists():
                    continue

                archive_name = file_path.name

                # Prevent duplicate filenames inside ZIP
                if archive_name in used_names:
                    stem = file_path.stem
                    suffix = file_path.suffix

                    counter = 1

                    while archive_name in used_names:
                        archive_name = (
                            f"{stem}_{counter}{suffix}"
                        )
                        counter += 1

                used_names.add(archive_name)

                zip_file.write(
                    file_path,
                    arcname=archive_name,
                )

        compressed_size = output_path.stat().st_size

        reduction = 0

        if total_original > 0:
            reduction = round(
                (1 - compressed_size / total_original) * 100,
                2,
            )

        return {
            "success": True,
            "original_size": total_original,
            "compressed_size": compressed_size,
            "reduction_percent": reduction,
        }

    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


# ============================================================
# Application Lifespan
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):

    print(
        "Starting DOCX to PDF Converter "
        "& File Compressor..."
    )

    print(f"Upload directory: {UPLOAD_DIR.resolve()}")
    print(f"Output directory: {OUTPUT_DIR.resolve()}")

    yield

    print("Shutting down...")


# ============================================================
# FastAPI Application
# ============================================================

app = FastAPI(
    title="DOCX to PDF Converter & File Compressor",
    description=(
        "Convert DOCX/DOC files to PDF and compress "
        "images, PDFs and DOCX files."
    ),
    version="1.1.0",
    lifespan=lifespan,
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,

    # Change these in production
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],

    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# ============================================================
# Root Endpoint
# ============================================================

@app.get("/")
async def root():

    return {
        "message": (
            "DOCX to PDF Converter "
            "& File Compressor API"
        ),
        "version": "1.1.0",
        "endpoints": {
            "convert_docx_to_pdf":
                "POST /api/convert/docx-to-pdf",

            "compress_file":
                "POST /api/compress/file",

            "compress_batch":
                "POST /api/compress/batch",

            "job_status":
                "GET /api/status/{job_id}",

            "download":
                "GET /api/download/{file_id}",

            "health":
                "GET /health",
        },
    }


# ============================================================
# Health Check
# ============================================================

@app.get("/health")
@app.get("/api/health")
async def health_check():

    return {
        "status": "healthy",
        "service": "docx-pdf-converter",
    }


# ============================================================
# DOCX → PDF Endpoint
# ============================================================

@app.post("/api/convert/docx-to-pdf")
async def convert_docx_to_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    quality: int = Form(85),
    dpi: int = Form(150),
):

    validate_quality(quality)

    filename = safe_filename(file.filename)

    extension = Path(filename).suffix.lower()

    if extension not in ALLOWED_DOCX_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Only DOCX/DOC files are supported",
        )

    job_id = str(uuid.uuid4())

    jobs[job_id] = JobStatus(
        job_id=job_id,
        status="pending",
        progress=0,
        message="Job created",
    )

    input_path = (
        UPLOAD_DIR /
        f"{job_id}_{filename}"
    )

    try:

        await save_upload_file(
            file,
            input_path,
        )

    except HTTPException:
        jobs.pop(job_id, None)
        raise

    output_filename = (
        f"{Path(filename).stem}.pdf"
    )

    output_path = (
        OUTPUT_DIR /
        f"{job_id}_{output_filename}"
    )

    background_tasks.add_task(
        process_docx_conversion,
        job_id,
        input_path,
        output_path,
        output_filename,
    )

    return {
        "job_id": job_id,
        "message": "Conversion started",
    }


# ============================================================
# DOCX Conversion Worker
# ============================================================

async def process_docx_conversion(
    job_id: str,
    input_path: Path,
    output_path: Path,
    output_filename: str,
):

    try:

        update_job_status(
            job_id,
            "processing",
            10,
            "Starting conversion...",
        )

        update_job_status(
            job_id,
            "processing",
            30,
            "Converting with LibreOffice...",
        )

        success = await convert_docx_to_pdf_libreoffice(
            input_path,
            output_path,
        )

        # Only use fallback for DOCX
        if not success and input_path.suffix.lower() == ".docx":

            update_job_status(
                job_id,
                "processing",
                50,
                "LibreOffice failed, trying fallback...",
            )

            success = await convert_docx_to_pdf_fallback(
                input_path,
                output_path,
            )

        if success and output_path.exists():

            update_job_status(
                job_id,
                "completed",
                100,
                "Conversion completed",
                [output_filename],
            )

        else:

            update_job_status(
                job_id,
                "failed",
                0,
                "Conversion failed",
                error=(
                    "LibreOffice conversion failed"
                ),
            )

    except Exception as exc:

        update_job_status(
            job_id,
            "failed",
            0,
            "Conversion failed",
            error=str(exc),
        )

    finally:

        if input_path.exists():
            input_path.unlink()


# ============================================================
# Single File Compression
# ============================================================

@app.post("/api/compress/file")
async def compress_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    quality: int = Form(85),
    max_dimension: int = Form(1920),
):

    validate_quality(quality)
    validate_max_dimension(max_dimension)

    filename = safe_filename(file.filename)

    job_id = str(uuid.uuid4())

    jobs[job_id] = JobStatus(
        job_id=job_id,
        status="pending",
        progress=0,
        message="Job created",
    )

    input_path = (
        UPLOAD_DIR /
        f"{job_id}_{filename}"
    )

    try:

        await save_upload_file(
            file,
            input_path,
        )

    except HTTPException:
        jobs.pop(job_id, None)
        raise

    file_type = get_file_type(input_path)

    output_filename = (
        f"compressed_{filename}"
    )

    output_path = (
        OUTPUT_DIR /
        f"{job_id}_{output_filename}"
    )

    background_tasks.add_task(
        process_file_compression,
        job_id,
        input_path,
        output_path,
        output_filename,
        file_type,
        quality,
        max_dimension,
    )

    return {
        "job_id": job_id,
        "message": "Compression started",
    }


# ============================================================
# Single File Compression Worker
# ============================================================

async def process_file_compression(
    job_id: str,
    input_path: Path,
    output_path: Path,
    output_filename: str,
    file_type: str,
    quality: int,
    max_dimension: int,
):

    try:

        update_job_status(
            job_id,
            "processing",
            10,
            "Analyzing file...",
        )

        result = {
            "success": False,
        }

        # Image
        if file_type.startswith("image/"):

            update_job_status(
                job_id,
                "processing",
                30,
                "Compressing image...",
            )

            result = await compress_image(
                input_path,
                output_path,
                quality,
                max_dimension,
            )

        # PDF
        elif file_type == "application/pdf":

            update_job_status(
                job_id,
                "processing",
                30,
                "Compressing PDF...",
            )

            result = await compress_pdf(
                input_path,
                output_path,
                quality,
            )

        # DOCX
        elif file_type == (
            "application/vnd.openxmlformats-"
            "officedocument.wordprocessingml.document"
        ):

            update_job_status(
                job_id,
                "processing",
                30,
                "Compressing DOCX...",
            )

            result = await compress_docx(
                input_path,
                output_path,
                quality,
            )

        # DOC
        elif file_type == "application/msword":

            # Old .doc files cannot safely be modified
            # using python-docx.
            update_job_status(
                job_id,
                "failed",
                0,
                "Old DOC compression is not supported",
                error=(
                    "Please convert the DOC file to DOCX first."
                ),
            )

            return

        # Unknown
        else:

            update_job_status(
                job_id,
                "processing",
                30,
                "Creating ZIP archive...",
            )

            zip_output_filename = (
                f"compressed_{Path(filename_from_path(input_path)).stem}.zip"
            )

            zip_output_path = (
                OUTPUT_DIR /
                f"{job_id}_{zip_output_filename}"
            )

            result = await create_zip_archive(
                [input_path],
                zip_output_path,
            )

            if result.get("success"):
                output_filename = zip_output_filename
                output_path = zip_output_path

        if result.get("success") and output_path.exists():

            reduction = result.get(
                "reduction_percent",
                0,
            )

            update_job_status(
                job_id,
                "completed",
                100,
                f"Compression completed. "
                f"Reduced by {reduction}%",
                [output_filename],
            )

        else:

            update_job_status(
                job_id,
                "failed",
                0,
                "Compression failed",
                error=result.get(
                    "error",
                    "Unknown error",
                ),
            )

    except Exception as exc:

        update_job_status(
            job_id,
            "failed",
            0,
            "Compression failed",
            error=str(exc),
        )

    finally:

        if input_path.exists():
            input_path.unlink()


def filename_from_path(path: Path) -> str:
    return path.name


# ============================================================
# Batch Compression
# ============================================================

@app.post("/api/compress/batch")
async def compress_batch(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    quality: int = Form(85),
    create_zip: bool = Form(True),
):

    validate_quality(quality)

    if not files:
        raise HTTPException(
            status_code=400,
            detail="At least one file is required",
        )

    job_id = str(uuid.uuid4())

    jobs[job_id] = JobStatus(
        job_id=job_id,
        status="pending",
        progress=0,
        message="Job created",
    )

    input_paths = []

    try:

        for file in files:

            filename = safe_filename(
                file.filename
            )

            input_path = (
                UPLOAD_DIR /
                f"{job_id}_{filename}"
            )

            await save_upload_file(
                file,
                input_path,
            )

            input_paths.append(input_path)

    except HTTPException:

        for path in input_paths:
            if path.exists():
                path.unlink()

        jobs.pop(job_id, None)

        raise

    if create_zip:

        output_filename = (
            f"compressed_batch_{job_id[:8]}.zip"
        )

        output_path = (
            OUTPUT_DIR /
            f"{job_id}_{output_filename}"
        )

        background_tasks.add_task(
            process_batch_compression,
            job_id,
            input_paths,
            output_path,
            output_filename,
            quality,
            True,
        )

    else:

        background_tasks.add_task(
            process_batch_compression,
            job_id,
            input_paths,
            None,
            None,
            quality,
            False,
        )

    return {
        "job_id": job_id,
        "message": "Batch compression started",
    }


# ============================================================
# Batch Compression Worker
# ============================================================

async def process_batch_compression(
    job_id: str,
    input_paths: List[Path],
    output_path: Optional[Path],
    output_filename: Optional[str],
    quality: int,
    create_zip: bool,
):

    try:

        update_job_status(
            job_id,
            "processing",
            10,
            f"Processing {len(input_paths)} files...",
        )

        result_files = []

        total_original = 0
        total_compressed = 0

        if create_zip:

            result = await create_zip_archive(
                input_paths,
                output_path,
            )

            if result.get("success"):

                result_files = [
                    output_filename
                ]

                total_original = result.get(
                    "original_size",
                    0,
                )

                total_compressed = result.get(
                    "compressed_size",
                    0,
                )

        else:

            for index, input_path in enumerate(
                input_paths
            ):

                file_type = get_file_type(
                    input_path
                )

                original_name = input_path.name

                if "_" in original_name:
                    original_name = original_name.split(
                        "_",
                        1,
                    )[1]

                out_filename = (
                    f"compressed_{original_name}"
                )

                out_path = (
                    OUTPUT_DIR /
                    f"{job_id}_{out_filename}"
                )

                result = {
                    "success": False
                }

                if file_type.startswith("image/"):

                    result = await compress_image(
                        input_path,
                        out_path,
                        quality,
                    )

                elif file_type == "application/pdf":

                    result = await compress_pdf(
                        input_path,
                        out_path,
                        quality,
                    )

                elif file_type == (
                    "application/vnd.openxmlformats-"
                    "officedocument.wordprocessingml.document"
                ):

                    result = await compress_docx(
                        input_path,
                        out_path,
                        quality,
                    )

                else:

                    zip_filename = (
                        f"compressed_"
                        f"{Path(original_name).stem}.zip"
                    )

                    zip_path = (
                        OUTPUT_DIR /
                        f"{job_id}_{zip_filename}"
                    )

                    result = await create_zip_archive(
                        [input_path],
                        zip_path,
                    )

                    if result.get("success"):
                        out_filename = zip_filename
                        out_path = zip_path

                if (
                    result.get("success")
                    and out_path.exists()
                ):

                    result_files.append(
                        out_filename
                    )

                    total_original += result.get(
                        "original_size",
                        0,
                    )

                    total_compressed += result.get(
                        "compressed_size",
                        0,
                    )

                progress = (
                    10
                    + int(
                        (index + 1)
                        / len(input_paths)
                        * 80
                    )
                )

                update_job_status(
                    job_id,
                    "processing",
                    progress,
                    (
                        f"Processed "
                        f"{index + 1}/"
                        f"{len(input_paths)} files"
                    ),
                )

        if result_files:

            reduction = 0

            if total_original > 0:
                reduction = round(
                    (
                        1
                        - total_compressed
                        / total_original
                    )
                    * 100,
                    2,
                )

            update_job_status(
                job_id,
                "completed",
                100,
                (
                    "Batch compression completed. "
                    f"Reduced by {reduction}%"
                ),
                result_files,
            )

        else:

            update_job_status(
                job_id,
                "failed",
                0,
                "All compressions failed",
                error="No files were successfully processed",
            )

    except Exception as exc:

        update_job_status(
            job_id,
            "failed",
            0,
            "Batch compression failed",
            error=str(exc),
        )

    finally:

        for path in input_paths:

            if path.exists():
                path.unlink()


# ============================================================
# Job Status
# ============================================================

@app.get("/api/status/{job_id}")
async def get_job_status(job_id: str):

    if job_id not in jobs:

        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    return jobs[job_id]


# ============================================================
# Download
# ============================================================

@app.get("/api/download/{file_id}")
async def download_file(file_id: str):

    # Prevent path traversal
    safe_file_id = Path(file_id).name

    if safe_file_id != file_id:
        raise HTTPException(
            status_code=400,
            detail="Invalid file ID",
        )

    for file_path in OUTPUT_DIR.glob(
        f"{safe_file_id}_*"
    ):

        if file_path.is_file():

            download_name = file_path.name.replace(
                f"{safe_file_id}_",
                "",
                1,
            )

            return FileResponse(
                path=str(file_path),
                filename=download_name,
                media_type="application/octet-stream",
            )

    raise HTTPException(
        status_code=404,
        detail="File not found",
    )


# ============================================================
# Run Application
# ============================================================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
    )
