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


def _greenhouse_jobs(response: Any) -> list[dict[str, Any]]:
    jobs = response.get("jobs")
    if not isinstance(jobs, list):
        return []
    return [item for item in jobs if isinstance(item, dict)]


def _greenhouse_location_name(job: dict[str, Any]) -> str | None:
    location = job.get("location")
    if isinstance(location, dict):
        return clean_optional(location.get("name"))
    return clean_optional(location)


def _greenhouse_departments(job: dict[str, Any]) -> list[str]:
    departments = job.get("departments")
    if not isinstance(departments, list):
        return []

    values: list[str] = []
    for department in departments:
        if not isinstance(department, dict):
            continue
        department_name = clean_optional(department.get("name"))
        if department_name and department_name not in values:
            values.append(department_name)
    return values


def _greenhouse_office_value(value: object | None) -> str | None:
    if isinstance(value, dict):
        return clean_optional(value.get("name") or value.get("location"))
    return clean_optional(value)


def _greenhouse_offices(job: dict[str, Any]) -> list[str]:
    offices = job.get("offices")
    if not isinstance(offices, list):
        return []

    values: list[str] = []
    for office in offices:
        if not isinstance(office, dict):
            continue
        office_name = _greenhouse_office_value(office.get("location")) or clean_optional(
            office.get("name")
        )
        if office_name and office_name not in values:
            values.append(office_name)
    return values


def _greenhouse_location_values(*, location: str | None, offices: list[str]) -> list[str]:
    values: list[str] = []
    append_clean_unique(values, location)
    for office in offices:
        append_clean_unique(values, office)
    return values


def _greenhouse_country_inference(*, location: str | None, offices: list[str]):  # noqa: ANN202
    office_inference = infer_countries_from_locations(offices)
    if office_inference.country_codes:
        return office_inference
    return infer_countries_from_locations([location])


def normalize_greenhouse_job(
    *,
    metadata: dict[str, Any],
    job: dict[str, Any],
    raw_file: Path,
) -> dict[str, Any] | None:
    job_title_raw = clean_optional(job.get("title"))
    if job_title_raw is None:
        return None
    if not is_ai_role_title_candidate(job_title_raw):
        return None

    platform_company_slug = clean_text(metadata.get("platform_company_slug"))
    if not platform_company_slug:
        return None

    board_url = clean_text(metadata.get("board_url")) or (
        f"https://boards.greenhouse.io/{platform_company_slug}"
    )
    location = _greenhouse_location_name(job)
    platform_job_id = clean_text(job.get("id")) or stable_sha256(
        (str(SourceName.GREENHOUSE), platform_company_slug, job_title_raw, location)
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

    departments = _greenhouse_departments(job)
    source_url = clean_optional(job.get("absolute_url")) or board_url
    company_raw = company_name_from_slug(platform_company_slug)
    company_normalized = normalize_company_name(company_raw)
    offices = _greenhouse_offices(job)
    location_values = _greenhouse_location_values(location=location, offices=offices)
    country_inference = _greenhouse_country_inference(
        location=location,
        offices=offices,
    )

    return {
        "record_type": "job_candidate",
        "job_id": stable_sha256(
            (str(SourceName.GREENHOUSE), platform_company_slug, platform_job_id)
        ),
        "country_code": first_or_empty(country_inference.country_codes),
        "country": first_value(country_inference.countries),
        "job_country_codes": country_inference.country_codes,
        "job_countries": country_inference.countries,
        "search_location_label": clean_optional(metadata.get("search_location_label")),
        "query_location": clean_optional(metadata.get("query_location")),
        "serper_location": clean_optional(metadata.get("serper_location")),
        "source": str(SourceName.GREENHOUSE),
        "source_mode": str(SourceMode.PUBLIC_JOB_BOARD_ENDPOINT),
        "source_url": source_url,
        "board_url": board_url,
        "job_url": source_url,
        "platform": str(SourceName.GREENHOUSE),
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
        "team": departments[0] if departments else None,
        "teams": departments,
        "location": location,
        "job_location_raw": location,
        "job_locations_raw": location_values,
        "offices": offices,
        "description": clean_optional(job.get("content")),
        "compensation": job.get("pay_input_ranges"),
        "source_updated_at": clean_optional(job.get("updated_at")),
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
        for job in _greenhouse_jobs(response)
        if (
            candidate := normalize_greenhouse_job(
                metadata=metadata,
                job=job,
                raw_file=raw_file,
            )
        )
        is not None
    ]
