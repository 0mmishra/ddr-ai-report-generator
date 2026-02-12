"""OpenRouter integration and strict DDR JSON validation pipeline."""

from __future__ import annotations

import json
import re
from typing import Any, Dict

import requests
from pydantic import ValidationError

from backend.config import get_openrouter_api_key, get_openrouter_model
from backend.prompts import DDR_PROMPT_TEMPLATE
from backend.schemas import DDRReport


EXPECTED_TOP_LEVEL_KEYS = {
    "Property_Issue_Summary",
    "Area_Wise_Observations",
    "Probable_Root_Cause",
    "Severity_Assessment",
    "Recommended_Actions",
    "Risk_Implications",
    "Additional_Notes",
    "Missing_or_Unclear_Information",
}

MISSING_ALIASES = {"", "n/a", "na", "null", "none", "unknown", "not provided", "missing"}
MAX_INPUT_CHARS_PER_REPORT = 20000


class LLMGenerationError(Exception):
    """Base exception for LLM generation failures."""


class LLMQuotaExceededError(LLMGenerationError):
    """Raised when OpenRouter quota or rate limits are exceeded."""


class LLMAuthError(LLMGenerationError):
    """Raised when OpenRouter API key/auth is invalid."""


def _extract_json_payload(raw_text: str) -> str:
    """Extract JSON from model output, handling accidental wrappers."""
    candidate = raw_text.strip()
    if candidate.startswith("{") and candidate.endswith("}"):
        return candidate

    fenced_match = re.search(r"\{.*\}", candidate, flags=re.DOTALL)
    if fenced_match:
        return fenced_match.group(0)

    raise ValueError("No JSON object found in model response.")


def _normalize_missing_markers(value: Any) -> Any:
    """Recursively force missing aliases to 'Not Available'."""
    if isinstance(value, dict):
        return {k: _normalize_missing_markers(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_missing_markers(item) for item in value]
    if value is None:
        return "Not Available"
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned.lower() in MISSING_ALIASES:
            return "Not Available"
        return cleaned
    return value


def _build_default_structure() -> Dict[str, Any]:
    """Create a schema-complete fallback dictionary for key completion."""
    return {
        "Property_Issue_Summary": "Not Available",
        "Area_Wise_Observations": {},
        "Probable_Root_Cause": "Not Available",
        "Severity_Assessment": {
            "overall_severity": "Not Available",
            "reasoning": "Not Available",
            "Confidence_Level": "Not Available",
            "Confidence_Reasoning": "Not Available",
        },
        "Recommended_Actions": "Not Available",
        "Risk_Implications": "Not Available",
        "Additional_Notes": "Not Available",
        "Missing_or_Unclear_Information": ["Not Available"],
    }


def _coerce_to_schema_shape(data: Dict[str, Any]) -> Dict[str, Any]:
    """Fill missing keys and ensure nested structures are present."""
    normalized = _normalize_missing_markers(data)
    completed = _build_default_structure()

    for key in EXPECTED_TOP_LEVEL_KEYS:
        if key in normalized:
            completed[key] = normalized[key]

    if not isinstance(completed.get("Area_Wise_Observations"), dict):
        completed["Area_Wise_Observations"] = {}

    if not isinstance(completed.get("Severity_Assessment"), dict):
        completed["Severity_Assessment"] = _build_default_structure()["Severity_Assessment"]
    else:
        severity = completed["Severity_Assessment"]
        severity.setdefault("overall_severity", "Not Available")
        severity.setdefault("reasoning", "Not Available")
        severity.setdefault("Confidence_Level", "Not Available")
        severity.setdefault("Confidence_Reasoning", "Not Available")
        completed["Severity_Assessment"] = _normalize_missing_markers(severity)

    if not isinstance(completed.get("Missing_or_Unclear_Information"), list):
        completed["Missing_or_Unclear_Information"] = ["Not Available"]
    elif not completed["Missing_or_Unclear_Information"]:
        completed["Missing_or_Unclear_Information"] = ["Not Available"]

    # Ensure every area has required keys and remove empty placeholder sections.
    for area, area_data in list(completed["Area_Wise_Observations"].items()):
        if not isinstance(area_data, dict):
            completed["Area_Wise_Observations"][area] = {
                "inspection_observation": "Not Available",
                "thermal_observation": "Not Available",
                "merged_finding": "Not Available",
                "dampness_type": "Not Available",
                "inspection_evidence_ref": "Not Available",
                "thermal_evidence_ref": "Not Available",
                "conflict_note": "Not Available",
            }
            continue
        area_data.setdefault("inspection_observation", "Not Available")
        area_data.setdefault("thermal_observation", "Not Available")
        area_data.setdefault("merged_finding", "Not Available")
        area_data.setdefault("dampness_type", "Not Available")
        area_data.setdefault("inspection_evidence_ref", "Not Available")
        area_data.setdefault("thermal_evidence_ref", "Not Available")
        area_data.setdefault("conflict_note", "Not Available")
        completed["Area_Wise_Observations"][area] = _normalize_missing_markers(area_data)

    # Remove placeholder "General" when it contains only missing values.
    general = completed["Area_Wise_Observations"].get("General")
    if isinstance(general, dict):
        is_placeholder_general = (
            general.get("inspection_observation") == "Not Available"
            and general.get("thermal_observation") == "Not Available"
            and general.get("merged_finding") == "Not Available"
        )
        if is_placeholder_general:
            completed["Area_Wise_Observations"].pop("General", None)

    return completed


def _extract_openrouter_error(response: requests.Response) -> str:
    """Extract the cleanest possible error message from OpenRouter responses."""
    try:
        payload = response.json()
    except ValueError:
        return response.text or "Unknown OpenRouter error."
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
        if payload.get("message"):
            return str(payload["message"])
    return str(payload)


def _call_openrouter(prompt: str) -> str:
    """Call OpenRouter Chat Completions API and return assistant content text."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {get_openrouter_api_key()}",
        "Content-Type": "application/json",
        # Helpful metadata headers for OpenRouter analytics/debugging.
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "DDR AI Report Generator",
    }
    payload = {
        "model": get_openrouter_model(),
        "temperature": 0.1,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=120,
        )
    except Exception as exc:
        raise LLMGenerationError(f"OpenRouter request failed: {exc}") from exc

    if response.status_code == 429:
        raise LLMQuotaExceededError(
            f"OpenRouter quota/rate limit exceeded (HTTP 429): {_extract_openrouter_error(response)}"
        )
    if response.status_code in (401, 403):
        raise LLMAuthError(
            f"OpenRouter authentication/authorization failed ({response.status_code}): "
            f"{_extract_openrouter_error(response)}"
        )
    if response.status_code >= 400:
        raise LLMGenerationError(
            f"OpenRouter request failed ({response.status_code}): {_extract_openrouter_error(response)}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise LLMGenerationError("OpenRouter returned non-JSON response.") from exc

    try:
        response_text = data["choices"][0]["message"]["content"]
    except Exception as exc:
        raise LLMGenerationError("OpenRouter response missing choices/message/content.") from exc

    if not isinstance(response_text, str) or not response_text.strip():
        raise LLMGenerationError("OpenRouter returned empty assistant content.")
    return response_text


def _parse_and_validate(raw_text: str) -> DDRReport:
    """Parse model output and validate strictly against DDR schema."""
    json_payload = _extract_json_payload(raw_text)
    parsed = json.loads(json_payload)
    coerced = _coerce_to_schema_shape(parsed)
    return DDRReport.model_validate(coerced)


def generate_ddr(inspection_text: str, thermal_text: str) -> DDRReport:
    """Generate a validated DDR report from both report texts with one retry."""
    inspection_slice = inspection_text[:MAX_INPUT_CHARS_PER_REPORT]
    thermal_slice = thermal_text[:MAX_INPUT_CHARS_PER_REPORT]

    # Use direct token replacement to avoid accidental formatting of JSON braces.
    base_prompt = DDR_PROMPT_TEMPLATE.replace(
        "{inspection_text}",
        inspection_slice,
    ).replace(
        "{thermal_text}",
        thermal_slice,
    )

    last_error: Exception | None = None
    retry_suffix = ""

    for attempt in range(2):
        try:
            raw_response = _call_openrouter(base_prompt + retry_suffix)
            return _parse_and_validate(raw_response)
        except (LLMQuotaExceededError, LLMAuthError):
            # Non-recoverable without external action; do not burn retry calls.
            raise
        except (json.JSONDecodeError, ValidationError, ValueError, LLMGenerationError) as exc:
            last_error = exc
            if attempt == 0:
                retry_suffix = (
                    "\n\nYour previous response was invalid. Return ONLY a valid JSON object with the exact schema."
                )
                continue
            break

    raise LLMGenerationError(f"Failed to generate a valid DDR JSON response: {last_error}") from last_error
