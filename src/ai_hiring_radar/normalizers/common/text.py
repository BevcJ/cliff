from __future__ import annotations

from ai_hiring_radar.classify import clean_text


def clean_optional(value: object | None) -> str | None:
    cleaned = clean_text(value)
    return cleaned or None


def append_clean_unique(values: list[str], value: object | None) -> None:
    cleaned = clean_optional(value)
    if cleaned and cleaned not in values:
        values.append(cleaned)


def first_value(values: list[str]) -> str | None:
    return values[0] if values else None


def first_or_empty(values: list[str]) -> str:
    return values[0] if values else ""
