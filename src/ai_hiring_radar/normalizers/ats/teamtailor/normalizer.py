from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

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


def _html_to_text(value: object | None) -> str | None:
    raw = clean_text(value)
    if not raw:
        return None

    text = unescape(raw)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(
        r"</(?:p|div|li|h[1-6]|ul|ol)>",
        "\n",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"<[^>]+>", " ", text)
    return clean_optional(unescape(text))


def _teamtailor_items(response: Any) -> list[ET.Element]:
    if not isinstance(response, str):
        return []

    try:
        root = ET.fromstring(response)
    except ET.ParseError:
        return []

    if _xml_local_name(root.tag) == "item":
        return [root]
    return [element for element in root.iter() if _xml_local_name(element.tag) == "item"]


def _teamtailor_locations(item: ET.Element) -> list[ET.Element]:
    container = _xml_first_child(item, "locations")
    if container is None:
        return []
    return _xml_children(container, "location")


def _teamtailor_location_display(location: ET.Element) -> str | None:
    values: list[str] = []
    for field in ("name", "city", "country"):
        append_clean_unique(values, _xml_child_text(location, field))
    return ", ".join(values) or None


def _teamtailor_location_values(item: ET.Element) -> list[str]:
    values: list[str] = []
    for location in _teamtailor_locations(item):
        append_clean_unique(values, _teamtailor_location_display(location))
    return values


def _teamtailor_country_source_locations(item: ET.Element) -> list[str]:
    values: list[str] = []
    for location in _teamtailor_locations(item):
        append_clean_unique(values, _xml_child_text(location, "country"))
        append_clean_unique(values, _xml_child_text(location, "city"))
        append_clean_unique(values, _xml_child_text(location, "name"))
        append_clean_unique(values, _teamtailor_location_display(location))
    return values


def _teamtailor_workplace_type(item: ET.Element) -> str | None:
    remote_status = clean_text(_xml_child_text(item, "remoteStatus")).casefold()
    if not remote_status or remote_status == "none":
        return None
    if remote_status in {"remote", "fully_remote"}:
        return "remote"
    if remote_status == "hybrid":
        return "hybrid"
    return remote_status


def _teamtailor_pub_date(value: object | None) -> str | None:
    cleaned = clean_optional(value)
    if cleaned is None:
        return None

    try:
        parsed_date = parsedate_to_datetime(cleaned)
    except (TypeError, ValueError, IndexError, OverflowError):
        return cleaned

    return parsed_date.replace(microsecond=0).isoformat()


def _teamtailor_link_slug(source_url: str, board_url: str) -> str | None:
    if source_url == board_url:
        return None
    parsed_url = urlparse(source_url)
    return clean_optional(parsed_url.path.rstrip("/").rsplit("/", 1)[-1])


def normalize_teamtailor_item(
    *,
    metadata: dict[str, Any],
    item: ET.Element,
    raw_file: Path,
) -> dict[str, Any] | None:
    job_title_raw = _xml_child_text(item, "title")
    if job_title_raw is None:
        return None
    if not is_ai_role_title_candidate(job_title_raw):
        return None

    platform_company_slug = clean_text(metadata.get("platform_company_slug"))
    if not platform_company_slug:
        return None

    board_url = clean_text(metadata.get("board_url")) or (
        f"https://{quote(platform_company_slug, safe='-_~.')}.teamtailor.com"
    )
    source_url = _xml_child_text(item, "link") or board_url
    location_values = _teamtailor_location_values(item)
    location = first_value(location_values)
    platform_job_id = (
        _xml_child_text(item, "guid")
        or _teamtailor_link_slug(source_url, board_url)
        or stable_sha256(
            (str(SourceName.TEAMTAILOR), platform_company_slug, job_title_raw, location)
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

    company_raw = company_name_from_slug(platform_company_slug)
    company_normalized = normalize_company_name(company_raw)
    country_source_locations = _teamtailor_country_source_locations(item)
    country_inference = infer_countries_from_locations(country_source_locations)
    description_html = _xml_child_text(item, "description")
    department = _xml_child_text(item, "department")

    return {
        "record_type": "job_candidate",
        "job_id": stable_sha256(
            (str(SourceName.TEAMTAILOR), platform_company_slug, platform_job_id)
        ),
        "country_code": first_or_empty(country_inference.country_codes),
        "country": first_value(country_inference.countries),
        "job_country_codes": country_inference.country_codes,
        "job_countries": country_inference.countries,
        "search_location_label": clean_optional(metadata.get("search_location_label")),
        "query_location": clean_optional(metadata.get("query_location")),
        "serper_location": clean_optional(metadata.get("serper_location")),
        "source": str(SourceName.TEAMTAILOR),
        "source_mode": str(SourceMode.PUBLIC_JOB_BOARD_ENDPOINT),
        "source_url": source_url,
        "board_url": board_url,
        "job_url": source_url if source_url != board_url else None,
        "platform": str(SourceName.TEAMTAILOR),
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
        "teamtailor_role": _xml_child_text(item, "role"),
        "division": _xml_child_text(item, "division"),
        "location": location,
        "job_location_raw": location,
        "job_locations_raw": location_values,
        "workplace_type": _teamtailor_workplace_type(item),
        "remote_status": _xml_child_text(item, "remoteStatus"),
        "description": _html_to_text(description_html),
        "description_html": description_html,
        "source_created_at": _teamtailor_pub_date(_xml_child_text(item, "pubDate")),
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
        for item in _teamtailor_items(response)
        if (
            candidate := normalize_teamtailor_item(
                metadata=metadata,
                item=item,
                raw_file=raw_file,
            )
        )
        is not None
    ]
