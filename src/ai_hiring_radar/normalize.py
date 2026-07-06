from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from ai_hiring_radar.aggregate import aggregate_companies
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
from ai_hiring_radar.dedupe import (
    MERGED_POSTINGS_FIELD,
    MERGED_ROLE_SEARCH_TERMS_FIELD,
    MERGED_SOURCE_URLS_FIELD,
    dedupe_job_candidates,
)
from ai_hiring_radar.hashing import job_candidate_id, stable_sha256
from ai_hiring_radar.models import EvidenceQuality, SourceMode, SourceName
from ai_hiring_radar.storage_json import (
    DEFAULT_DATA_DIR,
    format_date,
    raw_ats_dir,
    raw_search_dir,
    read_json,
    write_processed_jsonl,
)


GENERIC_COMPANY_VALUES = {
    "careers",
    "hiring",
    "jobs",
    "linkedin",
    "remote",
}
LINKEDIN_HOST_SUFFIX = "linkedin.com"
LINKEDIN_JOB_VIEW_PATH = "/jobs/view"
RAW_ATS_RESPONSE_RECORD_TYPE = "raw_ats_response"
ATS_PLATFORMS = (
    SourceName.ASHBY.value,
    SourceName.GREENHOUSE.value,
    SourceName.LEVER.value,
    SourceName.PERSONIO.value,
    SourceName.SMARTRECRUITERS.value,
)


@dataclass(frozen=True)
class ProcessingResult:
    job_candidates_path: Path
    companies_path: Path
    raw_file_count: int
    candidate_count: int
    deduped_candidate_count: int
    company_count: int


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


def normalize_company_name(company_raw: object | None) -> str | None:
    return _clean_company_candidate(company_raw)


def is_concrete_linkedin_job_url(source_url: object | None) -> bool:
    cleaned_url = clean_text(source_url)
    if not cleaned_url:
        return False

    parsed_url = urlparse(cleaned_url)
    host = parsed_url.netloc.casefold()
    if not (host == LINKEDIN_HOST_SUFFIX or host.endswith(f".{LINKEDIN_HOST_SUFFIX}")):
        return False

    path = parsed_url.path.rstrip("/").casefold()
    return path == LINKEDIN_JOB_VIEW_PATH or path.startswith(
        f"{LINKEDIN_JOB_VIEW_PATH}/"
    )


def extract_company_name(*, title: str | None, snippet: str | None = None) -> str | None:
    raw_title = clean_text(title)
    if raw_title:
        hiring_title_match = re.search(
            r"^(.+?)\s+hiring\s+.+$",
            raw_title,
            flags=re.IGNORECASE,
        )
        if hiring_title_match is not None:
            company = _clean_company_candidate(hiring_title_match.group(1))
            if company is not None:
                return company

        if " - " in raw_title:
            company = _clean_company_candidate(raw_title.split(" - ", 1)[1])
            if company is not None:
                return company

        at_match = re.search(r"\bat\s+(.+)$", raw_title, flags=re.IGNORECASE)
        if at_match is not None:
            company = _clean_company_candidate(at_match.group(1))
            if company is not None:
                return company

    raw_snippet = clean_text(snippet)
    if raw_snippet:
        at_match = re.search(r"\bat\s+([^.,;|]+)", raw_snippet, flags=re.IGNORECASE)
        if at_match is not None:
            company = _clean_company_candidate(at_match.group(1))
            if company is not None:
                return company

        hiring_match = re.search(
            r"([^.,;|]{2,100}?)\s+is hiring\b",
            raw_snippet,
            flags=re.IGNORECASE,
        )
        if hiring_match is not None:
            company = _clean_company_candidate(hiring_match.group(1))
            if company is not None:
                return company

    return None


def iter_raw_response_files(
    collection_date: str,
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
) -> list[Path]:
    raw_dir = raw_search_dir(collection_date, data_dir=data_dir)
    if not raw_dir.exists():
        raise FileNotFoundError(f"Raw search directory does not exist: {raw_dir}")

    return sorted(
        path for path in raw_dir.glob("*.json") if path.name != "manifest.json"
    )


def _response_payload(raw_record: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if raw_record.get("record_type") == "raw_search_response" and isinstance(
        raw_record.get("response"), dict
    ):
        return raw_record, raw_record["response"]

    return {}, raw_record


def _organic_results(response: dict[str, Any]) -> list[dict[str, Any]]:
    organic_results = response.get("organic_results") or response.get("organic")
    if not isinstance(organic_results, list):
        return []
    return [item for item in organic_results if isinstance(item, dict)]


def _result_rank(result: dict[str, Any]) -> int | None:
    position = result.get("position")
    if isinstance(position, int):
        return position
    if isinstance(position, str) and position.isdecimal():
        return int(position)
    return None


def normalize_organic_result(
    *,
    metadata: dict[str, Any],
    result: dict[str, Any],
    raw_file: Path,
) -> dict[str, Any] | None:
    source_url = _clean_optional(result.get("link"))
    if not is_concrete_linkedin_job_url(source_url):
        return None

    job_title_raw = _clean_optional(result.get("title"))
    if job_title_raw is None:
        return None

    snippet = _clean_optional(result.get("snippet"))
    role_search_term = clean_text(metadata.get("role_search_term"))
    company_raw = extract_company_name(title=job_title_raw, snippet=snippet)
    company_normalized = normalize_company_name(company_raw)
    if company_normalized is None:
        return None

    job_title_normalized = normalize_job_title(
        job_title_raw,
        role_search_term=role_search_term,
    )
    role_group = classify_role(
        job_title_raw=job_title_raw,
        job_title_normalized=job_title_normalized,
        role_search_term=role_search_term,
    )

    country_code = clean_text(metadata.get("country_code"))
    country = clean_text(metadata.get("country"))
    search_location_label = clean_text(metadata.get("search_location_label"))
    query_location = clean_text(metadata.get("query_location"))
    serper_location = clean_text(metadata.get("serper_location"))
    search_query = clean_text(metadata.get("search_query"))

    return {
        "record_type": "job_candidate",
        "job_id": job_candidate_id(
            source_url=source_url,
            country_code=country_code,
            role_search_term=role_search_term,
            job_title_raw=job_title_raw,
            snippet=snippet,
        ),
        "country_code": country_code,
        "country": country,
        "search_location_label": search_location_label,
        "query_location": query_location,
        "serper_location": serper_location,
        "source": clean_text(metadata.get("source")) or SourceName.SERPER_GOOGLE.value,
        "source_mode": clean_text(metadata.get("source_mode"))
        or SourceMode.LINKEDIN_SAFE_SEARCH.value,
        "source_url": source_url,
        "result_rank": _result_rank(result),
        "displayed_link": _clean_optional(result.get("displayed_link")),
        "company_raw": company_raw,
        "company_normalized": company_normalized,
        "job_title_raw": job_title_raw,
        "job_title_normalized": job_title_normalized,
        "role_search_term": role_search_term,
        "role_group": role_group,
        "search_query": search_query,
        "snippet": snippet,
        "evidence_quality": EvidenceQuality.TITLE_ONLY_SEARCH_RESULT.value,
        "needs_review": True,
        "collected_at": _clean_optional(metadata.get("collected_at")),
        "raw_file": raw_file.as_posix(),
    }


def normalize_raw_search_file(raw_file: Path) -> list[dict[str, Any]]:
    raw_record = read_json(raw_file)
    if not isinstance(raw_record, dict):
        return []

    metadata, response = _response_payload(raw_record)
    return [
        candidate
        for result in _organic_results(response)
        if (
            candidate := normalize_organic_result(
                metadata=metadata,
                result=result,
                raw_file=raw_file,
            )
        )
        is not None
    ]


def iter_raw_ats_response_files(
    collection_date: str,
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
) -> list[Path]:
    files: list[Path] = []
    for platform in ATS_PLATFORMS:
        raw_dir = raw_ats_dir(collection_date, data_dir=data_dir, platform=platform)
        if not raw_dir.exists():
            continue
        files.extend(path for path in raw_dir.glob("*.json") if path.name != "manifest.json")
    return sorted(files)


def _raw_ats_response_payload(
    raw_record: dict[str, Any],
) -> tuple[dict[str, Any], Any]:
    if raw_record.get("record_type") == RAW_ATS_RESPONSE_RECORD_TYPE and "response" in raw_record:
        return raw_record, raw_record["response"]

    return {}, raw_record


def _ashby_job_board(response: dict[str, Any]) -> dict[str, Any] | None:
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
    return _clean_optional(team.get("externalName") or team.get("name"))


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
        _append_clean_unique(values, team_name)
    return values


def _ashby_detail_secondary_locations(detail: dict[str, Any] | None) -> list[str]:
    if detail is None:
        return []
    secondary_locations = detail.get("secondaryLocationNames")
    if not isinstance(secondary_locations, list):
        return []

    values: list[str] = []
    for location in secondary_locations:
        _append_clean_unique(values, location)
    return values


def _ashby_display_location(job: dict[str, Any]) -> str | None:
    return _clean_optional(job.get("locationName") or job.get("location"))


def _postal_address_country(value: dict[str, Any]) -> str | None:
    address = value.get("address")
    if not isinstance(address, dict):
        return None

    postal_address = address.get("postalAddress")
    if not isinstance(postal_address, dict):
        return None

    return _clean_optional(postal_address.get("addressCountry"))


def _ashby_secondary_locations(job: dict[str, Any]) -> list[str]:
    secondary_locations = job.get("secondaryLocations")
    if not isinstance(secondary_locations, list):
        return []

    values: list[str] = []
    for location in secondary_locations:
        if not isinstance(location, dict):
            continue
        _append_clean_unique(
            values,
            location.get("locationName") or location.get("location"),
        )
    return values


def _ashby_location_values(job: dict[str, Any]) -> list[str]:
    values: list[str] = []
    _append_clean_unique(values, _ashby_display_location(job))
    for location in _ashby_secondary_locations(job):
        _append_clean_unique(values, location)
    return values


def _ashby_country_source_locations(job: dict[str, Any]) -> list[str]:
    values: list[str] = []
    _append_clean_unique(values, _postal_address_country(job))
    for location in _ashby_location_values(job):
        _append_clean_unique(values, location)

    secondary_locations = job.get("secondaryLocations")
    if isinstance(secondary_locations, list):
        for location in secondary_locations:
            if isinstance(location, dict):
                _append_clean_unique(values, _postal_address_country(location))
    return values


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


def normalize_ashby_job_posting(
    *,
    metadata: dict[str, Any],
    job: dict[str, Any],
    teams_by_id: dict[str, dict[str, Any]],
    raw_file: Path,
) -> dict[str, Any] | None:
    job_title_raw = _clean_optional(job.get("title"))
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
        f"https://jobs.ashbyhq.com/{platform_company_slug}"
    )
    platform_job_id = clean_text(job.get("id")) or stable_sha256(
        (
            SourceName.ASHBY.value,
            platform_company_slug,
            job_title_raw,
            job.get("locationName"),
        )
    )
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
    detail = _ashby_job_detail(
        metadata=metadata,
        platform_job_id=platform_job_id,
    )

    team = teams_by_id.get(clean_text(job.get("teamId")))
    parent_team = teams_by_id.get(clean_text(team.get("parentTeamId")) if team else "")
    detail_team_names = _ashby_detail_team_names(detail)
    company_raw = _company_name_from_slug(platform_company_slug)
    company_normalized = normalize_company_name(company_raw)
    location = _ashby_display_location(job) or _clean_optional(
        detail.get("locationName") if detail else None
    )
    location_values = _ashby_location_values(job)
    _append_clean_unique(location_values, detail.get("locationName") if detail else None)
    for detail_location in _ashby_detail_secondary_locations(detail):
        _append_clean_unique(location_values, detail_location)
    country_source_locations = _ashby_country_source_locations(job)
    for location_value in location_values:
        _append_clean_unique(country_source_locations, location_value)
    country_inference = infer_countries_from_locations(country_source_locations)
    detail_department = _clean_optional(
        detail.get("departmentExternalName") if detail else None
    ) or _clean_optional(detail.get("departmentName") if detail else None)
    job_url = f"{board_url.rstrip('/')}/{platform_job_id}"

    return {
        "record_type": "job_candidate",
        "job_id": stable_sha256(
            (SourceName.ASHBY.value, platform_company_slug, platform_job_id)
        ),
        "country_code": _first_or_empty(country_inference.country_codes),
        "country": _first_value(country_inference.countries),
        "job_country_codes": country_inference.country_codes,
        "job_countries": country_inference.countries,
        "search_location_label": _clean_optional(metadata.get("search_location_label")),
        "query_location": _clean_optional(metadata.get("query_location")),
        "serper_location": _clean_optional(metadata.get("serper_location")),
        "source": SourceName.ASHBY.value,
        "source_mode": SourceMode.PUBLIC_JOB_BOARD_ENDPOINT.value,
        "source_url": board_url,
        "board_url": board_url,
        "job_url": job_url,
        "platform": SourceName.ASHBY.value,
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
        "team": _ashby_team_name(team) or _first_value(detail_team_names),
        "teams": detail_team_names,
        "parent_team": _ashby_team_name(parent_team),
        "department": detail_department,
        "location": location,
        "job_location_raw": location,
        "job_locations_raw": location_values,
        "workplace_type": _clean_optional(job.get("workplaceType"))
        or _clean_optional(detail.get("workplaceType") if detail else None),
        "employment_type": _clean_optional(job.get("employmentType"))
        or _clean_optional(detail.get("employmentType") if detail else None),
        "secondary_locations": _ashby_secondary_locations(job),
        "compensation": _clean_optional(job.get("compensationTierSummary"))
        or _clean_optional(detail.get("compensationTierSummary") if detail else None),
        "description": _clean_optional(detail.get("descriptionHtml") if detail else None),
        "evidence_quality": EvidenceQuality.TITLE_ONLY_ATS_LISTING.value,
        "needs_review": True,
        "collected_at": _clean_optional(metadata.get("collected_at")),
        "raw_file": raw_file.as_posix(),
    }


def _greenhouse_jobs(response: dict[str, Any]) -> list[dict[str, Any]]:
    jobs = response.get("jobs")
    if not isinstance(jobs, list):
        return []
    return [item for item in jobs if isinstance(item, dict)]


def _greenhouse_location_name(job: dict[str, Any]) -> str | None:
    location = job.get("location")
    if isinstance(location, dict):
        return _clean_optional(location.get("name"))
    return _clean_optional(location)


def _greenhouse_departments(job: dict[str, Any]) -> list[str]:
    departments = job.get("departments")
    if not isinstance(departments, list):
        return []

    values: list[str] = []
    for department in departments:
        if not isinstance(department, dict):
            continue
        department_name = _clean_optional(department.get("name"))
        if department_name and department_name not in values:
            values.append(department_name)
    return values


def _greenhouse_office_value(value: object | None) -> str | None:
    if isinstance(value, dict):
        return _clean_optional(value.get("name") or value.get("location"))
    return _clean_optional(value)


def _greenhouse_offices(job: dict[str, Any]) -> list[str]:
    offices = job.get("offices")
    if not isinstance(offices, list):
        return []

    values: list[str] = []
    for office in offices:
        if not isinstance(office, dict):
            continue
        office_name = _greenhouse_office_value(office.get("location")) or _clean_optional(
            office.get("name")
        )
        if office_name and office_name not in values:
            values.append(office_name)
    return values


def _greenhouse_location_values(*, location: str | None, offices: list[str]) -> list[str]:
    values: list[str] = []
    _append_clean_unique(values, location)
    for office in offices:
        _append_clean_unique(values, office)
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
    job_title_raw = _clean_optional(job.get("title"))
    if job_title_raw is None:
        return None
    if match_known_role(job_title_raw) is None and not has_ai_signal(job_title_raw):
        return None

    platform_company_slug = clean_text(metadata.get("platform_company_slug"))
    if not platform_company_slug:
        return None

    board_url = clean_text(metadata.get("board_url")) or (
        f"https://boards.greenhouse.io/{platform_company_slug}"
    )
    location = _greenhouse_location_name(job)
    platform_job_id = clean_text(job.get("id")) or stable_sha256(
        (SourceName.GREENHOUSE.value, platform_company_slug, job_title_raw, location)
    )
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

    departments = _greenhouse_departments(job)
    source_url = _clean_optional(job.get("absolute_url")) or board_url
    company_raw = _company_name_from_slug(platform_company_slug)
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
            (SourceName.GREENHOUSE.value, platform_company_slug, platform_job_id)
        ),
        "country_code": _first_or_empty(country_inference.country_codes),
        "country": _first_value(country_inference.countries),
        "job_country_codes": country_inference.country_codes,
        "job_countries": country_inference.countries,
        "search_location_label": _clean_optional(metadata.get("search_location_label")),
        "query_location": _clean_optional(metadata.get("query_location")),
        "serper_location": _clean_optional(metadata.get("serper_location")),
        "source": SourceName.GREENHOUSE.value,
        "source_mode": SourceMode.PUBLIC_JOB_BOARD_ENDPOINT.value,
        "source_url": source_url,
        "board_url": board_url,
        "job_url": source_url,
        "platform": SourceName.GREENHOUSE.value,
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
        "description": _clean_optional(job.get("content")),
        "compensation": job.get("pay_input_ranges"),
        "source_updated_at": _clean_optional(job.get("updated_at")),
        "evidence_quality": EvidenceQuality.TITLE_ONLY_ATS_LISTING.value,
        "needs_review": True,
        "collected_at": _clean_optional(metadata.get("collected_at")),
        "raw_file": raw_file.as_posix(),
    }


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
    return _clean_optional(_lever_categories(job).get("location"))


def _lever_description(job: dict[str, Any]) -> str | None:
    return _clean_optional(
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
    job_title_raw = _clean_optional(job.get("text") or job.get("title"))
    if job_title_raw is None:
        return None
    if match_known_role(job_title_raw) is None and not has_ai_signal(job_title_raw):
        return None

    platform_company_slug = clean_text(metadata.get("platform_company_slug"))
    if not platform_company_slug:
        return None

    board_url = clean_text(metadata.get("board_url")) or (
        f"https://jobs.lever.co/{platform_company_slug}"
    )
    location = _lever_location(job)
    platform_job_id = clean_text(job.get("id")) or stable_sha256(
        (SourceName.LEVER.value, platform_company_slug, job_title_raw, location)
    )
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

    categories = _lever_categories(job)
    source_url = _clean_optional(job.get("hostedUrl")) or board_url
    company_raw = _company_name_from_slug(platform_company_slug)
    company_normalized = normalize_company_name(company_raw)
    location_values: list[str] = []
    _append_clean_unique(location_values, location)
    country_inference = infer_countries_from_locations(location_values)

    return {
        "record_type": "job_candidate",
        "job_id": stable_sha256(
            (SourceName.LEVER.value, platform_company_slug, platform_job_id)
        ),
        "country_code": _first_or_empty(country_inference.country_codes),
        "country": _first_value(country_inference.countries),
        "job_country_codes": country_inference.country_codes,
        "job_countries": country_inference.countries,
        "search_location_label": _clean_optional(metadata.get("search_location_label")),
        "query_location": _clean_optional(metadata.get("query_location")),
        "serper_location": _clean_optional(metadata.get("serper_location")),
        "source": SourceName.LEVER.value,
        "source_mode": SourceMode.PUBLIC_JOB_BOARD_ENDPOINT.value,
        "source_url": source_url,
        "board_url": board_url,
        "job_url": source_url,
        "apply_url": _clean_optional(job.get("applyUrl")),
        "platform": SourceName.LEVER.value,
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
        "team": _clean_optional(categories.get("team") or categories.get("department")),
        "department": _clean_optional(categories.get("department")),
        "location": location,
        "job_location_raw": location,
        "job_locations_raw": location_values,
        "employment_type": _clean_optional(categories.get("commitment")),
        "description": _lever_description(job),
        "description_plain": _clean_optional(job.get("descriptionPlain")),
        "lists": job.get("lists") if isinstance(job.get("lists"), list) else [],
        "source_created_at": _clean_optional(job.get("createdAt")),
        "evidence_quality": EvidenceQuality.TITLE_ONLY_ATS_LISTING.value,
        "needs_review": True,
        "collected_at": _clean_optional(metadata.get("collected_at")),
        "raw_file": raw_file.as_posix(),
    }


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
    return _clean_optional(location.get("fullLocation") or location.get("city"))


def _smartrecruiters_location_values(job: dict[str, Any]) -> list[str]:
    location = _smartrecruiters_location(job)
    values: list[str] = []
    _append_clean_unique(values, location.get("fullLocation"))
    _append_clean_unique(values, location.get("city"))
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
        source_url = _clean_optional(job.get(field))
        if source_url is not None:
            return source_url
    return board_url


def normalize_smartrecruiters_posting(
    *,
    metadata: dict[str, Any],
    job: dict[str, Any],
    raw_file: Path,
) -> dict[str, Any] | None:
    job_title_raw = _clean_optional(job.get("name") or job.get("title"))
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
        f"https://careers.smartrecruiters.com/{quote(platform_company_slug, safe='-_~.')}"
    )
    location = _smartrecruiters_display_location(job)
    platform_job_id = clean_text(job.get("id")) or stable_sha256(
        (SourceName.SMARTRECRUITERS.value, platform_company_slug, job_title_raw, location)
    )
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

    location_data = _smartrecruiters_location(job)
    location_values = _smartrecruiters_location_values(job)
    country_inference = _smartrecruiters_country_inference(
        country=location_data.get("country"),
        locations=location_values,
    )
    source_url = _smartrecruiters_source_url(job, board_url)
    company_raw = _company_name_from_slug(platform_company_slug)
    company_normalized = normalize_company_name(company_raw)

    return {
        "record_type": "job_candidate",
        "job_id": stable_sha256(
            (SourceName.SMARTRECRUITERS.value, platform_company_slug, platform_job_id)
        ),
        "country_code": _first_or_empty(country_inference.country_codes),
        "country": _first_value(country_inference.countries),
        "job_country_codes": country_inference.country_codes,
        "job_countries": country_inference.countries,
        "search_location_label": _clean_optional(metadata.get("search_location_label")),
        "query_location": _clean_optional(metadata.get("query_location")),
        "serper_location": _clean_optional(metadata.get("serper_location")),
        "source": SourceName.SMARTRECRUITERS.value,
        "source_mode": SourceMode.PUBLIC_JOB_BOARD_ENDPOINT.value,
        "source_url": source_url,
        "board_url": board_url,
        "job_url": source_url if source_url != board_url else None,
        "api_ref": _clean_optional(job.get("ref")),
        "platform": SourceName.SMARTRECRUITERS.value,
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
        "location_country_raw": _clean_optional(location_data.get("country")),
        "workplace_type": _smartrecruiters_workplace_type(job),
        "remote": location_data.get("remote") if isinstance(location_data.get("remote"), bool) else None,
        "hybrid": location_data.get("hybrid") if isinstance(location_data.get("hybrid"), bool) else None,
        "source_created_at": _clean_optional(
            job.get("releasedDate") or job.get("createdOn") or job.get("publishedOn")
        ),
        "source_updated_at": _clean_optional(job.get("updatedOn") or job.get("updatedAt")),
        "evidence_quality": EvidenceQuality.TITLE_ONLY_ATS_LISTING.value,
        "needs_review": True,
        "collected_at": _clean_optional(metadata.get("collected_at")),
        "raw_file": raw_file.as_posix(),
    }


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _xml_children(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in element if _xml_local_name(child.tag) == name]


def _xml_first_child(element: ET.Element, name: str) -> ET.Element | None:
    for child in element:
        if _xml_local_name(child.tag) == name:
            return child
    return None


def _xml_child_text(element: ET.Element, name: str) -> str | None:
    child = _xml_first_child(element, name)
    if child is None:
        return None
    return _clean_optional(child.text)


def _personio_positions(response: Any) -> list[ET.Element]:
    if not isinstance(response, str):
        return []

    try:
        root = ET.fromstring(response)
    except ET.ParseError:
        return []

    if _xml_local_name(root.tag) == "position":
        return [root]
    return [
        element for element in root.iter() if _xml_local_name(element.tag) == "position"
    ]


def _personio_job_description_sections(position: ET.Element) -> list[dict[str, str]]:
    container = _xml_first_child(position, "jobDescriptions")
    if container is None:
        return []

    sections: list[dict[str, str]] = []
    for section in _xml_children(container, "jobDescription"):
        section_name = _xml_child_text(section, "name")
        value = _xml_child_text(section, "value")
        if value is None:
            continue
        sections.append(
            {
                "name": section_name or "",
                "value": value,
            }
        )
    return sections


def _personio_description(position: ET.Element) -> str | None:
    sections = _personio_job_description_sections(position)
    values = [section["value"] for section in sections if section.get("value")]
    return "\n\n".join(values) or None


def _personio_job_url(
    position: ET.Element,
    *,
    board_url: str,
    platform_job_id: str | None,
) -> str | None:
    for field in ("jobUrl", "jobURL", "url", "link"):
        job_url = _xml_child_text(position, field)
        if job_url is not None:
            return job_url
    if platform_job_id is not None:
        return f"{board_url.rstrip('/')}/job/{quote(platform_job_id, safe='')}"
    return None


def normalize_personio_position(
    *,
    metadata: dict[str, Any],
    position: ET.Element,
    raw_file: Path,
) -> dict[str, Any] | None:
    job_title_raw = _xml_child_text(position, "name")
    if job_title_raw is None:
        return None
    if match_known_role(job_title_raw) is None and not has_ai_signal(job_title_raw):
        return None

    platform_company_slug = clean_text(metadata.get("platform_company_slug"))
    if not platform_company_slug:
        return None

    board_url = clean_text(metadata.get("board_url")) or (
        f"https://{platform_company_slug}.jobs.personio.com"
    )
    location = _xml_child_text(position, "office")
    xml_platform_job_id = _xml_child_text(position, "id")
    platform_job_id = xml_platform_job_id or stable_sha256(
        (SourceName.PERSONIO.value, platform_company_slug, job_title_raw, location)
    )
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

    company_raw = _company_name_from_slug(platform_company_slug)
    company_normalized = normalize_company_name(company_raw)
    location_values: list[str] = []
    _append_clean_unique(location_values, location)
    country_inference = infer_countries_from_locations(location_values)
    source_url = (
        _personio_job_url(
            position,
            board_url=board_url,
            platform_job_id=xml_platform_job_id,
        )
        or board_url
    )

    return {
        "record_type": "job_candidate",
        "job_id": stable_sha256(
            (SourceName.PERSONIO.value, platform_company_slug, platform_job_id)
        ),
        "country_code": _first_or_empty(country_inference.country_codes),
        "country": _first_value(country_inference.countries),
        "job_country_codes": country_inference.country_codes,
        "job_countries": country_inference.countries,
        "search_location_label": _clean_optional(metadata.get("search_location_label")),
        "query_location": _clean_optional(metadata.get("query_location")),
        "serper_location": _clean_optional(metadata.get("serper_location")),
        "source": SourceName.PERSONIO.value,
        "source_mode": SourceMode.PUBLIC_JOB_BOARD_ENDPOINT.value,
        "source_url": source_url,
        "board_url": board_url,
        "job_url": source_url if source_url != board_url else None,
        "platform": SourceName.PERSONIO.value,
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
        "team": _xml_child_text(position, "department"),
        "department": _xml_child_text(position, "department"),
        "location": location,
        "job_location_raw": location,
        "job_locations_raw": location_values,
        "employment_type": _xml_child_text(position, "employmentType"),
        "schedule": _xml_child_text(position, "schedule"),
        "recruiting_category": _xml_child_text(position, "recruitingCategory"),
        "description": _personio_description(position),
        "job_description_sections": _personio_job_description_sections(position),
        "evidence_quality": EvidenceQuality.TITLE_ONLY_ATS_LISTING.value,
        "needs_review": True,
        "collected_at": _clean_optional(metadata.get("collected_at")),
        "raw_file": raw_file.as_posix(),
    }


def normalize_raw_ats_file(raw_file: Path) -> list[dict[str, Any]]:
    raw_record = read_json(raw_file)
    if not isinstance(raw_record, dict):
        return []

    metadata, response = _raw_ats_response_payload(raw_record)
    platform = clean_text(metadata.get("platform"))
    if platform == SourceName.GREENHOUSE.value:
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

    if platform == SourceName.LEVER.value:
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

    if platform == SourceName.PERSONIO.value:
        return [
            candidate
            for position in _personio_positions(response)
            if (
                candidate := normalize_personio_position(
                    metadata=metadata,
                    position=position,
                    raw_file=raw_file,
                )
            )
            is not None
        ]

    if platform == SourceName.SMARTRECRUITERS.value:
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

    if platform not in {"", SourceName.ASHBY.value}:
        return []

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


def build_job_candidates(
    collection_date: str,
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for raw_file in _raw_search_files_if_present(collection_date, data_dir=data_dir):
        candidates.extend(normalize_raw_search_file(raw_file))
    for raw_file in iter_raw_ats_response_files(collection_date, data_dir=data_dir):
        candidates.extend(normalize_raw_ats_file(raw_file))
    return candidates


def _raw_search_files_if_present(
    collection_date: str,
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
) -> list[Path]:
    try:
        return iter_raw_response_files(collection_date, data_dir=data_dir)
    except FileNotFoundError:
        return []


def _raw_input_files(
    collection_date: str,
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
) -> tuple[list[Path], list[Path]]:
    raw_search_files = _raw_search_files_if_present(collection_date, data_dir=data_dir)
    raw_ats_files = iter_raw_ats_response_files(collection_date, data_dir=data_dir)

    if not raw_search_files and not raw_ats_files:
        expected_ats_dirs = ", ".join(
            raw_ats_dir(collection_date, data_dir=data_dir, platform=platform).as_posix()
            for platform in ATS_PLATFORMS
        )
        raise FileNotFoundError(
            "No raw input files found for collection date "
            f"{collection_date}. Expected Serper files under "
            f"{raw_search_dir(collection_date, data_dir=data_dir)} or ATS files under "
            f"one of: {expected_ats_dirs}."
        )

    return raw_search_files, raw_ats_files


def _without_dedupe_metadata(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in candidate.items()
        if key
        not in {
            MERGED_POSTINGS_FIELD,
            MERGED_SOURCE_URLS_FIELD,
            MERGED_ROLE_SEARCH_TERMS_FIELD,
        }
    }


def process_collection(
    collection_date: str,
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
) -> ProcessingResult:
    normalized_date = format_date(collection_date)
    raw_search_files, raw_ats_files = _raw_input_files(
        normalized_date,
        data_dir=data_dir,
    )

    candidates: list[dict[str, Any]] = []
    for raw_file in raw_search_files:
        candidates.extend(normalize_raw_search_file(raw_file))
    for raw_file in raw_ats_files:
        candidates.extend(normalize_raw_ats_file(raw_file))

    deduped_candidates = dedupe_job_candidates(candidates)
    companies = aggregate_companies(deduped_candidates)
    persisted_candidates = [
        _without_dedupe_metadata(candidate) for candidate in deduped_candidates
    ]

    job_candidates_path = write_processed_jsonl(
        f"job_candidates_{normalized_date}.jsonl",
        persisted_candidates,
        data_dir=data_dir,
    )
    companies_path = write_processed_jsonl(
        f"companies_{normalized_date}.jsonl",
        companies,
        data_dir=data_dir,
    )

    return ProcessingResult(
        job_candidates_path=job_candidates_path,
        companies_path=companies_path,
        raw_file_count=len(raw_search_files) + len(raw_ats_files),
        candidate_count=len(candidates),
        deduped_candidate_count=len(deduped_candidates),
        company_count=len(companies),
    )
