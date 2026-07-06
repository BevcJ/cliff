from __future__ import annotations

import hashlib


HASH_SEPARATOR = " | "


def normalize_hash_part(value: object | None) -> str:
    return " ".join(str(value or "").strip().lower().split())


def stable_sha256(parts: list[object | None] | tuple[object | None, ...]) -> str:
    normalized = HASH_SEPARATOR.join(normalize_hash_part(part) for part in parts)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def job_candidate_id(
    *,
    source_url: str | None,
    country_code: str,
    role_search_term: str,
    job_title_raw: str,
    snippet: str | None = None,
) -> str:
    if normalize_hash_part(source_url):
        return stable_sha256(
            (source_url, country_code, role_search_term, job_title_raw)
        )

    return stable_sha256((country_code, role_search_term, job_title_raw, snippet))
