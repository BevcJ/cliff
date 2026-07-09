from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from ai_hiring_radar.classify import (
    classify_role,
    clean_text,
    has_ai_signal,
    is_excluded_ai_trainer_title,
    match_known_role,
    normalize_job_title,
)
from ai_hiring_radar.country_inference import (
    COUNTRY_NAMES_BY_CODE,
    CountryInference,
    infer_countries_from_locations,
)
from ai_hiring_radar.hashing import stable_sha256
from ai_hiring_radar.models import EvidenceQuality, SourceMode, SourceName


GENERIC_COMPANY_VALUES = {
    "careers",
    "hiring",
    "jobs",
    "linkedin",
    "remote",
}


def _clean_optional(value: object | None) -> str | None:
    cleaned = clean_text(value)
    return cleaned or None


def _append_clean_unique(values: list[str], value: object | None) -> None:
    cleaned = _clean_optional(value)
    if cleaned and cleaned not in values:
        values.append(cleaned)


def _first_value(values: list[str]) -> str | None:
    return values[0] if values else None


def _first_or_empty(values: list[str]) -> str:
    return values[0] if values else ""


def _clean_company_candidate(value: object | None) -> str | None:
    candidate = clean_text(value)
    if not candidate:
        return None

    candidate = re.sub(r"\s+is hiring\b.*$", "", candidate, flags=re.IGNORECASE)
    candidate = re.sub(r"\s*[|•].*$", "", candidate).strip()
    candidate = re.sub(r"\s+-\s+LinkedIn\b.*$", "", candidate, flags=re.IGNORECASE)
    candidate = re.sub(r"\bLinkedIn\b.*$", "", candidate, flags=re.IGNORECASE)
    candidate = candidate.strip(" \t\n\r-–—|,.;:")
    candidate = clean_text(candidate)

    if not candidate or candidate.casefold() in GENERIC_COMPANY_VALUES:
        return None
    return candidate


def _normalize_company_name(company_raw: object | None) -> str | None:
    return _clean_company_candidate(company_raw)


def _company_name_from_slug(platform_company_slug: str) -> str | None:
    words = clean_text(platform_company_slug.replace("-", " ").replace("_", " "))
    if not words:
        return None
    return " ".join(word[:1].upper() + word[1:] for word in words.split())


def _ats_role_search_term(job_title_raw: str) -> str:
    known_role = match_known_role(job_title_raw)
    if known_role is not None:
        return known_role.role
    return "title contains AI"


def workable_jobs(response: Any) -> list[dict[str, Any]]:
    if not isinstance(response, dict):
        return []
    results = response.get("results")
    if not isinstance(results, list):
        return []
    return [item for item in results if isinstance(item, dict)]


def _workable_detail(
    *,
    metadata: dict[str, Any],
    platform_job_id: str,
) -> dict[str, Any] | None:
    detail_responses = metadata.get("job_detail_responses")
    if not isinstance(detail_responses, dict):
        return None
    detail = detail_responses.get(platform_job_id)
    return detail if isinstance(detail, dict) else None


def _workable_account_response(metadata: dict[str, Any]) -> dict[str, Any]:
    account_response = metadata.get("account_response")
    return account_response if isinstance(account_response, dict) else {}


def _workable_departments(job: dict[str, Any], detail: dict[str, Any] | None) -> list[str]:
    values: list[str] = []
    for source in (job, detail or {}):
        department = source.get("department")
        if isinstance(department, list):
            for item in department:
                _append_clean_unique(values, item)
        else:
            _append_clean_unique(values, department)
    return values


def _workable_location_dicts(job: dict[str, Any]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    location = job.get("location")
    if isinstance(location, dict) and location.get("hidden") is not True:
        values.append(location)

    locations = job.get("locations")
    if isinstance(locations, list):
        for item in locations:
            if (
                isinstance(item, dict)
                and item.get("hidden") is not True
                and item not in values
            ):
                values.append(item)
    return values


def _workable_location_value(location: dict[str, Any]) -> str | None:
    direct_value = _clean_optional(
        location.get("formatted") or location.get("location_str") or location.get("name")
    )
    if direct_value is not None:
        return direct_value

    parts: list[str] = []
    for field in ("city", "region", "state", "country"):
        _append_clean_unique(parts, location.get(field))
    return ", ".join(parts) or None


def _workable_location_values(job: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for location in _workable_location_dicts(job):
        _append_clean_unique(values, _workable_location_value(location))
    return values


def _workable_country_code(value: object | None) -> str | None:
    country_code = clean_text(value).casefold()
    if country_code == "gb":
        country_code = "uk"
    if country_code in COUNTRY_NAMES_BY_CODE:
        return country_code
    return None


def _workable_country_inference(job: dict[str, Any]) -> CountryInference:
    country_codes: list[str] = []
    country_source_values: list[object | None] = []
    for location in _workable_location_dicts(job):
        country_code = _workable_country_code(
            location.get("countryCode") or location.get("country_code")
        )
        if country_code is not None and country_code not in country_codes:
            country_codes.append(country_code)
        country_source_values.append(location.get("country"))
        country_source_values.append(_workable_location_value(location))

    if country_codes:
        return CountryInference(
            country_codes=country_codes,
            countries=[COUNTRY_NAMES_BY_CODE[code] for code in country_codes],
        )
    return infer_countries_from_locations(country_source_values)


def _workable_workplace_type(job: dict[str, Any], detail: dict[str, Any] | None) -> str | None:
    workplace = _clean_optional(job.get("workplace")) or _clean_optional(
        detail.get("workplace") if detail else None
    )
    if workplace is not None:
        return workplace
    remote = job.get("remote")
    if isinstance(remote, bool):
        return "remote" if remote else None
    return None


def _workable_source_url(
    *,
    job: dict[str, Any],
    detail: dict[str, Any] | None,
    board_url: str,
    platform_company_slug: str,
    platform_job_id: str,
) -> str:
    for source in (detail or {}, job):
        for field in ("url", "shortlink", "application_url", "apply_url"):
            source_url = _clean_optional(source.get(field))
            if source_url is not None:
                return source_url
    if platform_job_id:
        return (
            "https://apply.workable.com/"
            f"{quote(platform_company_slug, safe='-_~.')}/j/"
            f"{quote(platform_job_id, safe='-_~.')}"
        )
    return board_url


def normalize_workable_job(
    *,
    metadata: dict[str, Any],
    job: dict[str, Any],
    raw_file: Path,
) -> dict[str, Any] | None:
    state = clean_text(job.get("state")).casefold()
    if state and state != "published":
        return None
    if job.get("isInternal") is True:
        return None
    if job.get("hidden") is True:
        return None

    job_title_raw = _clean_optional(job.get("title") or job.get("name"))
    if job_title_raw is None:
        return None
    if is_excluded_ai_trainer_title(job_title_raw):
        return None
    if match_known_role(job_title_raw) is None and not has_ai_signal(job_title_raw):
        return None

    platform_company_slug = clean_text(metadata.get("platform_company_slug"))
    if not platform_company_slug:
        return None

    board_url = clean_text(metadata.get("board_url")) or (
        f"https://apply.workable.com/{quote(platform_company_slug, safe='-_~.')}"
    )
    location_values = _workable_location_values(job)
    platform_job_id = clean_text(job.get("shortcode")) or clean_text(job.get("id"))
    if not platform_job_id:
        platform_job_id = stable_sha256(
            (SourceName.WORKABLE.value, platform_company_slug, job_title_raw, location_values)
        )
    detail = _workable_detail(metadata=metadata, platform_job_id=platform_job_id)
    role_search_term = _ats_role_search_term(job_title_raw)
    job_title_normalized = normalize_job_title(
        job_title_raw,
        role_search_term=role_search_term,
    )
    role_group = classify_role(
        job_title_raw=job_title_raw,
        job_title_normalized=job_title_normalized,
        role_search_term=role_search_term,
    )

    account_response = _workable_account_response(metadata)
    company_raw = _clean_optional(account_response.get("name")) or _company_name_from_slug(
        platform_company_slug
    )
    company_normalized = _normalize_company_name(company_raw)
    departments = _workable_departments(job, detail)
    country_inference = _workable_country_inference(job)
    source_url = _workable_source_url(
        job=job,
        detail=detail,
        board_url=board_url,
        platform_company_slug=platform_company_slug,
        platform_job_id=platform_job_id,
    )

    return {
        "record_type": "job_candidate",
        "job_id": stable_sha256(
            (SourceName.WORKABLE.value, platform_company_slug, platform_job_id)
        ),
        "country_code": _first_or_empty(country_inference.country_codes),
        "country": _first_value(country_inference.countries),
        "job_country_codes": country_inference.country_codes,
        "job_countries": country_inference.countries,
        "search_location_label": _clean_optional(metadata.get("search_location_label")),
        "query_location": _clean_optional(metadata.get("query_location")),
        "serper_location": _clean_optional(metadata.get("serper_location")),
        "source": SourceName.WORKABLE.value,
        "source_mode": SourceMode.PUBLIC_JOB_BOARD_ENDPOINT.value,
        "source_url": source_url,
        "board_url": board_url,
        "job_url": source_url if source_url != board_url else None,
        "platform": SourceName.WORKABLE.value,
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
        "department": departments[0] if departments else None,
        "departments": departments,
        "location": _first_value(location_values),
        "job_location_raw": _first_value(location_values),
        "job_locations_raw": location_values,
        "locations": _workable_location_dicts(job),
        "remote": job.get("remote") if isinstance(job.get("remote"), bool) else None,
        "workplace_type": _workable_workplace_type(job, detail),
        "employment_type": _clean_optional(job.get("worktype"))
        or _clean_optional(detail.get("worktype") if detail else None)
        or _clean_optional(detail.get("full_part_time") if detail else None),
        "description": _clean_optional(detail.get("description") if detail else None),
        "requirements": _clean_optional(detail.get("requirements") if detail else None),
        "benefits": _clean_optional(detail.get("benefits") if detail else None),
        "source_published_at": _clean_optional(job.get("published"))
        or _clean_optional(detail.get("published") if detail else None),
        "language": _clean_optional(job.get("language")),
        "approval_status": _clean_optional(job.get("approvalStatus")),
        "evidence_quality": EvidenceQuality.TITLE_ONLY_ATS_LISTING.value,
        "needs_review": True,
        "collected_at": _clean_optional(metadata.get("collected_at")),
        "raw_file": raw_file.as_posix(),
    }
