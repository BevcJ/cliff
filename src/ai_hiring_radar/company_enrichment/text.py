from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


def clean_scalar(value: object | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(str(value).split()).strip()
    return cleaned or None


def first_clean(record: dict[str, Any], *fields: str) -> str | None:
    for field in fields:
        cleaned = clean_scalar(record.get(field))
        if cleaned is not None:
            return cleaned
    return None


def has_value(value: object | None) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def normalize_source_urls(values: object | None) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        return []

    urls: list[str] = []
    for value in values:
        cleaned = clean_scalar(value)
        if cleaned is None or not _is_public_url(cleaned):
            continue
        if cleaned not in urls:
            urls.append(cleaned)
    return urls


def _is_public_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def is_ats_url(value: object | None) -> bool:
    cleaned = clean_scalar(value)
    if cleaned is None:
        return False

    parsed = urlparse(cleaned)
    host = parsed.netloc.casefold()
    path = parsed.path.casefold()
    return (
        host in {
            "apply.workable.com",
            "api.smartrecruiters.com",
            "careers.smartrecruiters.com",
            "jobs.smartrecruiters.com",
        }
        or (host.endswith(".workable.com") and host not in {"www.workable.com"})
        or host.endswith(".jobs.personio.com")
        or host.endswith(".recruitee.com")
        or host == "jobs.personio.com"
        or host == "jobs.ashbyhq.com"
        or host == "jobs.lever.co"
        or host.endswith(".teamtailor.com")
        or host == "boards.greenhouse.io"
        or host == "job-boards.greenhouse.io"
        or (host.endswith(".greenhouse.io") and "/jobs/" in path)
    )


def is_low_trust_contact_source_url(value: object | None) -> bool:
    cleaned = clean_scalar(value)
    if cleaned is None:
        return False

    host = urlparse(cleaned).netloc.casefold()
    return any(
        host == domain or host.endswith(f".{domain}")
        for domain in (
            "contactout.com",
            "rocketreach.co",
            "apollo.io",
            "hunter.io",
            "lusha.com",
            "success.ai",
            "thecompanycheck.com",
        )
    )


def has_non_ats_source_url(values: object | None) -> bool:
    return any(not is_ats_url(url) for url in normalize_source_urls(values))
