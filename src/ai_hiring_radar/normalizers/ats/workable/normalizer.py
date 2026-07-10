from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote

from ai_hiring_radar.classify import clean_text, is_ai_role_title_candidate
from ai_hiring_radar.country_inference import (
    CountryInference,
    infer_countries_from_locations,
)
from ai_hiring_radar.hashing import stable_sha256
from ai_hiring_radar.models import SourceName
from ai_hiring_radar.normalizers.common.candidate import build_ats_candidate
from ai_hiring_radar.normalizers.common.company import company_name_from_slug
from ai_hiring_radar.normalizers.common.countries import (
    country_inference_from_codes,
    normalize_country_code,
)
from ai_hiring_radar.normalizers.common.text import (
    append_clean_unique,
    clean_optional,
    first_value,
)


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
                append_clean_unique(values, item)
        else:
            append_clean_unique(values, department)
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
    direct_value = clean_optional(
        location.get("formatted") or location.get("location_str") or location.get("name")
    )
    if direct_value is not None:
        return direct_value

    parts: list[str] = []
    for field in ("city", "region", "state", "country"):
        append_clean_unique(parts, location.get(field))
    return ", ".join(parts) or None


def _workable_location_values(job: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for location in _workable_location_dicts(job):
        append_clean_unique(values, _workable_location_value(location))
    return values


def _workable_country_inference(job: dict[str, Any]) -> CountryInference:
    country_codes: list[str] = []
    country_source_values: list[object | None] = []
    for location in _workable_location_dicts(job):
        country_code = normalize_country_code(
            location.get("countryCode") or location.get("country_code")
        )
        if country_code is not None and country_code not in country_codes:
            country_codes.append(country_code)
        country_source_values.append(location.get("country"))
        country_source_values.append(_workable_location_value(location))

    if country_codes:
        return country_inference_from_codes(country_codes)
    return infer_countries_from_locations(country_source_values)


def _workable_workplace_type(job: dict[str, Any], detail: dict[str, Any] | None) -> str | None:
    workplace = clean_optional(job.get("workplace")) or clean_optional(
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
            source_url = clean_optional(source.get(field))
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

    job_title_raw = clean_optional(job.get("title") or job.get("name"))
    if job_title_raw is None:
        return None
    if not is_ai_role_title_candidate(job_title_raw):
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
            (str(SourceName.WORKABLE), platform_company_slug, job_title_raw, location_values)
        )
    detail = _workable_detail(metadata=metadata, platform_job_id=platform_job_id)

    account_response = _workable_account_response(metadata)
    company_raw = clean_optional(account_response.get("name")) or company_name_from_slug(
        platform_company_slug
    )
    departments = _workable_departments(job, detail)
    country_inference = _workable_country_inference(job)
    source_url = _workable_source_url(
        job=job,
        detail=detail,
        board_url=board_url,
        platform_company_slug=platform_company_slug,
        platform_job_id=platform_job_id,
    )

    return build_ats_candidate(
        source=SourceName.WORKABLE,
        metadata=metadata,
        raw_file=raw_file,
        platform_company_slug=platform_company_slug,
        platform_job_id=platform_job_id,
        board_url=board_url,
        source_url=source_url,
        job_url=source_url if source_url != board_url else None,
        job_title_raw=job_title_raw,
        company_raw=company_raw,
        country_inference=country_inference,
        location=first_value(location_values),
        job_locations_raw=location_values,
        extra_fields={
            "team": departments[0] if departments else None,
            "department": departments[0] if departments else None,
            "departments": departments,
            "locations": _workable_location_dicts(job),
            "remote": job.get("remote") if isinstance(job.get("remote"), bool) else None,
            "workplace_type": _workable_workplace_type(job, detail),
            "employment_type": clean_optional(job.get("worktype"))
            or clean_optional(detail.get("worktype") if detail else None)
            or clean_optional(detail.get("full_part_time") if detail else None),
            "description": clean_optional(detail.get("description") if detail else None),
            "requirements": clean_optional(detail.get("requirements") if detail else None),
            "benefits": clean_optional(detail.get("benefits") if detail else None),
            "source_published_at": clean_optional(job.get("published"))
            or clean_optional(detail.get("published") if detail else None),
            "language": clean_optional(job.get("language")),
            "approval_status": clean_optional(job.get("approvalStatus")),
        },
    )


def normalize_response(
    *,
    metadata: dict[str, Any],
    response: Any,
    raw_file: Path,
) -> list[dict[str, Any]]:
    return [
        candidate
        for job in workable_jobs(response)
        if (
            candidate := normalize_workable_job(
                metadata=metadata,
                job=job,
                raw_file=raw_file,
            )
        )
        is not None
    ]
