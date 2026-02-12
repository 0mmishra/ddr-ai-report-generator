"""FastAPI application exposing DDR generation and report download APIs."""

from __future__ import annotations

import shutil
from pathlib import Path
import os

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend.llm_engine import (
    LLMAuthError,
    LLMGenerationError,
    LLMQuotaExceededError,
    generate_ddr,
)
from backend.merger import preprocess_reports
from backend.parser import extract_text_from_pdf
from backend.report_generator import generate_docx


# ===== Production Safe Paths =====

ROOT_DIR = Path(os.getcwd())
UPLOAD_DIR = ROOT_DIR / "uploads"
OUTPUT_DIR = ROOT_DIR / "outputs"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


app = FastAPI(title="DDR AI Report Generator API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _save_upload(upload_file: UploadFile, target_path: Path) -> None:
    with target_path.open("wb") as output_stream:
        shutil.copyfileobj(upload_file.file, output_stream)


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok"}


@app.post("/generate-ddr")
async def generate_ddr_endpoint(
    inspection_file: UploadFile = File(...),
    thermal_file: UploadFile = File(...),
) -> dict:

    try:
        if not inspection_file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="inspection_file must be a PDF.")

        if not thermal_file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="thermal_file must be a PDF.")

        inspection_path = UPLOAD_DIR / f"inspection_{inspection_file.filename}"
        thermal_path = UPLOAD_DIR / f"thermal_{thermal_file.filename}"

        _save_upload(inspection_file, inspection_path)
        _save_upload(thermal_file, thermal_path)

        inspection_text = extract_text_from_pdf(str(inspection_path))
        thermal_text = extract_text_from_pdf(str(thermal_path))

        if not inspection_text.strip():
            inspection_text = "Not Available"

        if not thermal_text.strip():
            thermal_text = "Not Available"

        inspection_text, thermal_text = preprocess_reports(inspection_text, thermal_text)

        ddr_report = generate_ddr(
            inspection_text=inspection_text,
            thermal_text=thermal_text,
        )

        docx_path = generate_docx(
            ddr_report=ddr_report,
            output_dir=str(OUTPUT_DIR),
        )

        file_name = Path(docx_path).name

        return {
            "report_data": ddr_report.model_dump(),
            "download_file": file_name,  # safer for deployment
        }

    except HTTPException:
        raise

    except LLMQuotaExceededError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    except LLMAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    except LLMGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate DDR report: {exc}",
        ) from exc

    finally:
        inspection_file.file.close()
        thermal_file.file.close()


@app.get("/download-report")
def download_report(
    file_name: str = Query(..., description="DOCX file name in outputs directory")
):
    safe_name = Path(file_name).name
    file_path = OUTPUT_DIR / safe_name

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Requested report file not found.")

    return FileResponse(
        path=str(file_path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=safe_name,
    )
