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


def _recruitee_offers(response: Any) -> list[dict[str, Any]]:
    if not isinstance(response, dict):
        return []
    offers = response.get("offers")
    if not isinstance(offers, list):
        return []
    return [item for item in offers if isinstance(item, dict)]


def _recruitee_offer_detail(
    *,
    metadata: dict[str, Any],
    platform_job_id: str,
) -> dict[str, Any] | None:
    detail_responses = metadata.get("offer_detail_responses")
    if not isinstance(detail_responses, dict):
        return None

    response = detail_responses.get(platform_job_id)
    if not isinstance(response, dict):
        return None

    offer = response.get("offer")
    if isinstance(offer, dict):
        return offer
    return response


def _recruitee_records(
    offer: dict[str, Any],
    detail: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    return [detail, offer] if detail is not None else [offer]


def _recruitee_record_value(
    records: list[dict[str, Any]],
    *fields: str,
) -> str | None:
    for record in records:
        for field in fields:
            cleaned = clean_optional(record.get(field))
            if cleaned is not None:
                return cleaned
    return None


def _recruitee_raw_value(
    records: list[dict[str, Any]],
    *fields: str,
) -> Any | None:
    for record in records:
        for field in fields:
            value = record.get(field)
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            if isinstance(value, (list, dict)) and not value:
                continue
            return value
    return None


def _recruitee_named_value(value: object | None) -> str | None:
    if isinstance(value, dict):
        return clean_optional(value.get("name") or value.get("title"))
    return clean_optional(value)


def _recruitee_department(records: list[dict[str, Any]]) -> str | None:
    return _recruitee_named_value(_recruitee_raw_value(records, "department"))


def _recruitee_location_display(value: object | None) -> str | None:
    if isinstance(value, dict):
        full_address = clean_optional(
            value.get("full_address") or value.get("fullAddress")
        )
        if full_address is not None:
            return full_address

        city = clean_optional(value.get("city"))
        country = clean_optional(value.get("country") or value.get("country_code"))
        if city and country:
            return f"{city}, {country}"
        return clean_optional(value.get("name") or value.get("location") or city)
    return clean_optional(value)


def _recruitee_location_items(record: dict[str, Any]) -> list[object]:
    locations = record.get("locations")
    if not isinstance(locations, list):
        return []
    return locations


def _recruitee_location_values_from_record(record: dict[str, Any]) -> list[str]:
    values: list[str] = []
    append_clean_unique(values, _recruitee_location_display(record.get("location")))

    for location in _recruitee_location_items(record):
        append_clean_unique(values, _recruitee_location_display(location))
        if not isinstance(location, dict):
            continue
        append_clean_unique(values, location.get("full_address"))

    append_clean_unique(values, record.get("city"))
    append_clean_unique(values, record.get("country"))
    append_clean_unique(values, record.get("country_code"))
    return values


def _recruitee_location_values(records: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for record in records:
        for location in _recruitee_location_values_from_record(record):
            append_clean_unique(values, location)

    for record in records:
        for location in _recruitee_location_items(record):
            if not isinstance(location, dict):
                continue
            for field in ("city", "country", "country_code"):
                append_clean_unique(values, location.get(field))
    return values


def _recruitee_display_location(records: list[dict[str, Any]]) -> str | None:
    for record in records:
        location = _recruitee_location_display(record.get("location"))
        if location is not None:
            return location
    return first_value(_recruitee_location_values(records))


def _recruitee_country_code(value: object | None) -> str | None:
    country_code = clean_text(value).casefold()
    if country_code == "gb":
        country_code = "uk"
    if country_code in COUNTRY_NAMES_BY_CODE:
        return country_code
    return None


def _append_recruitee_country_code(values: list[str], value: object | None) -> None:
    country_code = _recruitee_country_code(value)
    if country_code is not None and country_code not in values:
        values.append(country_code)


def _recruitee_country_codes(records: list[dict[str, Any]]) -> list[str]:
    country_codes: list[str] = []
    for record in records:
        _append_recruitee_country_code(country_codes, record.get("country_code"))
        _append_recruitee_country_code(country_codes, record.get("countryCode"))
        _append_recruitee_country_code(country_codes, record.get("country"))
        for location in _recruitee_location_items(record):
            if not isinstance(location, dict):
                continue
            _append_recruitee_country_code(country_codes, location.get("country_code"))
            _append_recruitee_country_code(country_codes, location.get("countryCode"))
            _append_recruitee_country_code(country_codes, location.get("country"))
    return country_codes


def _recruitee_country_values(records: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for record in records:
        append_clean_unique(values, record.get("country"))
        append_clean_unique(values, record.get("country_code"))
        for location in _recruitee_location_items(record):
            if isinstance(location, dict):
                append_clean_unique(values, location.get("country"))
                append_clean_unique(values, location.get("country_code"))
                append_clean_unique(values, location.get("full_address"))
            else:
                append_clean_unique(values, location)
    return values


def _recruitee_country_inference(
    *,
    records: list[dict[str, Any]],
    locations: list[str],
) -> CountryInference:
    country_codes = _recruitee_country_codes(records)
    if country_codes:
        return CountryInference(
            country_codes=country_codes,
            countries=[COUNTRY_NAMES_BY_CODE[country_code] for country_code in country_codes],
        )

    values = _recruitee_country_values(records)
    values.extend(locations)
    return infer_countries_from_locations(values)


def _recruitee_bool_value(records: list[dict[str, Any]], field: str) -> bool | None:
    for record in records:
        value = record.get(field)
        if isinstance(value, bool):
            return value
    return None


def _recruitee_workplace_type(records: list[dict[str, Any]]) -> str | None:
    if _recruitee_bool_value(records, "hybrid") is True:
        return "hybrid"
    if _recruitee_bool_value(records, "remote") is True:
        return "remote"
    if _recruitee_bool_value(records, "on_site") is True:
        return "on_site"
    return None


def _recruitee_source_url(
    *,
    records: list[dict[str, Any]],
    board_url: str,
    offer_slug: str | None,
) -> str:
    source_url = _recruitee_record_value(
        records,
        "careers_url",
        "careersUrl",
        "job_url",
        "jobUrl",
        "public_url",
        "url",
    )
    if source_url is not None:
        return source_url
    if offer_slug is not None:
        return f"{board_url.rstrip('/')}/o/{quote(offer_slug, safe='-_~.')}"
    return board_url


def _recruitee_description(records: list[dict[str, Any]]) -> str | None:
    values: list[str] = []
    for field in (
        "description",
        "requirements",
        "description_requirements",
        "descriptionRequirements",
    ):
        for record in records:
            append_clean_unique(values, record.get(field))
    return "\n\n".join(values) or None


def normalize_recruitee_offer(
    *,
    metadata: dict[str, Any],
    offer: dict[str, Any],
    raw_file: Path,
) -> dict[str, Any] | None:
    platform_company_slug = clean_text(metadata.get("platform_company_slug"))
    if not platform_company_slug:
        return None

    listing_platform_job_id = clean_text(offer.get("id")) or clean_text(offer.get("slug"))
    detail = (
        _recruitee_offer_detail(
            metadata=metadata,
            platform_job_id=listing_platform_job_id,
        )
        if listing_platform_job_id
        else None
    )
    records = _recruitee_records(offer, detail)
    job_title_raw = _recruitee_record_value(records, "title", "name")
    if job_title_raw is None:
        return None
    if not is_ai_role_title_candidate(job_title_raw):
        return None

    board_url = clean_text(metadata.get("board_url")) or (
        f"https://{platform_company_slug}.recruitee.com"
    )
    location = _recruitee_display_location(records)
    platform_job_id = listing_platform_job_id or stable_sha256(
        (str(SourceName.RECRUITEE), platform_company_slug, job_title_raw, location)
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

    offer_slug = _recruitee_record_value(records, "slug")
    source_url = _recruitee_source_url(
        records=records,
        board_url=board_url,
        offer_slug=offer_slug,
    )
    company_raw = _recruitee_named_value(
        _recruitee_raw_value(records, "company")
    ) or company_name_from_slug(platform_company_slug)
    company_normalized = normalize_company_name(company_raw)
    location_values = _recruitee_location_values(records)
    country_inference = _recruitee_country_inference(
        records=records,
        locations=location_values,
    )
    department = _recruitee_department(records)

    return {
        "record_type": "job_candidate",
        "job_id": stable_sha256(
            (str(SourceName.RECRUITEE), platform_company_slug, platform_job_id)
        ),
        "country_code": first_or_empty(country_inference.country_codes),
        "country": first_value(country_inference.countries),
        "job_country_codes": country_inference.country_codes,
        "job_countries": country_inference.countries,
        "search_location_label": clean_optional(metadata.get("search_location_label")),
        "query_location": clean_optional(metadata.get("query_location")),
        "serper_location": clean_optional(metadata.get("serper_location")),
        "source": str(SourceName.RECRUITEE),
        "source_mode": str(SourceMode.PUBLIC_JOB_BOARD_ENDPOINT),
        "source_url": source_url,
        "board_url": board_url,
        "job_url": source_url if source_url != board_url else None,
        "apply_url": _recruitee_record_value(
            records,
            "careers_apply_url",
            "careersApplyUrl",
            "apply_url",
            "applyUrl",
        ),
        "platform": str(SourceName.RECRUITEE),
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
        "team": department,
        "department": department,
        "location": location,
        "job_location_raw": location,
        "job_locations_raw": location_values,
        "locations": _recruitee_raw_value(records, "locations"),
        "location_country_raw": _recruitee_record_value(
            records,
            "country_code",
            "country",
        ),
        "workplace_type": _recruitee_workplace_type(records),
        "remote": _recruitee_bool_value(records, "remote"),
        "hybrid": _recruitee_bool_value(records, "hybrid"),
        "on_site": _recruitee_bool_value(records, "on_site"),
        "employment_type": _recruitee_record_value(
            records,
            "employment_type_code",
            "employmentTypeCode",
            "employment_type",
            "employmentType",
            "contract_type",
        ),
        "compensation": _recruitee_raw_value(records, "salary", "compensation"),
        "description": _recruitee_description(records),
        "requirements": _recruitee_record_value(records, "requirements"),
        "offer_slug": offer_slug,
        "company_id": _recruitee_record_value(records, "company_id", "companyId"),
        "source_published_at": _recruitee_record_value(
            records,
            "published_at",
            "posted",
            "created_at",
        ),
        "source_updated_at": _recruitee_record_value(records, "updated_at", "updated"),
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
        for offer in _recruitee_offers(response)
        if (
            candidate := normalize_recruitee_offer(
                metadata=metadata,
                offer=offer,
                raw_file=raw_file,
            )
        )
        is not None
    ]
