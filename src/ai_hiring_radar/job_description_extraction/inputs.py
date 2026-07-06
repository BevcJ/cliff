from __future__ import annotations

from typing import Any

from ai_hiring_radar.job_description_extraction.dates import normalize_explicit_date
from ai_hiring_radar.job_description_extraction.text import clean_scalar, has_value


SCALAR_INPUT_FIELDS = (
    "record_type",
    "job_id",
    "source",
    "source_mode",
    "platform",
    "platform_company_slug",
    "platform_job_id",
    "company_normalized",
    "job_title_raw",
    "job_title_normalized",
    "role_search_term",
    "role_group",
    "source_url",
    "job_url",
    "board_url",
    "apply_url",
    "team",
    "parent_team",
    "department",
    "location",
    "job_location_raw",
    "workplace_type",
    "employment_type",
    "schedule",
    "recruiting_category",
    "source_created_at",
    "source_updated_at",
    "collected_at",
    "description",
    "description_plain",
)
SEQUENCE_INPUT_FIELDS = (
    "teams",
    "job_locations_raw",
    "secondary_locations",
    "offices",
    "job_description_sections",
    "lists",
)
USEFUL_INPUT_FIELDS = (
    "description",
    "description_plain",
    "job_description_sections",
    "lists",
    "workplace_type",
    "employment_type",
    "team",
    "teams",
    "parent_team",
    "department",
    "location",
    "job_location_raw",
    "job_locations_raw",
    "secondary_locations",
    "offices",
    "source_created_at",
    "source_updated_at",
    "normalized_source_dates",
    "platform",
    "platform_company_slug",
    "platform_job_id",
)


def build_extraction_input(candidate: dict[str, Any]) -> dict[str, Any] | None:
    if not clean_scalar(candidate.get("job_id")):
        return None

    extraction_input = _build_candidate_payload(candidate)
    if not _has_useful_extraction_input(extraction_input):
        return None

    return extraction_input


def _build_candidate_payload(candidate: dict[str, Any]) -> dict[str, Any]:
    extraction_input: dict[str, Any] = {}
    _add_scalar_fields(extraction_input, candidate)
    _add_sequence_fields(extraction_input, candidate)
    _add_compensation(extraction_input, candidate)
    _add_normalized_dates(extraction_input, candidate)
    return extraction_input


def _add_scalar_fields(
    extraction_input: dict[str, Any],
    candidate: dict[str, Any],
) -> None:
    for field in SCALAR_INPUT_FIELDS:
        value = candidate.get(field)
        if has_value(value):
            extraction_input[field] = value


def _add_sequence_fields(
    extraction_input: dict[str, Any],
    candidate: dict[str, Any],
) -> None:
    for field in SEQUENCE_INPUT_FIELDS:
        items = _clean_sequence(candidate.get(field))
        if items:
            extraction_input[field] = items


def _add_compensation(
    extraction_input: dict[str, Any],
    candidate: dict[str, Any],
) -> None:
    compensation = candidate.get("compensation")
    if has_value(compensation):
        extraction_input["compensation"] = compensation


def _add_normalized_dates(
    extraction_input: dict[str, Any],
    candidate: dict[str, Any],
) -> None:
    normalized_dates = {
        "posted_at": normalize_explicit_date(candidate.get("source_created_at")),
        "updated_at": normalize_explicit_date(candidate.get("source_updated_at")),
    }
    normalized_dates = {
        key: value for key, value in normalized_dates.items() if value is not None
    }
    if normalized_dates:
        extraction_input["normalized_source_dates"] = normalized_dates


def _has_useful_extraction_input(extraction_input: dict[str, Any]) -> bool:
    return any(has_value(extraction_input.get(field)) for field in USEFUL_INPUT_FIELDS)


def _clean_sequence(values: object | None) -> list[Any]:
    if not isinstance(values, list):
        return []

    items: list[Any] = []
    for value in values:
        if isinstance(value, dict):
            compact = {key: item for key, item in value.items() if has_value(item)}
            if compact:
                items.append(compact)
            continue

        cleaned = clean_scalar(value)
        if cleaned is not None and cleaned not in items:
            items.append(cleaned)
    return items
