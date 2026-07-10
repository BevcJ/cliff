from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from urllib.parse import quote

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
    return clean_optional(child.text)


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
    if not is_ai_role_title_candidate(job_title_raw):
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
        (str(SourceName.PERSONIO), platform_company_slug, job_title_raw, location)
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

    company_raw = company_name_from_slug(platform_company_slug)
    company_normalized = normalize_company_name(company_raw)
    location_values: list[str] = []
    append_clean_unique(location_values, location)
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
            (str(SourceName.PERSONIO), platform_company_slug, platform_job_id)
        ),
        "country_code": first_or_empty(country_inference.country_codes),
        "country": first_value(country_inference.countries),
        "job_country_codes": country_inference.country_codes,
        "job_countries": country_inference.countries,
        "search_location_label": clean_optional(metadata.get("search_location_label")),
        "query_location": clean_optional(metadata.get("query_location")),
        "serper_location": clean_optional(metadata.get("serper_location")),
        "source": str(SourceName.PERSONIO),
        "source_mode": str(SourceMode.PUBLIC_JOB_BOARD_ENDPOINT),
        "source_url": source_url,
        "board_url": board_url,
        "job_url": source_url if source_url != board_url else None,
        "platform": str(SourceName.PERSONIO),
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
