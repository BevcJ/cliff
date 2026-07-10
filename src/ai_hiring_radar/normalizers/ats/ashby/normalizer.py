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


def _ashby_job_board(response: Any) -> dict[str, Any] | None:
    data = response.get("data")
    if not isinstance(data, dict):
        return None

    job_board = data.get("jobBoard")
    if not isinstance(job_board, dict):
        return None
    return job_board


def _ashby_job_postings(job_board: dict[str, Any]) -> list[dict[str, Any]]:
    job_postings = job_board.get("jobPostings")
    if not isinstance(job_postings, list):
        return []
    return [item for item in job_postings if isinstance(item, dict)]


def _ashby_teams_by_id(job_board: dict[str, Any]) -> dict[str, dict[str, Any]]:
    teams = job_board.get("teams")
    if not isinstance(teams, list):
        return {}

    teams_by_id: dict[str, dict[str, Any]] = {}
    for team in teams:
        if not isinstance(team, dict):
            continue
        team_id = clean_text(team.get("id"))
        if team_id:
            teams_by_id[team_id] = team
    return teams_by_id


def _ashby_team_name(team: dict[str, Any] | None) -> str | None:
    if team is None:
        return None
    return clean_optional(team.get("externalName") or team.get("name"))


def _ashby_job_detail(
    *,
    metadata: dict[str, Any],
    platform_job_id: str,
) -> dict[str, Any] | None:
    detail_responses = metadata.get("job_detail_responses")
    if not isinstance(detail_responses, dict):
        return None

    response = detail_responses.get(platform_job_id)
    if not isinstance(response, dict):
        return None

    data = response.get("data")
    if isinstance(data, dict) and isinstance(data.get("jobPosting"), dict):
        return data["jobPosting"]

    if isinstance(response.get("jobPosting"), dict):
        return response["jobPosting"]

    return None


def _ashby_detail_team_names(detail: dict[str, Any] | None) -> list[str]:
    if detail is None:
        return []
    team_names = detail.get("teamNames")
    if not isinstance(team_names, list):
        return []

    values: list[str] = []
    for team_name in team_names:
        append_clean_unique(values, team_name)
    return values


def _ashby_detail_secondary_locations(detail: dict[str, Any] | None) -> list[str]:
    if detail is None:
        return []
    secondary_locations = detail.get("secondaryLocationNames")
    if not isinstance(secondary_locations, list):
        return []

    values: list[str] = []
    for location in secondary_locations:
        append_clean_unique(values, location)
    return values


def _ashby_display_location(job: dict[str, Any]) -> str | None:
    return clean_optional(job.get("locationName") or job.get("location"))


def _postal_address_country(value: dict[str, Any]) -> str | None:
    address = value.get("address")
    if not isinstance(address, dict):
        return None

    postal_address = address.get("postalAddress")
    if not isinstance(postal_address, dict):
        return None

    return clean_optional(postal_address.get("addressCountry"))


def _ashby_secondary_locations(job: dict[str, Any]) -> list[str]:
    secondary_locations = job.get("secondaryLocations")
    if not isinstance(secondary_locations, list):
        return []

    values: list[str] = []
    for location in secondary_locations:
        if not isinstance(location, dict):
            continue
        append_clean_unique(
            values,
            location.get("locationName") or location.get("location"),
        )
    return values


def _ashby_location_values(job: dict[str, Any]) -> list[str]:
    values: list[str] = []
    append_clean_unique(values, _ashby_display_location(job))
    for location in _ashby_secondary_locations(job):
        append_clean_unique(values, location)
    return values


def _ashby_country_source_locations(job: dict[str, Any]) -> list[str]:
    values: list[str] = []
    append_clean_unique(values, _postal_address_country(job))
    for location in _ashby_location_values(job):
        append_clean_unique(values, location)

    secondary_locations = job.get("secondaryLocations")
    if isinstance(secondary_locations, list):
        for location in secondary_locations:
            if isinstance(location, dict):
                append_clean_unique(values, _postal_address_country(location))
    return values


def normalize_ashby_job_posting(
    *,
    metadata: dict[str, Any],
    job: dict[str, Any],
    teams_by_id: dict[str, dict[str, Any]],
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
        f"https://jobs.ashbyhq.com/{platform_company_slug}"
    )
    platform_job_id = clean_text(job.get("id")) or stable_sha256(
        (
            str(SourceName.ASHBY),
            platform_company_slug,
            job_title_raw,
            job.get("locationName"),
        )
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
    detail = _ashby_job_detail(
        metadata=metadata,
        platform_job_id=platform_job_id,
    )

    team = teams_by_id.get(clean_text(job.get("teamId")))
    parent_team = teams_by_id.get(clean_text(team.get("parentTeamId")) if team else "")
    detail_team_names = _ashby_detail_team_names(detail)
    company_raw = company_name_from_slug(platform_company_slug)
    company_normalized = normalize_company_name(company_raw)
    location = _ashby_display_location(job) or clean_optional(
        detail.get("locationName") if detail else None
    )
    location_values = _ashby_location_values(job)
    append_clean_unique(location_values, detail.get("locationName") if detail else None)
    for detail_location in _ashby_detail_secondary_locations(detail):
        append_clean_unique(location_values, detail_location)
    country_source_locations = _ashby_country_source_locations(job)
    for location_value in location_values:
        append_clean_unique(country_source_locations, location_value)
    country_inference = infer_countries_from_locations(country_source_locations)
    detail_department = clean_optional(
        detail.get("departmentExternalName") if detail else None
    ) or clean_optional(detail.get("departmentName") if detail else None)
    job_url = f"{board_url.rstrip('/')}/{platform_job_id}"

    return {
        "record_type": "job_candidate",
        "job_id": stable_sha256(
            (str(SourceName.ASHBY), platform_company_slug, platform_job_id)
        ),
        "country_code": first_or_empty(country_inference.country_codes),
        "country": first_value(country_inference.countries),
        "job_country_codes": country_inference.country_codes,
        "job_countries": country_inference.countries,
        "search_location_label": clean_optional(metadata.get("search_location_label")),
        "query_location": clean_optional(metadata.get("query_location")),
        "serper_location": clean_optional(metadata.get("serper_location")),
        "source": str(SourceName.ASHBY),
        "source_mode": str(SourceMode.PUBLIC_JOB_BOARD_ENDPOINT),
        "source_url": board_url,
        "board_url": board_url,
        "job_url": job_url,
        "platform": str(SourceName.ASHBY),
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
        "team": _ashby_team_name(team) or first_value(detail_team_names),
        "teams": detail_team_names,
        "parent_team": _ashby_team_name(parent_team),
        "department": detail_department,
        "location": location,
        "job_location_raw": location,
        "job_locations_raw": location_values,
        "workplace_type": clean_optional(job.get("workplaceType"))
        or clean_optional(detail.get("workplaceType") if detail else None),
        "employment_type": clean_optional(job.get("employmentType"))
        or clean_optional(detail.get("employmentType") if detail else None),
        "secondary_locations": _ashby_secondary_locations(job),
        "compensation": clean_optional(job.get("compensationTierSummary"))
        or clean_optional(detail.get("compensationTierSummary") if detail else None),
        "description": clean_optional(detail.get("descriptionHtml") if detail else None),
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
    job_board = _ashby_job_board(response)
    if job_board is None:
        return []

    teams_by_id = _ashby_teams_by_id(job_board)
    return [
        candidate
        for job in _ashby_job_postings(job_board)
        if (
            candidate := normalize_ashby_job_posting(
                metadata=metadata,
                job=job,
                teams_by_id=teams_by_id,
                raw_file=raw_file,
            )
        )
        is not None
    ]
