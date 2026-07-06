from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from ai_hiring_radar.config import TaxonomyConfig, load_taxonomy_config
from ai_hiring_radar.models import RoleGroup


AI_SIGNAL_TERMS = (
    "ai",
    "genai",
    "generative ai",
    "llm",
    "artificial intelligence",
)
AI_TRAINER_EXCLUSION_RE = re.compile(
    r"\b(?:ai|artificial intelligence|genai|generative ai|llm)\s+"
    r"(?:quality\s+)?trainer\b|\bmodel\s+trainer\b",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class KnownRole:
    role: str
    group: RoleGroup
    match_key: str


def clean_text(value: object | None) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split()).strip()


def _phrase_key(value: object | None) -> str:
    cleaned = clean_text(value).casefold()
    searchable = re.sub(r"[^a-z0-9]+", " ", cleaned)
    return " ".join(searchable.split())


def _searchable_text(value: object | None) -> str:
    key = _phrase_key(value)
    return f" {key} " if key else " "


def _build_known_roles(taxonomy_config: TaxonomyConfig) -> tuple[KnownRole, ...]:
    roles = [
        KnownRole(role=role, group=RoleGroup.AI_EXECUTION, match_key=_phrase_key(role))
        for role in taxonomy_config.execution_roles
    ]
    roles.extend(
        KnownRole(role=role, group=RoleGroup.AI_PRODUCT, match_key=_phrase_key(role))
        for role in taxonomy_config.product_roles
    )

    return tuple(
        sorted(
            roles,
            key=lambda item: (len(item.match_key.split()), len(item.match_key)),
            reverse=True,
        )
    )


@lru_cache(maxsize=1)
def _default_known_roles() -> tuple[KnownRole, ...]:
    return _build_known_roles(load_taxonomy_config())


def known_roles(taxonomy_config: TaxonomyConfig | None = None) -> tuple[KnownRole, ...]:
    if taxonomy_config is None:
        return _default_known_roles()
    return _build_known_roles(taxonomy_config)


def match_known_role(
    value: object | None,
    *,
    taxonomy_config: TaxonomyConfig | None = None,
) -> KnownRole | None:
    haystack = _searchable_text(value)
    for known_role in known_roles(taxonomy_config):
        if f" {known_role.match_key} " in haystack:
            return known_role
    return None


def has_ai_signal(value: object | None) -> bool:
    haystack = _searchable_text(value)
    return any(f" {_phrase_key(term)} " in haystack for term in AI_SIGNAL_TERMS)


def is_excluded_ai_trainer_title(value: object | None) -> bool:
    return AI_TRAINER_EXCLUSION_RE.search(clean_text(value)) is not None


def normalize_job_title(
    job_title_raw: str,
    *,
    role_search_term: str | None = None,
    taxonomy_config: TaxonomyConfig | None = None,
) -> str:
    title_match = match_known_role(job_title_raw, taxonomy_config=taxonomy_config)
    if title_match is not None:
        return title_match.role

    search_term_match = match_known_role(role_search_term, taxonomy_config=taxonomy_config)
    if search_term_match is not None:
        return search_term_match.role

    return clean_text(job_title_raw)


def classify_role(
    *,
    job_title_raw: str | None,
    job_title_normalized: str | None = None,
    role_search_term: str | None = None,
    taxonomy_config: TaxonomyConfig | None = None,
) -> str:
    for value in (job_title_normalized, job_title_raw, role_search_term):
        known_role = match_known_role(value, taxonomy_config=taxonomy_config)
        if known_role is not None:
            return known_role.group.value

    combined_signal = " ".join(
        clean_text(value) for value in (job_title_raw, job_title_normalized, role_search_term)
    )
    if has_ai_signal(combined_signal):
        return RoleGroup.UNCLEAR.value

    return RoleGroup.UNCLEAR.value
