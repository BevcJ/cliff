from __future__ import annotations

from typing import Any

from ai_hiring_radar.company_enrichment.text import clean_scalar, first_clean, has_value
from ai_hiring_radar.hashing import normalize_hash_part


COMPANY_SEQUENCE_FIELDS = (
    "countries",
    "ai_execution_titles",
    "ai_product_titles",
    "matched_search_terms",
    "evidence_urls",
    "sources",
)
COMPANY_MAPPING_SEQUENCE_FIELDS = ("ai_role_title_counts",)
CANDIDATE_CONTEXT_FIELDS = (
    "job_title_raw",
    "job_url",
    "platform",
    "location",
    "team",
    "department",
)


def company_record_key(company_record: dict[str, Any]) -> str:
    return normalize_hash_part(clean_scalar(company_record.get("company")))


def group_candidate_records_by_company(
    raw_candidates: list[Any],
) -> dict[str, list[dict[str, Any]]]:
    candidates_by_company: dict[str, list[dict[str, Any]]] = {}
    for raw_candidate in raw_candidates:
        if not isinstance(raw_candidate, dict):
            continue
        company_key = _candidate_company_key(raw_candidate)
        if not company_key:
            continue
        candidates_by_company.setdefault(company_key, []).append(raw_candidate)
    return candidates_by_company


def build_enrichment_input(
    company_record: dict[str, Any],
    candidate_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    company = clean_scalar(company_record.get("company"))
    if company is None:
        return None

    enrichment_input: dict[str, Any] = {"company": company}
    _add_scalar_company_fields(enrichment_input, company_record)
    _add_sequence_company_fields(enrichment_input, company_record)
    _add_mapping_sequence_company_fields(enrichment_input, company_record)

    candidate_context = _candidate_contexts(candidate_records or [])
    if candidate_context:
        enrichment_input["candidate_context"] = candidate_context

    return enrichment_input


def _candidate_company_key(candidate: dict[str, Any]) -> str:
    return normalize_hash_part(first_clean(candidate, "company_normalized", "company"))


def _add_scalar_company_fields(
    enrichment_input: dict[str, Any],
    company_record: dict[str, Any],
) -> None:
    value = clean_scalar(company_record.get("role_classification"))
    if value is not None:
        enrichment_input["role_classification"] = value


def _add_sequence_company_fields(
    enrichment_input: dict[str, Any],
    company_record: dict[str, Any],
) -> None:
    for field in COMPANY_SEQUENCE_FIELDS:
        values = _clean_sequence(company_record.get(field))
        if values:
            enrichment_input[field] = values


def _add_mapping_sequence_company_fields(
    enrichment_input: dict[str, Any],
    company_record: dict[str, Any],
) -> None:
    for field in COMPANY_MAPPING_SEQUENCE_FIELDS:
        values = _clean_mapping_sequence(company_record.get(field))
        if values:
            enrichment_input[field] = values


def _candidate_contexts(candidate_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    for candidate in candidate_records:
        context = _candidate_context(candidate)
        if context and context not in contexts:
            contexts.append(context)
    return contexts


def _candidate_context(candidate: dict[str, Any]) -> dict[str, Any]:
    context: dict[str, Any] = {}
    for field in CANDIDATE_CONTEXT_FIELDS:
        if field == "job_url":
            value = first_clean(candidate, "job_url", "source_url")
        elif field == "platform":
            value = first_clean(candidate, "platform", "source")
        else:
            value = clean_scalar(candidate.get(field))
        if value is not None:
            context[field] = value
    return context


def _clean_sequence(values: object | None) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        return []

    items: list[str] = []
    for value in values:
        cleaned = clean_scalar(value)
        if cleaned is not None and cleaned not in items:
            items.append(cleaned)
    return items


def _clean_mapping_sequence(values: object | None) -> list[dict[str, Any]]:
    if not isinstance(values, (list, tuple)):
        return []

    items: list[dict[str, Any]] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        compact = {key: item for key, item in value.items() if has_value(item)}
        if compact:
            items.append(compact)
    return items
