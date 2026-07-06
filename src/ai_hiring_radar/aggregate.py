from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from ai_hiring_radar.dedupe import (
    MERGED_POSTINGS_FIELD,
    MERGED_ROLE_SEARCH_TERMS_FIELD,
    MERGED_SOURCE_URLS_FIELD,
)
from ai_hiring_radar.hashing import normalize_hash_part
from ai_hiring_radar.models import RoleGroup


def _clean_scalar(value: object | None) -> str:
    return " ".join(str(value or "").split()).strip()


def _append_unique(values: list[str], value: object | None) -> None:
    cleaned = _clean_scalar(value)
    if cleaned and cleaned not in values:
        values.append(cleaned)


def _candidate_list_values(
    candidate: dict[str, Any], *, list_field: str, fallback_field: str
) -> list[str]:
    values: list[str] = []
    raw_values = candidate.get(list_field)
    if isinstance(raw_values, list):
        for value in raw_values:
            _append_unique(values, value)
    _append_unique(values, candidate.get(fallback_field))
    return values


def _candidate_countries(candidate: dict[str, Any]) -> list[str]:
    countries: list[str] = []
    raw_countries = candidate.get("job_countries")
    if isinstance(raw_countries, list):
        for country in raw_countries:
            _append_unique(countries, country)
    if countries:
        return countries

    _append_unique(countries, candidate.get("country"))
    return countries


COUNTED_ROLE_GROUPS = {
    RoleGroup.AI_EXECUTION.value,
    RoleGroup.AI_PRODUCT.value,
    RoleGroup.UNCLEAR.value,
}


def _counted_posting_entry(
    *, posting_key: object | None, title: object | None, role_group: object | None
) -> dict[str, str] | None:
    cleaned_role_group = _clean_scalar(role_group)
    if cleaned_role_group not in COUNTED_ROLE_GROUPS:
        return None

    cleaned_title = _clean_scalar(title)
    cleaned_posting_key = _clean_scalar(posting_key)
    if not cleaned_title or not cleaned_posting_key:
        return None

    return {
        "posting_key": cleaned_posting_key,
        "job_title_raw": cleaned_title,
    }


def _candidate_posting_entries(candidate: dict[str, Any]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    raw_postings = candidate.get(MERGED_POSTINGS_FIELD)
    if isinstance(raw_postings, list):
        for posting in raw_postings:
            if not isinstance(posting, dict):
                continue
            entry = _counted_posting_entry(
                posting_key=posting.get("posting_key"),
                title=posting.get("job_title_raw"),
                role_group=posting.get("role_group"),
            )
            if entry is not None:
                entries.append(entry)

    if entries:
        return entries

    fallback_key = (
        _clean_scalar(candidate.get("job_id"))
        or _clean_scalar(candidate.get("source_url"))
        or ":".join(
            (
                _company_key(candidate),
                _clean_scalar(candidate.get("job_title_raw")),
                _clean_scalar(candidate.get("country")),
            )
        )
    )
    fallback_entry = _counted_posting_entry(
        posting_key=fallback_key,
        title=candidate.get("job_title_raw"),
        role_group=candidate.get("role_group"),
    )
    return [fallback_entry] if fallback_entry is not None else []


def _company_key(candidate: dict[str, Any]) -> str:
    return normalize_hash_part(candidate.get("company_normalized"))


def _role_classification(role_groups: Iterable[str]) -> str:
    groups = set(role_groups)
    has_execution = RoleGroup.AI_EXECUTION.value in groups
    has_product = RoleGroup.AI_PRODUCT.value in groups

    if has_execution and has_product:
        return RoleGroup.BOTH_EXECUTION_AND_PRODUCT.value
    if has_execution:
        return RoleGroup.AI_EXECUTION.value
    if has_product:
        return RoleGroup.AI_PRODUCT.value
    return RoleGroup.UNCLEAR.value


def _why_interesting(
    *, company: str, countries: list[str], matched_search_terms: list[str]
) -> str:
    country_text = ", ".join(countries) or "the searched countries"
    terms_text = ", ".join(matched_search_terms) or "AI role searches"
    return (
        f"{company} appears in search results for {terms_text} in {country_text}. "
        "Needs manual validation because evidence is title-only."
    )


def aggregate_companies(candidates: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates_by_company: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        company_key = _company_key(candidate)
        if not company_key:
            continue
        candidates_by_company[company_key].append(candidate)

    companies: list[dict[str, Any]] = []
    for company_candidates in candidates_by_company.values():
        countries: list[str] = []
        role_groups: list[str] = []
        ai_execution_titles: list[str] = []
        ai_product_titles: list[str] = []
        matched_search_terms: list[str] = []
        evidence_urls: list[str] = []
        sources: list[str] = []
        evidence_quality: list[str] = []
        seen_posting_keys: set[str] = set()
        title_counts: dict[str, int] = {}
        needs_review = False

        company = _clean_scalar(company_candidates[0].get("company_normalized"))
        for candidate in company_candidates:
            role_group = _clean_scalar(candidate.get("role_group"))
            title = _clean_scalar(candidate.get("job_title_normalized"))

            for country in _candidate_countries(candidate):
                _append_unique(countries, country)
            _append_unique(role_groups, role_group)
            _append_unique(sources, candidate.get("source"))
            _append_unique(evidence_quality, candidate.get("evidence_quality"))

            for source_url in _candidate_list_values(
                candidate,
                list_field=MERGED_SOURCE_URLS_FIELD,
                fallback_field="source_url",
            ):
                _append_unique(evidence_urls, source_url)
            for role_search_term in _candidate_list_values(
                candidate,
                list_field=MERGED_ROLE_SEARCH_TERMS_FIELD,
                fallback_field="role_search_term",
            ):
                _append_unique(matched_search_terms, role_search_term)

            if role_group == RoleGroup.AI_EXECUTION.value:
                _append_unique(ai_execution_titles, title)
            elif role_group == RoleGroup.AI_PRODUCT.value:
                _append_unique(ai_product_titles, title)

            for posting in _candidate_posting_entries(candidate):
                posting_key = posting["posting_key"]
                if posting_key in seen_posting_keys:
                    continue
                seen_posting_keys.add(posting_key)
                raw_title = posting["job_title_raw"]
                title_counts[raw_title] = title_counts.get(raw_title, 0) + 1

            needs_review = needs_review or bool(candidate.get("needs_review", True))

        if not evidence_urls or not matched_search_terms:
            continue

        companies.append(
            {
                "record_type": "company_intelligence_title_only",
                "company": company,
                "countries": countries,
                "role_classification": _role_classification(role_groups),
                "ai_execution_titles": ai_execution_titles,
                "ai_product_titles": ai_product_titles,
                "ai_role_title_counts": [
                    {"title": title, "count": count}
                    for title, count in title_counts.items()
                ],
                "matched_search_terms": matched_search_terms,
                "evidence_urls": evidence_urls,
                "sources": sources,
                "evidence_quality": evidence_quality,
                "needs_review": needs_review,
                "review_status": "new",
                "why_interesting": _why_interesting(
                    company=company,
                    countries=countries,
                    matched_search_terms=matched_search_terms,
                ),
            }
        )

    return sorted(companies, key=lambda item: normalize_hash_part(item["company"]))
