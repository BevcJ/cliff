from __future__ import annotations

from typing import Any

from ai_hiring_radar.job_description_extraction.constants import (
    EXTRACTION_VERSION,
    JOB_DESCRIPTION_EXTRACT_RECORD_TYPE,
    PROMPT_VERSION,
)
from ai_hiring_radar.job_description_extraction.contracts import JobDescriptionExtraction
from ai_hiring_radar.job_description_extraction.dates import normalize_explicit_date
from ai_hiring_radar.job_description_extraction.text import clean_scalar, first_clean
from ai_hiring_radar.llm_usage import LLMCostEstimate, LLMUsage, llm_record_metadata


def build_extraction_record(
    *,
    candidate: dict[str, Any],
    extraction: JobDescriptionExtraction,
    model: str,
    extracted_at: str,
    llm_usage: LLMUsage | None = None,
    llm_cost: LLMCostEstimate | None = None,
) -> dict[str, Any]:
    extraction_dump = extraction.model_dump(mode="json")

    record = {
        "record_type": JOB_DESCRIPTION_EXTRACT_RECORD_TYPE,
        "extraction_version": EXTRACTION_VERSION,
        "prompt_version": PROMPT_VERSION,
        "model": model,
        "job_id": clean_scalar(candidate.get("job_id")),
        "source": clean_scalar(candidate.get("source")),
        "platform": first_clean(candidate, "platform", "source"),
        "platform_company_slug": clean_scalar(candidate.get("platform_company_slug")),
        "platform_job_id": clean_scalar(candidate.get("platform_job_id")),
        "company_normalized": clean_scalar(candidate.get("company_normalized")),
        "job_title_raw": clean_scalar(candidate.get("job_title_raw")),
        "job_url": first_clean(candidate, "job_url", "source_url"),
        "workplace_mode": extraction_dump["workplace_mode"],
        "ai_team_context": extraction_dump["ai_team_context"],
        "delivery_context": extraction_dump["delivery_context"],
        "contacts": extraction_dump["contacts"],
        "posted_at": _posted_at(candidate, extraction),
        "updated_at": _updated_at(candidate, extraction),
        "extracted_at": extracted_at,
    }
    record.update(llm_record_metadata(usage=llm_usage, cost=llm_cost))
    return record


def _posted_at(candidate: dict[str, Any], extraction: JobDescriptionExtraction) -> str | None:
    return normalize_explicit_date(extraction.posted_at) or normalize_explicit_date(
        candidate.get("source_created_at")
    )


def _updated_at(candidate: dict[str, Any], extraction: JobDescriptionExtraction) -> str | None:
    return normalize_explicit_date(extraction.updated_at) or normalize_explicit_date(
        candidate.get("source_updated_at")
    )
