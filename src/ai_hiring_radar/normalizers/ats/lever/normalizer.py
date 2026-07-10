from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_hiring_radar.classify import (
    classify_role,
    clean_text,
    is_ai_role_title_candidate,
    normalize_job_title,
)
from ai_hiring_radar.country_inference import infer_countries_from_locations
from ai_hiring_radar.hashing import stable_sha256
from ai_hiring_radar.models import EvidenceQuality, SourceMode, SourceName
from ai_hiring_radar.normalizers.common.company import (
    company_name_from_slug,
    normalize_company_name,
)
from ai_hiring_radar.normalizers.common.roles import ats_role_search_term
from ai_hiring_radar.normalizers.common.text import (
    append_clean_unique,
    clean_optional,
    first_or_empty,
    first_value,
)


def _lever_postings(response: Any) -> list[dict[str, Any]]:
    if not isinstance(response, list):
        return []
    return [item for item in response if isinstance(item, dict)]


def _lever_categories(job: dict[str, Any]) -> dict[str, Any]:
    categories = job.get("categories")
    if not isinstance(categories, dict):
        return {}
    return categories


def _lever_location(job: dict[str, Any]) -> str | None:
    return clean_optional(_lever_categories(job).get("location"))


def _lever_description(job: dict[str, Any]) -> str | None:
    return clean_optional(
        job.get("description")
        or job.get("descriptionBody")
        or job.get("additional")
        or job.get("descriptionPlain")
    )


def normalize_lever_posting(
    *,
    metadata: dict[str, Any],
    job: dict[str, Any],
    raw_file: Path,
) -> dict[str, Any] | None:
    job_title_raw = clean_optional(job.get("text") or job.get("title"))
    if job_title_raw is None:
        return None
    if not is_ai_role_title_candidate(job_title_raw):
        return None

    platform_company_slug = clean_text(metadata.get("platform_company_slug"))
    if not platform_company_slug:
        return None

    board_url = clean_text(metadata.get("board_url")) or (
        f"https://jobs.lever.co/{platform_company_slug}"
    )
    location = _lever_location(job)
    platform_job_id = clean_text(job.get("id")) or stable_sha256(
        (str(SourceName.LEVER), platform_company_slug, job_title_raw, location)
    )
    role_search_term = ats_role_search_term(job_title_raw)
    job_title_normalized = normalize_job_title(
        job_title_raw,
        role_search_term=role_search_term,
    )
    role_group = classify_role(
        job_title_raw=job_title_raw,
        job_title_normalized=job_title_normalized,
        role_search_term=role_search_term,
    )

    categories = _lever_categories(job)
    source_url = clean_optional(job.get("hostedUrl")) or board_url
    company_raw = company_name_from_slug(platform_company_slug)
    company_normalized = normalize_company_name(company_raw)
    location_values: list[str] = []
    append_clean_unique(location_values, location)
    country_inference = infer_countries_from_locations(location_values)

    return {
        "record_type": "job_candidate",
        "job_id": stable_sha256(
            (str(SourceName.LEVER), platform_company_slug, platform_job_id)
        ),
        "country_code": first_or_empty(country_inference.country_codes),
        "country": first_value(country_inference.countries),
        "job_country_codes": country_inference.country_codes,
        "job_countries": country_inference.countries,
        "search_location_label": clean_optional(metadata.get("search_location_label")),
        "query_location": clean_optional(metadata.get("query_location")),
        "serper_location": clean_optional(metadata.get("serper_location")),
        "source": str(SourceName.LEVER),
        "source_mode": str(SourceMode.PUBLIC_JOB_BOARD_ENDPOINT),
        "source_url": source_url,
        "board_url": board_url,
        "job_url": source_url,
        "apply_url": clean_optional(job.get("applyUrl")),
        "platform": str(SourceName.LEVER),
        "platform_company_slug": platform_company_slug,
        "platform_job_id": platform_job_id,
        "result_rank": None,
        "displayed_link": None,
        "company_raw": company_raw,
        "company_normalized": company_normalized,
        "job_title_raw": job_title_raw,
        "job_title_normalized": job_title_normalized,
        "role_search_term": role_search_term,
        "role_group": role_group,
        "search_query": None,
        "snippet": None,
        "team": clean_optional(categories.get("team") or categories.get("department")),
        "department": clean_optional(categories.get("department")),
        "location": location,
        "job_location_raw": location,
        "job_locations_raw": location_values,
        "employment_type": clean_optional(categories.get("commitment")),
        "description": _lever_description(job),
        "description_plain": clean_optional(job.get("descriptionPlain")),
        "lists": job.get("lists") if isinstance(job.get("lists"), list) else [],
        "source_created_at": clean_optional(job.get("createdAt")),
        "evidence_quality": str(EvidenceQuality.TITLE_ONLY_ATS_LISTING),
        "needs_review": True,
        "collected_at": clean_optional(metadata.get("collected_at")),
        "raw_file": raw_file.as_posix(),
    }


def normalize_response(
    *,
    metadata: dict[str, Any],
    response: Any,
    raw_file: Path,
) -> list[dict[str, Any]]:
    return [
        candidate
        for job in _lever_postings(response)
        if (
            candidate := normalize_lever_posting(
                metadata=metadata,
                job=job,
                raw_file=raw_file,
            )
        )
        is not None
    ]
