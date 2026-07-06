from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from ai_hiring_radar.hashing import normalize_hash_part
from ai_hiring_radar.models import RoleGroup


MERGED_SOURCE_URLS_FIELD = "all_source_urls"
MERGED_ROLE_SEARCH_TERMS_FIELD = "all_role_search_terms"
MERGED_POSTINGS_FIELD = "all_postings"


def _clean_scalar(value: object | None) -> str:
    return " ".join(str(value or "").split()).strip()


def _append_unique(values: list[str], value: object | None) -> None:
    cleaned = _clean_scalar(value)
    if cleaned and cleaned not in values:
        values.append(cleaned)


def _list_values(record: dict[str, Any], field: str) -> list[str]:
    raw_values = record.get(field)
    if not isinstance(raw_values, list):
        return []

    values: list[str] = []
    for value in raw_values:
        _append_unique(values, value)
    return values


def _posting_key(record: dict[str, Any]) -> str:
    source = normalize_hash_part(record.get("source"))
    platform_company_slug = normalize_hash_part(record.get("platform_company_slug"))
    platform_job_id = normalize_hash_part(record.get("platform_job_id"))
    if source and platform_company_slug and platform_job_id:
        return f"platform:{source}:{platform_company_slug}:{platform_job_id}"

    source_url = _clean_scalar(record.get("source_url"))
    if source_url:
        return f"source_url:{source_url}"

    job_id = normalize_hash_part(record.get("job_id"))
    if job_id:
        return f"job_id:{job_id}"

    company = normalize_hash_part(record.get("company_normalized"))
    title = normalize_hash_part(record.get("job_title_raw"))
    country = _country_key(record)
    return f"fallback:{source}:{company}:{title}:{country}"


def _posting_entry(record: dict[str, Any]) -> dict[str, str] | None:
    title = _clean_scalar(record.get("job_title_raw"))
    if not title:
        return None

    return {
        "posting_key": _posting_key(record),
        "job_title_raw": title,
        "role_group": _clean_scalar(record.get("role_group")),
    }


def _append_unique_posting(
    postings: list[dict[str, str]], posting: dict[str, str] | None
) -> None:
    if posting is None:
        return
    posting_key = posting.get("posting_key")
    if not posting_key:
        return
    if any(item.get("posting_key") == posting_key for item in postings):
        return
    postings.append(posting)


def _posting_values(record: dict[str, Any]) -> list[dict[str, str]]:
    raw_values = record.get(MERGED_POSTINGS_FIELD)
    if not isinstance(raw_values, list):
        return []

    postings: list[dict[str, str]] = []
    for value in raw_values:
        if not isinstance(value, dict):
            continue
        title = _clean_scalar(value.get("job_title_raw"))
        posting_key = _clean_scalar(value.get("posting_key"))
        if not title or not posting_key:
            continue
        _append_unique_posting(
            postings,
            {
                "posting_key": posting_key,
                "job_title_raw": title,
                "role_group": _clean_scalar(value.get("role_group")),
            },
        )
    return postings


def _with_merge_fields(record: dict[str, Any]) -> dict[str, Any]:
    merged = dict(record)

    source_urls = _list_values(merged, MERGED_SOURCE_URLS_FIELD)
    _append_unique(source_urls, merged.get("source_url"))
    merged[MERGED_SOURCE_URLS_FIELD] = source_urls

    role_search_terms = _list_values(merged, MERGED_ROLE_SEARCH_TERMS_FIELD)
    _append_unique(role_search_terms, merged.get("role_search_term"))
    merged[MERGED_ROLE_SEARCH_TERMS_FIELD] = role_search_terms

    postings = _posting_values(merged)
    _append_unique_posting(postings, _posting_entry(merged))
    merged[MERGED_POSTINGS_FIELD] = postings

    return merged


def merge_candidate_records(
    canonical: dict[str, Any], duplicate: dict[str, Any]
) -> dict[str, Any]:
    merged = _with_merge_fields(canonical)
    duplicate_with_fields = _with_merge_fields(duplicate)

    for source_url in duplicate_with_fields[MERGED_SOURCE_URLS_FIELD]:
        _append_unique(merged[MERGED_SOURCE_URLS_FIELD], source_url)
    for role_search_term in duplicate_with_fields[MERGED_ROLE_SEARCH_TERMS_FIELD]:
        _append_unique(merged[MERGED_ROLE_SEARCH_TERMS_FIELD], role_search_term)
    for posting in duplicate_with_fields[MERGED_POSTINGS_FIELD]:
        _append_unique_posting(merged[MERGED_POSTINGS_FIELD], posting)

    for field in (
        "company_raw",
        "company_normalized",
        "displayed_link",
        "snippet",
        "collected_at",
    ):
        if not merged.get(field) and duplicate_with_fields.get(field):
            merged[field] = duplicate_with_fields[field]

    if merged.get("role_group") == RoleGroup.UNCLEAR.value and duplicate_with_fields.get(
        "role_group"
    ) != RoleGroup.UNCLEAR.value:
        merged["role_group"] = duplicate_with_fields.get("role_group")
        merged["job_title_normalized"] = duplicate_with_fields.get(
            "job_title_normalized", merged.get("job_title_normalized")
        )

    return merged


def _dedupe_with_key(
    candidates: Iterable[dict[str, Any]],
    key_func: Callable[[dict[str, Any]], tuple[object, ...] | None],
) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    index_by_key: dict[tuple[object, ...], int] = {}

    for candidate in candidates:
        key = key_func(candidate)
        if key is None:
            deduped.append(_with_merge_fields(candidate))
            continue

        existing_index = index_by_key.get(key)
        if existing_index is None:
            index_by_key[key] = len(deduped)
            deduped.append(_with_merge_fields(candidate))
            continue

        deduped[existing_index] = merge_candidate_records(
            deduped[existing_index], candidate
        )

    return deduped


def _source_url_key(candidate: dict[str, Any]) -> tuple[str, str] | None:
    if _platform_job_key(candidate) is not None:
        return None

    source_url = _clean_scalar(candidate.get("source_url"))
    if not source_url:
        return None
    return ("source_url", source_url)


def _platform_job_key(candidate: dict[str, Any]) -> tuple[str, str, str, str] | None:
    source = normalize_hash_part(candidate.get("source"))
    platform_company_slug = normalize_hash_part(candidate.get("platform_company_slug"))
    platform_job_id = normalize_hash_part(candidate.get("platform_job_id"))
    if source and platform_company_slug and platform_job_id:
        return ("platform_job", source, platform_company_slug, platform_job_id)
    return None


def _country_key(candidate: dict[str, Any]) -> str:
    country_codes = _list_values(candidate, "job_country_codes")
    if country_codes:
        return ",".join(normalize_hash_part(value) for value in country_codes)

    countries = _list_values(candidate, "job_countries")
    if countries:
        return ",".join(normalize_hash_part(value) for value in countries)

    return normalize_hash_part(candidate.get("country") or candidate.get("country_code"))


def _company_title_country_key(candidate: dict[str, Any]) -> tuple[str, str, str, str] | None:
    country = _country_key(candidate)
    company = normalize_hash_part(candidate.get("company_normalized"))
    title = normalize_hash_part(candidate.get("job_title_normalized"))
    if company and title and country:
        return ("company_title_country", company, title, country)

    raw_title = normalize_hash_part(candidate.get("job_title_raw"))
    role_search_term = normalize_hash_part(candidate.get("role_search_term"))
    if raw_title and role_search_term and country and not company:
        return ("raw_title_role_country", raw_title, role_search_term, country)

    return None


def dedupe_job_candidates(candidates: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    by_platform_job = _dedupe_with_key(candidates, _platform_job_key)
    by_url = _dedupe_with_key(by_platform_job, _source_url_key)
    return _dedupe_with_key(by_url, _company_title_country_key)
