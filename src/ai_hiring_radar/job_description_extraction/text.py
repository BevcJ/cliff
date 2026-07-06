from __future__ import annotations

from typing import Any


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
    if isinstance(value, list | tuple | set | dict):
        return bool(value)
    return True
