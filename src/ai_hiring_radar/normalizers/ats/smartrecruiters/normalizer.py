from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote

from ai_hiring_radar.classify import (
    classify_role,
    clean_text,
    is_ai_role_title_candidate,
    normalize_job_title,
)
from ai_hiring_radar.country_inference import (
    COUNTRY_NAMES_BY_CODE,
    CountryInference,
    infer_countries_from_locations,
)
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


def _smartrecruiters_pages(response: Any) -> list[dict[str, Any]]:
    if isinstance(response, dict):
        return [response]
    if not isinstance(response, list):
        return []
    return [item for item in response if isinstance(item, dict)]


def _smartrecruiters_postings(response: Any) -> list[dict[str, Any]]:
    postings: list[dict[str, Any]] = []
    for page in _smartrecruiters_pages(response):
        content = page.get("content")
        if not isinstance(content, list):
            continue
        postings.extend(item for item in content if isinstance(item, dict))
    return postings


def _smartrecruiters_location(job: dict[str, Any]) -> dict[str, Any]:
    location = job.get("location")
    return location if isinstance(location, dict) else {}


def _smartrecruiters_display_location(job: dict[str, Any]) -> str | None:
    location = _smartrecruiters_location(job)
    return clean_optional(location.get("fullLocation") or location.get("city"))


def _smartrecruiters_location_values(job: dict[str, Any]) -> list[str]:
    location = _smartrecruiters_location(job)
    values: list[str] = []
    append_clean_unique(values, location.get("fullLocation"))
    append_clean_unique(values, location.get("city"))
    return values


def _smartrecruiters_country_code(value: object | None) -> str | None:
    country_code = clean_text(value).casefold()
    if country_code == "gb":
        country_code = "uk"
    if country_code in COUNTRY_NAMES_BY_CODE:
        return country_code
    return None


def _smartrecruiters_country_inference(
    *,
    country: object | None,
    locations: list[str],
) -> CountryInference:
    country_code = _smartrecruiters_country_code(country)
    if country_code is not None:
        return CountryInference(
            country_codes=[country_code],
            countries=[COUNTRY_NAMES_BY_CODE[country_code]],
        )

    values: list[object | None] = [country]
    values.extend(locations)
    return infer_countries_from_locations(values)


def _smartrecruiters_workplace_type(job: dict[str, Any]) -> str | None:
    location = _smartrecruiters_location(job)
    if location.get("hybrid") is True:
        return "hybrid"
    if location.get("remote") is True:
        return "remote"
    return None


def _smartrecruiters_source_url(job: dict[str, Any], board_url: str) -> str:
    for field in (
        "postingUrl",
        "publicUrl",
        "jobUrl",
        "url",
        "applyUrl",
        "ref",
    ):
        source_url = clean_optional(job.get(field))
        if source_url is not None:
            return source_url
    return board_url


def normalize_smartrecruiters_posting(
    *,
    metadata: dict[str, Any],
    job: dict[str, Any],
    raw_file: Path,
) -> dict[str, Any] | None:
    job_title_raw = clean_optional(job.get("name") or job.get("title"))
    if job_title_raw is None:
        return None
    if not is_ai_role_title_candidate(job_title_raw):
        return None

    platform_company_slug = clean_text(metadata.get("platform_company_slug"))
    if not platform_company_slug:
        return None

    board_url = clean_text(metadata.get("board_url")) or (
        f"https://careers.smartrecruiters.com/{quote(platform_company_slug, safe='-_~.')}"
    )
    location = _smartrecruiters_display_location(job)
    platform_job_id = clean_text(job.get("id")) or stable_sha256(
        (str(SourceName.SMARTRECRUITERS), platform_company_slug, job_title_raw, location)
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

    location_data = _smartrecruiters_location(job)
    location_values = _smartrecruiters_location_values(job)
    country_inference = _smartrecruiters_country_inference(
        country=location_data.get("country"),
        locations=location_values,
    )
    source_url = _smartrecruiters_source_url(job, board_url)
    company_raw = company_name_from_slug(platform_company_slug)
    company_normalized = normalize_company_name(company_raw)

    return {
        "record_type": "job_candidate",
        "job_id": stable_sha256(
            (str(SourceName.SMARTRECRUITERS), platform_company_slug, platform_job_id)
        ),
        "country_code": first_or_empty(country_inference.country_codes),
        "country": first_value(country_inference.countries),
        "job_country_codes": country_inference.country_codes,
        "job_countries": country_inference.countries,
        "search_location_label": clean_optional(metadata.get("search_location_label")),
        "query_location": clean_optional(metadata.get("query_location")),
        "serper_location": clean_optional(metadata.get("serper_location")),
        "source": str(SourceName.SMARTRECRUITERS),
        "source_mode": str(SourceMode.PUBLIC_JOB_BOARD_ENDPOINT),
        "source_url": source_url,
        "board_url": board_url,
        "job_url": source_url if source_url != board_url else None,
        "api_ref": clean_optional(job.get("ref")),
        "platform": str(SourceName.SMARTRECRUITERS),
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
        "location": location,
        "job_location_raw": location,
        "job_locations_raw": location_values,
        "location_country_raw": clean_optional(location_data.get("country")),
        "workplace_type": _smartrecruiters_workplace_type(job),
        "remote": location_data.get("remote") if isinstance(location_data.get("remote"), bool) else None,
        "hybrid": location_data.get("hybrid") if isinstance(location_data.get("hybrid"), bool) else None,
        "source_created_at": clean_optional(
            job.get("releasedDate") or job.get("createdOn") or job.get("publishedOn")
        ),
        "source_updated_at": clean_optional(job.get("updatedOn") or job.get("updatedAt")),
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
        for job in _smartrecruiters_postings(response)
        if (
            candidate := normalize_smartrecruiters_posting(
                metadata=metadata,
                job=job,
                raw_file=raw_file,
            )
        )
        is not None
    ]
