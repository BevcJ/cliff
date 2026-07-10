from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_hiring_radar.classify import classify_role, normalize_job_title
from ai_hiring_radar.country_inference import CountryInference
from ai_hiring_radar.hashing import stable_sha256
from ai_hiring_radar.models import EvidenceQuality, SourceMode, SourceName
from ai_hiring_radar.normalizers.common.company import normalize_company_name
from ai_hiring_radar.normalizers.common.roles import ats_role_search_term
from ai_hiring_radar.normalizers.common.text import clean_optional, first_or_empty, first_value


def build_ats_candidate(
    *,
    source: SourceName | str,
    metadata: dict[str, Any],
    raw_file: Path,
    platform_company_slug: str,
    platform_job_id: str,
    board_url: str,
    source_url: str,
    job_title_raw: str,
    company_raw: object | None,
    country_inference: CountryInference,
    role_search_term: str | None = None,
    job_url: str | None = None,
    location: str | None = None,
    job_locations_raw: list[str] | None = None,
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_value = str(source)
    role_search_term = role_search_term or ats_role_search_term(job_title_raw)
    job_title_normalized = normalize_job_title(
        job_title_raw,
        role_search_term=role_search_term,
    )
    role_group = classify_role(
        job_title_raw=job_title_raw,
        job_title_normalized=job_title_normalized,
        role_search_term=role_search_term,
    )
    cleaned_company_raw = clean_optional(company_raw)

    candidate: dict[str, Any] = {
        "record_type": "job_candidate",
        "job_id": stable_sha256((source_value, platform_company_slug, platform_job_id)),
        "country_code": first_or_empty(country_inference.country_codes),
        "country": first_value(country_inference.countries),
        "job_country_codes": country_inference.country_codes,
        "job_countries": country_inference.countries,
        "search_location_label": clean_optional(metadata.get("search_location_label")),
        "query_location": clean_optional(metadata.get("query_location")),
        "serper_location": clean_optional(metadata.get("serper_location")),
        "source": source_value,
        "source_mode": str(SourceMode.PUBLIC_JOB_BOARD_ENDPOINT),
        "source_url": source_url,
        "board_url": board_url,
        "job_url": job_url,
        "platform": source_value,
        "platform_company_slug": platform_company_slug,
        "platform_job_id": platform_job_id,
        "result_rank": None,
        "displayed_link": None,
        "company_raw": cleaned_company_raw,
        "company_normalized": normalize_company_name(cleaned_company_raw),
        "job_title_raw": job_title_raw,
        "job_title_normalized": job_title_normalized,
        "role_search_term": role_search_term,
        "role_group": role_group,
        "search_query": None,
        "snippet": None,
        "location": location,
        "job_location_raw": location,
        "job_locations_raw": job_locations_raw or [],
        "evidence_quality": str(EvidenceQuality.TITLE_ONLY_ATS_LISTING),
        "needs_review": True,
        "collected_at": clean_optional(metadata.get("collected_at")),
        "raw_file": raw_file.as_posix(),
    }

    if extra_fields is not None:
        conflicts = sorted(candidate.keys() & extra_fields.keys())
        if conflicts:
            raise ValueError(
                "extra_fields cannot override base ATS candidate fields: "
                + ", ".join(conflicts)
            )
        candidate.update(extra_fields)

    return candidate
