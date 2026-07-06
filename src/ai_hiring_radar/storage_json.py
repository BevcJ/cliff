from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Iterable


DEFAULT_DATA_DIR = Path("data")
DEFAULT_SOURCE_NAME = "serper_google"
DEFAULT_ATS_PLATFORM = "ashby"


def format_date(value: date | str | None = None) -> str:
    if value is None:
        return date.today().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return date.fromisoformat(value).isoformat()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "unknown"


def stable_search_filename(
    *, country_code: str, role_term: str, search_location: str
) -> str:
    return (
        f"{slugify(country_code)}_"
        f"{slugify(role_term)}_"
        f"{slugify(search_location)}.json"
    )


def stable_board_filename(*, platform_company_slug: str) -> str:
    return f"{slugify(platform_company_slug)}.json"


def raw_search_dir(
    collection_date: date | str | None = None,
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
    source_name: str = DEFAULT_SOURCE_NAME,
) -> Path:
    return data_dir / "raw" / "searches" / format_date(collection_date) / source_name


def raw_ats_dir(
    collection_date: date | str | None = None,
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
    platform: str = DEFAULT_ATS_PLATFORM,
) -> Path:
    return data_dir / "raw" / "ats" / format_date(collection_date) / platform


def ats_discovery_dir(
    collection_date: date | str | None = None,
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
    platform: str = DEFAULT_ATS_PLATFORM,
) -> Path:
    return data_dir / "raw" / "ats_discovery" / format_date(collection_date) / platform


def processed_dir(*, data_dir: Path = DEFAULT_DATA_DIR) -> Path:
    return data_dir / "processed"


def exports_dir(*, data_dir: Path = DEFAULT_DATA_DIR) -> Path:
    return data_dir / "exports"


def write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")
    return path


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def read_jsonl(path: Path) -> list[Any]:
    with path.open("r", encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def write_raw_search_response(
    response: dict[str, Any],
    *,
    country_code: str,
    role_term: str,
    search_location: str,
    collection_date: date | str | None = None,
    data_dir: Path = DEFAULT_DATA_DIR,
) -> Path:
    path = raw_search_dir(collection_date, data_dir=data_dir) / stable_search_filename(
        country_code=country_code,
        role_term=role_term,
        search_location=search_location,
    )
    return write_json(path, response)


def write_raw_ats_response(
    response: dict[str, Any],
    *,
    platform_company_slug: str,
    collection_date: date | str | None = None,
    data_dir: Path = DEFAULT_DATA_DIR,
    platform: str = DEFAULT_ATS_PLATFORM,
) -> Path:
    path = raw_ats_dir(
        collection_date,
        data_dir=data_dir,
        platform=platform,
    ) / stable_board_filename(platform_company_slug=platform_company_slug)
    return write_json(path, response)


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            file.write("\n")
    return path


def append_jsonl(path: Path, record: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
        file.write("\n")
    return path


def write_processed_jsonl(
    filename: str,
    records: Iterable[dict[str, Any]],
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
) -> Path:
    return write_jsonl(processed_dir(data_dir=data_dir) / filename, records)


def read_processed_jsonl(
    filename: str,
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
) -> list[Any]:
    return read_jsonl(processed_dir(data_dir=data_dir) / filename)


def write_export_text(
    filename: str,
    content: str,
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
) -> Path:
    path = exports_dir(data_dir=data_dir) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path
