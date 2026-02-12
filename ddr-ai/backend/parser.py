"""PDF parser with OCR fallback for image-based or low-text documents."""

from __future__ import annotations

import io
import re
from typing import List

import pdfplumber
import pytesseract
from PIL import Image


def _clean_text(text: str) -> str:
    """Normalize line breaks and spacing for downstream processing."""
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def _extract_with_pdfplumber(file_path: str) -> str:
    """Extract textual content from all pages using pdfplumber."""
    pages_text: List[str] = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                pages_text.append(page_text.strip())
    return _clean_text("\n".join(pages_text))


def _extract_with_ocr(file_path: str) -> str:
    """Render each PDF page as an image and apply OCR text extraction."""
    pages_text: List[str] = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_image = page.to_image(resolution=300).original
            if not isinstance(page_image, Image.Image):
                # Some backends may return raw bytes; normalize to PIL image.
                page_image = Image.open(io.BytesIO(page_image))
            ocr_text = pytesseract.image_to_string(page_image) or ""
            if ocr_text.strip():
                pages_text.append(ocr_text.strip())
    return _clean_text("\n".join(pages_text))


def extract_text_from_pdf(file_path: str) -> str:
    """Extract text from PDF with OCR fallback when native text is insufficient."""
    try:
        extracted_text = _extract_with_pdfplumber(file_path)
    except Exception as exc:
        # Keep flow resilient; caller decides how to handle empty extraction.
        extracted_text = ""

    # Heuristic threshold for deciding if OCR is needed.
    if len(extracted_text) >= 300:
        return extracted_text

    try:
        ocr_text = _extract_with_ocr(file_path)
    except Exception:
        # Return whatever text we already extracted when OCR is unavailable.
        return extracted_text

    merged = f"{extracted_text}\n{ocr_text}".strip()
    return _clean_text(merged)
