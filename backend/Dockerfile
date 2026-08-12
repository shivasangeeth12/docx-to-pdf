import asyncio
import io
import shutil
import uuid
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

import fitz
import magic
from docx import Document
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import BaseModel, Field


# ============================================================
# Configuration
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
TEMP_DIR = BASE_DIR / "temp"

MAX_FILE_SIZE = 100 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

jobs = {}


# ============================================================
# Models
# ============================================================

class JobStatus(BaseModel):
    job_id: str
    status: str
    progress: int
    message: str
    result_files: List[str] = Field(default_factory=list)
    error: Optional[str] = None


# ============================================================
# Utilities
# ============================================================

def safe_filename(filename: Optional[str]) -> str:
    if not filename:
        return "uploaded_file"

    filename = Path(filename).name

    filename = "".join(
        c if c.isalnum() or c in "._-" else "_"
        for c in filename
    )

    return filename or "uploaded_file"


def validate_quality(quality: int):
    if not 1 <= quality <= 100:
        raise HTTPException(
            status_code=400,
            detail="Quality must be between 1 and 100",
        )


def validate_dimension(max_dimension: int):
    if not 100 <= max_dimension <= 10000:
        raise HTTPException(
            status_code=400,
            detail="Max dimension must be between 100 and 10000",
        )


async def save_upload_file(
    file: UploadFile,
    destination: Path,
):
    total_size = 0

    try:
        with open(destination, "wb") as output:

            while True:
                chunk = await file.read(CHUNK_SIZE)

                if not chunk:
                    break

                total_size += len(chunk)

                if total_size > MAX_FILE_SIZE:
                    output.close()

                    if destination.exists():
                        destination.unlink()

                    raise HTTPException(
                        status_code=413,
                        detail="File size exceeds 100 MB limit",
                    )

                output.write(chunk)

    finally:
        await file.close()

    return total_size


def get_file_type(path: Path) -> str:
    try:
        detector = magic.Magic(mime=True)
        return detector.from_file(str(path))
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

async def convert_with_libreoffice(
    input_path: Path,
    output_path: Path,
) -> bool:

    try:

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
            print(stderr.decode(errors="ignore"))
            return False

        generated = (
            output_path.parent /
            f"{input_path.stem}.pdf"
        )

        if not generated.exists():
            return False

        if generated != output_path:
            if output_path.exists():
                output_path.unlink()

            shutil.move(
                str(generated),
                str(output_path),
            )

        return output_path.exists()

    except Exception as exc:
        print(f"LibreOffice error: {exc}")
        return False


async def fallback_docx_to_pdf(
    input_path: Path,
    output_path: Path,
) -> bool:

    if input_path.suffix.lower() != ".docx":
        return False

    try:

        document = Document(input_path)

        pdf = fitz.open()
        page = pdf.new_page()

        x = 50
        y = 50

        for paragraph in document.paragraphs:

            text = paragraph.text.strip()

            if not text:
                continue

            if y > 750:
                page = pdf.new_page()
                y = 50

            page.insert_text(
                (x, y),
                text,
                fontsize=11,
            )

            y += 20

        pdf.save(str(output_path))
        pdf.close()

        return output_path.exists()

    except Exception as exc:
        print(f"Fallback conversion error: {exc}")
        return False


# ============================================================
# Image compression
# ============================================================

async def compress_image(
    input_path: Path,
    output_path: Path,
    quality: int = 85,
    max_dimension: int = 1920,
):

    try:

        original_size = input_path.stat().st_size

        with Image.open(input_path) as original:

            image = original.copy()

            if max(image.width, image.height) > max_dimension:

                ratio = (
                    max_dimension /
                    max(image.width, image.height)
                )

                new_size = (
                    max(1, int(image.width * ratio)),
                    max(1, int(image.height * ratio)),
                )

                image = image.resize(
                    new_size,
                    Image.Resampling.LANCZOS,
                )

            extension = output_path.suffix.lower()

            if extension in [".jpg", ".jpeg"]:

                if image.mode not in ["RGB", "L"]:

                    if "A" in image.getbands():

                        background = Image.new(
                            "RGB",
                            image.size,
                            "white",
                        )

                        background.paste(
                            image,
                            mask=image.getchannel("A"),
                        )

                        image = background

                    else:
                        image = image.convert("RGB")

                image.save(
                    output_path,
                    "JPEG",
                    quality=quality,
                    optimize=True,
                )

            elif extension == ".png":

                image.save(
                    output_path,
                    "PNG",
                    optimize=True,
                )

            elif extension == ".webp":

                image.save(
                    output_path,
                    "WEBP",
                    quality=quality,
                    method=6,
                )

            else:

                image.save(output_path)

        compressed_size = output_path.stat().st_size

        reduction = round(
            (1 - compressed_size / original_size) * 100,
            2,
        ) if original_size else 0

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
# PDF compression
# ============================================================

async def compress_pdf(
    input_path: Path,
    output_path: Path,
    quality: int = 85,
):

    try:

        original_size = input_path.stat().st_size

        document = fitz.open(str(input_path))

        for page in document:

            for image_info in page.get_images(full=True):

                xref = image_info[0]

                try:

                    pixmap = fitz.Pixmap(
                        document,
                        xref,
                    )

                    if pixmap.width == 0:
                        continue

                    if pixmap.n > 4:

                        rgb = fitz.Pixmap(
                            fitz.csRGB,
                            pixmap,
                        )

                    else:

                        rgb = pixmap

                    jpeg_data = rgb.tobytes(
                        "jpeg",
                        quality=quality,
                    )

                    document.update_stream(
                        xref,
                        jpeg_data,
                    )

                except Exception as image_error:

                    print(
                        f"PDF image skipped: "
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

        reduction = round(
            (1 - compressed_size / original_size) * 100,
            2,
        ) if original_size else 0

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
# DOCX compression
# ============================================================

async def compress_docx(
    input_path: Path,
    output_path: Path,
    quality: int = 85,
):

    try:

        original_size = input_path.stat().st_size

        with zipfile.ZipFile(
            input_path,
            "r",
        ) as source:

            with zipfile.ZipFile(
                output_path,
                "w",
                zipfile.ZIP_DEFLATED,
                compresslevel=9,
            ) as destination:

                for item in source.infolist():

                    data = source.read(item.filename)

                    lower_name = item.filename.lower()

                    if (
                        item.filename.startswith("word/media/")
                        and lower_name.endswith(
                            (".jpg", ".jpeg")
                        )
                    ):

                        try:

                            image = Image.open(
                                io.BytesIO(data)
                            )

                            if image.mode not in [
                                "RGB",
                                "L",
                            ]:
                                image = image.convert("RGB")

                            buffer = io.BytesIO()

                            image.save(
                                buffer,
                                format="JPEG",
                                quality=quality,
                                optimize=True,
                            )

                            data = buffer.getvalue()

                        except Exception as image_error:

                            print(
                                f"DOCX image skipped: "
                                f"{image_error}"
                            )

                    elif (
                        item.filename.startswith("word/media/")
                        and lower_name.endswith(".png")
                    ):

                        try:

                            image = Image.open(
                                io.BytesIO(data)
                            )

                            buffer = io.BytesIO()

                            image.save(
                                buffer,
                                format="PNG",
                                optimize=True,
                            )

                            data = buffer.getvalue()

                        except Exception:
                            pass

                    destination.writestr(
                        item,
                        data,
                    )

        compressed_size = output_path.stat().st_size

        reduction = round(
            (1 - compressed_size / original_size) * 100,
            2,
        ) if original_size else 0

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
# ZIP
# ============================================================

async def create_zip_archive(
    files: List[Path],
    output_path: Path,
):

    try:

        total_original = sum(
            path.stat().st_size
            for path in files
            if path.exists()
        )

        with zipfile.ZipFile(
            output_path,
            "w",
            zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:

            for path in files:

                if path.exists():

                    archive.write(
                        path,
                        arcname=path.name,
                    )

        compressed_size = output_path.stat().st_size

        reduction = round(
            (1 - compressed_size / total_original) * 100,
            2,
        ) if total_original else 0

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
# App
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):

    print("DOCX → PDF service starting...")

    yield

    print("DOCX → PDF service shutting down...")


app = FastAPI(
    title="DOCX to PDF Converter & File Compressor",
    version="2.0.0",
    lifespan=lifespan,
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# ============================================================
# Health
# ============================================================

@app.get("/health")
@app.get("/api/health")
async def health():

    return {
        "status": "healthy",
        "service": "docx-pdf-converter",
    }


# ============================================================
# Root
# ============================================================

@app.get("/")
async def root():

    return {
        "message": "DOCX to PDF Converter & File Compressor",
        "version": "2.0.0",
    }


# ============================================================
# DOCX → PDF
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

    if extension not in [".docx", ".doc"]:

        raise HTTPException(
            status_code=400,
            detail="Only DOCX and DOC files are supported",
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
        process_conversion,
        job_id,
        input_path,
        output_path,
        output_filename,
    )

    return {
        "job_id": job_id,
        "message": "Conversion started",
    }


async def process_conversion(
    job_id,
    input_path,
    output_path,
    output_filename,
):

    try:

        update_job_status(
            job_id,
            "processing",
            20,
            "Starting conversion...",
        )

        success = await convert_with_libreoffice(
            input_path,
            output_path,
        )

        if (
            not success
            and input_path.suffix.lower() == ".docx"
        ):

            update_job_status(
                job_id,
                "processing",
                60,
                "Trying fallback conversion...",
            )

            success = await fallback_docx_to_pdf(
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
                error="LibreOffice conversion failed",
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
# Single compression
# ============================================================

@app.post("/api/compress/file")
async def compress_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    quality: int = Form(85),
    max_dimension: int = Form(1920),
):

    validate_quality(quality)
    validate_dimension(max_dimension)

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

    background_tasks.add_task(
        process_compression,
        job_id,
        input_path,
        file_type,
        quality,
        max_dimension,
    )

    return {
        "job_id": job_id,
        "message": "Compression started",
    }


async def process_compression(
    job_id,
    input_path,
    file_type,
    quality,
    max_dimension,
):

    try:

        update_job_status(
            job_id,
            "processing",
            10,
            "Analyzing file...",
        )

        original_name = input_path.name

        if "_" in original_name:
            original_name = original_name.split(
                "_",
                1,
            )[1]

        extension = Path(
            original_name
        ).suffix.lower()

        if file_type.startswith("image/"):

            output_filename = (
                f"compressed_{original_name}"
            )

            output_path = (
                OUTPUT_DIR /
                f"{job_id}_{output_filename}"
            )

            result = await compress_image(
                input_path,
                output_path,
                quality,
                max_dimension,
            )

        elif file_type == "application/pdf":

            output_filename = (
                f"compressed_{original_name}"
            )

            output_path = (
                OUTPUT_DIR /
                f"{job_id}_{output_filename}"
            )

            result = await compress_pdf(
                input_path,
                output_path,
                quality,
            )

        elif (
            file_type
            == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ):

            output_filename = (
                f"compressed_{original_name}"
            )

            output_path = (
                OUTPUT_DIR /
                f"{job_id}_{output_filename}"
            )

            result = await compress_docx(
                input_path,
                output_path,
                quality,
            )

        else:

            output_filename = (
                f"compressed_{Path(original_name).stem}.zip"
            )

            output_path = (
                OUTPUT_DIR /
                f"{job_id}_{output_filename}"
            )

            result = await create_zip_archive(
                [input_path],
                output_path,
            )

        if result.get("success") and output_path.exists():

            update_job_status(
                job_id,
                "completed",
                100,
                (
                    "Compression completed. "
                    f"Reduced by "
                    f"{result.get('reduction_percent', 0)}%"
                ),
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


# ============================================================
# Batch compression
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

    background_tasks.add_task(
        process_batch,
        job_id,
        input_paths,
        quality,
        create_zip,
    )

    return {
        "job_id": job_id,
        "message": "Batch compression started",
    }


async def process_batch(
    job_id,
    input_paths,
    quality,
    create_zip,
):

    try:

        result_files = []

        total_original = 0
        total_compressed = 0

        if create_zip:

            output_filename = (
                f"compressed_batch_{job_id[:8]}.zip"
            )

            output_path = (
                OUTPUT_DIR /
                f"{job_id}_{output_filename}"
            )

            result = await create_zip_archive(
                input_paths,
                output_path,
            )

            if result.get("success"):

                result_files.append(
                    output_filename
                )

                total_original = result[
                    "original_size"
                ]

                total_compressed = result[
                    "compressed_size"
                ]

        else:

            for index, input_path in enumerate(
                input_paths
            ):

                file_type = get_file_type(
                    input_path
                )

                original_name = input_path.name

                if "_" in original_name:

                    original_name = (
                        original_name.split(
                            "_",
                            1,
                        )[1]
                    )

                if file_type.startswith("image/"):

                    output_filename = (
                        f"compressed_{original_name}"
                    )

                    output_path = (
                        OUTPUT_DIR /
                        f"{job_id}_{output_filename}"
                    )

                    result = await compress_image(
                        input_path,
                        output_path,
                        quality,
                    )

                elif file_type == "application/pdf":

                    output_filename = (
                        f"compressed_{original_name}"
                    )

                    output_path = (
                        OUTPUT_DIR /
                        f"{job_id}_{output_filename}"
                    )

                    result = await compress_pdf(
                        input_path,
                        output_path,
                        quality,
                    )

                elif (
                    file_type
                    == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                ):

                    output_filename = (
                        f"compressed_{original_name}"
                    )

                    output_path = (
                        OUTPUT_DIR /
                        f"{job_id}_{output_filename}"
                    )

                    result = await compress_docx(
                        input_path,
                        output_path,
                        quality,
                    )

                else:

                    output_filename = (
                        f"compressed_"
                        f"{Path(original_name).stem}.zip"
                    )

                    output_path = (
                        OUTPUT_DIR /
                        f"{job_id}_{output_filename}"
                    )

                    result = await create_zip_archive(
                        [input_path],
                        output_path,
                    )

                if (
                    result.get("success")
                    and output_path.exists()
                ):

                    result_files.append(
                        output_filename
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

            reduction = round(
                (
                    1
                    - total_compressed
                    / total_original
                )
                * 100,
                2,
            ) if total_original else 0

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
                "Batch compression failed",
                error="No files were processed",
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
# Status
# ============================================================

@app.get("/api/status/{job_id}")
async def get_status(job_id: str):

    if job_id not in jobs:

        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    return jobs[job_id]


# ============================================================
# Download
# ============================================================

@app.get("/api/download/{job_id}")
async def download_file(job_id: str):

    if not job_id.isalnum() and "-" not in job_id:

        raise HTTPException(
            status_code=400,
            detail="Invalid job ID",
        )

    matches = list(
        OUTPUT_DIR.glob(
            f"{job_id}_*"
        )
    )

    if not matches:

        raise HTTPException(
            status_code=404,
            detail="File not found",
        )

    file_path = matches[0]

    filename = file_path.name.replace(
        f"{job_id}_",
        "",
        1,
    )

    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/octet-stream",
    )


# ============================================================
# Run
# ============================================================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
    )
