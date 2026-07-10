from __future__ import annotations

import re

from ai_hiring_radar.classify import clean_text


GENERIC_COMPANY_VALUES = {
    "careers",
    "hiring",
    "jobs",
    "linkedin",
    "remote",
}


def clean_company_candidate(value: object | None) -> str | None:
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
    return clean_company_candidate(company_raw)


def company_name_from_slug(platform_company_slug: str) -> str | None:
    words = clean_text(platform_company_slug.replace("-", " ").replace("_", " "))
    if not words:
        return None
    return " ".join(word[:1].upper() + word[1:] for word in words.split())
