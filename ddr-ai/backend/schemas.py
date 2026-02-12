"""Pydantic schemas that enforce strict DDR output structure."""

from __future__ import annotations

from typing import Dict, List

from pydantic import BaseModel, Field, field_validator


MISSING_VALUE_ALIASES = {
    "n/a",
    "na",
    "none",
    "null",
    "unknown",
    "not provided",
    "missing",
}


def _validate_non_empty(value: str, field_name: str) -> str:
    """Ensure values are present and normalize whitespace."""
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} cannot be empty.")
    if cleaned.lower() in MISSING_VALUE_ALIASES:
        raise ValueError(
            f"{field_name} uses an invalid missing marker. Use 'Not Available' instead."
        )
    return cleaned


class AreaObservation(BaseModel):
    """Area-specific merged findings built from both reports."""

    inspection_observation: str = Field(..., description="Observation from inspection data.")
    thermal_observation: str = Field(..., description="Observation from thermal data.")
    merged_finding: str = Field(..., description="Combined area-level diagnostic statement.")
    dampness_type: str = Field(
        default="Not Available",
        description=(
            "Rising Damp | Penetrating Damp | Plumbing Leakage Damp with optional "
            "'(Probable)' qualifier | Not Available"
        ),
    )
    inspection_evidence_ref: str = Field(
        default="Not Available",
        description="Inspection section/table/checklist reference when available.",
    )
    thermal_evidence_ref: str = Field(
        default="Not Available",
        description="Thermal image/reference when available.",
    )
    conflict_note: str = Field(
        default="Not Available",
        description="Explicitly describes conflicts if inspection and thermal disagree.",
    )

    @field_validator(
        "inspection_observation",
        "thermal_observation",
        "merged_finding",
        "dampness_type",
        "inspection_evidence_ref",
        "thermal_evidence_ref",
        "conflict_note",
    )
    @classmethod
    def validate_strings(cls, value: str, info) -> str:
        """Apply consistent string validation to all text fields."""
        return _validate_non_empty(value, info.field_name)

    @field_validator("dampness_type")
    @classmethod
    def validate_dampness_type(cls, value: str) -> str:
        """Constrain dampness type labels with support for multiple comma-separated labels."""
        allowed = {
            "rising damp",
            "rising damp (probable)",
            "penetrating damp",
            "penetrating damp (probable)",
            "plumbing leakage damp",
            "plumbing leakage damp (probable)",
            "not available",
        }
        parts = [part.strip().lower() for part in value.split(",")]
        if not parts:
            raise ValueError("dampness_type cannot be empty.")
        for part in parts:
            if part not in allowed:
                raise ValueError(
                    "dampness_type must use Rising/Penetrating/Plumbing Leakage Damp with optional "
                    "'(Probable)', or Not Available."
                )
        return value


class SeverityAssessment(BaseModel):
    """Overall severity assessment with justification."""

    overall_severity: str = Field(..., description="Low | Medium | High | Critical")
    reasoning: str = Field(..., description="Reasoning for assigned severity.")
    Confidence_Level: str = Field(..., description="High | Medium | Low | Not Available")
    Confidence_Reasoning: str = Field(
        ...,
        description=(
            "Confidence basis: multiple inspection observations, thermal confirmation, "
            "or single-source evidence."
        ),
    )

    @field_validator("overall_severity", "reasoning", "Confidence_Level", "Confidence_Reasoning")
    @classmethod
    def validate_strings(cls, value: str, info) -> str:
        """Ensure severity fields are non-empty and normalized."""
        return _validate_non_empty(value, info.field_name)

    @field_validator("overall_severity")
    @classmethod
    def validate_overall_severity(cls, value: str) -> str:
        """Constrain severity labels to diagnostic scale."""
        allowed = {
            "low",
            "low to moderate",
            "moderate",
            "moderate to high",
            "high",
            "not available",
        }
        if value.strip().lower() not in allowed:
            raise ValueError(
                "overall_severity must be Low, Low to Moderate, Moderate, Moderate to High, High, or Not Available."
            )
        return value

    @field_validator("Confidence_Level")
    @classmethod
    def validate_confidence_level(cls, value: str) -> str:
        """Constrain confidence level to approved labels."""
        allowed = {"high", "medium", "low", "not available"}
        if value.strip().lower() not in allowed:
            raise ValueError("Confidence_Level must be High, Medium, Low, or Not Available.")
        return value


class DDRReport(BaseModel):
    """Strict final response schema for the generated detailed diagnostic report."""

    Property_Issue_Summary: str
    Area_Wise_Observations: Dict[str, AreaObservation]
    Probable_Root_Cause: str
    Severity_Assessment: SeverityAssessment
    Recommended_Actions: str
    Risk_Implications: str
    Additional_Notes: str
    Missing_or_Unclear_Information: List[str]

    @field_validator(
        "Property_Issue_Summary",
        "Probable_Root_Cause",
        "Recommended_Actions",
        "Risk_Implications",
        "Additional_Notes",
    )
    @classmethod
    def validate_core_strings(cls, value: str, info) -> str:
        """Enforce non-empty text and approved missing marker."""
        return _validate_non_empty(value, info.field_name)

    @field_validator("Area_Wise_Observations")
    @classmethod
    def validate_area_observations(cls, value: Dict[str, AreaObservation]) -> Dict[str, AreaObservation]:
        """Ensure area dictionary keys are valid and placeholders are excluded."""
        for key in value.keys():
            if not key or not key.strip():
                raise ValueError("Area_Wise_Observations contains an empty area name.")
            if key.strip().lower() == "general":
                area = value[key]
                if (
                    area.inspection_observation.strip() == "Not Available"
                    and area.thermal_observation.strip() == "Not Available"
                    and area.merged_finding.strip() == "Not Available"
                ):
                    raise ValueError("Placeholder 'General' area with no valid observations is not allowed.")
        return value

    @field_validator("Missing_or_Unclear_Information")
    @classmethod
    def validate_missing_info_list(cls, value: List[str]) -> List[str]:
        """Validate each missing/unclear item is a non-empty statement."""
        cleaned_items: List[str] = []
        for item in value:
            cleaned = item.strip()
            if not cleaned:
                raise ValueError("Missing_or_Unclear_Information contains an empty item.")
            cleaned_items.append(cleaned)
        return cleaned_items
