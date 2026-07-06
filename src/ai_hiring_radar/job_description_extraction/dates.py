from __future__ import annotations

from datetime import date, datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def normalize_explicit_date(value: object | None) -> str | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        return _format_datetime(value)

    if isinstance(value, date):
        return value.isoformat()

    if isinstance(value, int | float):
        return _format_timestamp(float(value))

    cleaned = _clean_scalar(value)
    if cleaned is None:
        return None

    if cleaned.isdecimal():
        return _format_timestamp(float(cleaned))

    try:
        parsed_datetime = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except ValueError:
        try:
            return date.fromisoformat(cleaned).isoformat()
        except ValueError:
            return None

    return _format_datetime(parsed_datetime)


def _clean_scalar(value: object | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(str(value).split()).strip()
    return cleaned or None


def _format_timestamp(value: float) -> str | None:
    try:
        if value > 10_000_000_000:
            value = value / 1000
        parsed_datetime = datetime.fromtimestamp(value, tz=timezone.utc)
    except (OSError, OverflowError, ValueError):
        return None
    return _format_datetime(parsed_datetime)


def _format_datetime(value: datetime) -> str:
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc)
    value = value.replace(microsecond=0)
    return value.isoformat().replace("+00:00", "Z")
