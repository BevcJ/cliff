from __future__ import annotations

from typing import Any

from ai_hiring_radar.company_enrichment.constants import (
    COMPANY_ENRICHMENT_RECORD_TYPE,
    ENRICHMENT_VERSION,
    PROMPT_VERSION,
)
from ai_hiring_radar.company_enrichment.contracts import CompanyEnrichment
from ai_hiring_radar.company_enrichment.text import clean_scalar, normalize_source_urls
from ai_hiring_radar.llm_usage import LLMCostEstimate, LLMUsage, llm_record_metadata
from ai_hiring_radar.storage_json import slugify


FIELD_SOURCE_URL_KEYS = (
    "company_description_source_urls",
    "industry_source_urls",
    "company_size_source_urls",
    "founded_year_source_urls",
    "company_type_source_urls",
    "funding_summary_source_urls",
    "ai_tech_forward_source_urls",
)


def build_enrichment_record(
    *,
    company_record: dict[str, Any],
    enrichment: CompanyEnrichment,
    model: str,
    enriched_at: str,
    quality_warnings: tuple[str, ...] | list[str] = (),
    llm_usage: LLMUsage | None = None,
    llm_cost: LLMCostEstimate | None = None,
) -> dict[str, Any]:
    enrichment_dump = enrichment.model_dump(mode="json")
    company = clean_scalar(company_record.get("company"))

    record = {
        "record_type": COMPANY_ENRICHMENT_RECORD_TYPE,
        "enrichment_version": ENRICHMENT_VERSION,
        "prompt_version": PROMPT_VERSION,
        "model": model,
        "company": company,
        "company_key": slugify(company or "unknown"),
        "countries": _clean_sequence(company_record.get("countries")),
        "role_classification": clean_scalar(company_record.get("role_classification")),
        "ai_execution_titles": _clean_sequence(company_record.get("ai_execution_titles")),
        "ai_product_titles": _clean_sequence(company_record.get("ai_product_titles")),
        "ai_role_title_counts": _clean_mapping_sequence(
            company_record.get("ai_role_title_counts")
        ),
        "evidence_urls": normalize_source_urls(company_record.get("evidence_urls")),
        "company_description": enrichment_dump["company_description"],
        "company_description_source_urls": enrichment_dump[
            "company_description_source_urls"
        ],
        "industry": enrichment_dump["industry"],
        "industry_source_urls": enrichment_dump["industry_source_urls"],
        "company_size": enrichment_dump["company_size"],
        "company_size_source_urls": enrichment_dump["company_size_source_urls"],
        "founded_year": enrichment_dump["founded_year"],
        "founded_year_source_urls": enrichment_dump["founded_year_source_urls"],
        "company_type": enrichment_dump["company_type"],
        "company_type_source_urls": enrichment_dump["company_type_source_urls"],
        "funding_summary": enrichment_dump["funding_summary"],
        "funding_summary_source_urls": enrichment_dump["funding_summary_source_urls"],
        "ai_tech_forward_signal": enrichment_dump["ai_tech_forward_signal"],
        "ai_tech_forward_reason": enrichment_dump["ai_tech_forward_reason"],
        "ai_tech_forward_source_urls": enrichment_dump[
            "ai_tech_forward_source_urls"
        ],
        "contacts": enrichment_dump["contacts"],
        "source_urls": _source_url_union(enrichment_dump),
        "quality_warnings": list(quality_warnings),
        "enriched_at": enriched_at,
    }
    record.update(llm_record_metadata(usage=llm_usage, cost=llm_cost))
    return record


def _source_url_union(enrichment_dump: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for field in FIELD_SOURCE_URL_KEYS:
        values.extend(enrichment_dump.get(field, []))

    for contact in enrichment_dump.get("contacts", []):
        if isinstance(contact, dict):
            values.extend(contact.get("source_urls", []))

    values.extend(enrichment_dump.get("source_urls", []))
    return normalize_source_urls(values)


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
        compact = {key: item for key, item in value.items() if item is not None}
        if compact:
            items.append(compact)
    return items
