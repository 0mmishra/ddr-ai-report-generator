"""Text pre-processing helpers for deduplication and normalization."""

from __future__ import annotations

import re
from typing import Iterable, List, Tuple


AREA_NORMALIZATION_MAP = {
    r"\blr\b": "living room",
    r"\bbr\b": "bedroom",
    r"\bwc\b": "washroom",
    r"\bkit\b": "kitchen",
}


def clean_whitespace(text: str) -> str:
    """Collapse repeated whitespace to keep prompts compact."""
    return re.sub(r"\s+", " ", text).strip()


def split_sentences(text: str) -> List[str]:
    """Split text into sentence-like chunks for duplicate filtering."""
    if not text.strip():
        return []
    return [segment.strip() for segment in re.split(r"(?<=[.!?])\s+", text) if segment.strip()]


def remove_repeated_sentences(text: str) -> str:
    """Drop repeated sentences while preserving first occurrence order."""
    seen = set()
    unique: List[str] = []
    for sentence in split_sentences(text):
        normalized = sentence.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(sentence)
    return " ".join(unique)


def normalize_area_names(text: str) -> str:
    """Normalize common area abbreviations to improve consistency."""
    normalized = text
    for pattern, replacement in AREA_NORMALIZATION_MAP.items():
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
    return normalized


def _normalize_pipeline(text: str, transforms: Iterable) -> str:
    """Apply all transforms in a stable pipeline."""
    output = text
    for transform in transforms:
        output = transform(output)
    return output


def preprocess_reports(inspection_text: str, thermal_text: str) -> Tuple[str, str]:
    """Apply duplicate filtering, whitespace cleanup, and area normalization."""
    transforms = [clean_whitespace, normalize_area_names, remove_repeated_sentences, clean_whitespace]
    return (
        _normalize_pipeline(inspection_text, transforms),
        _normalize_pipeline(thermal_text, transforms),
    )

