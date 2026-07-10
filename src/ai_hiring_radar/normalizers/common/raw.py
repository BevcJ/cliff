from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_hiring_radar.models import SourceName
from ai_hiring_radar.storage_json import DEFAULT_DATA_DIR, raw_ats_dir


RAW_ATS_RESPONSE_RECORD_TYPE = "raw_ats_response"
ATS_PLATFORMS = (
    str(SourceName.ASHBY),
    str(SourceName.GREENHOUSE),
    str(SourceName.LEVER),
    str(SourceName.PERSONIO),
    str(SourceName.RECRUITEE),
    str(SourceName.TEAMTAILOR),
    str(SourceName.SMARTRECRUITERS),
    str(SourceName.WORKABLE),
)


def iter_raw_ats_response_files(
    collection_date: str,
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
) -> list[Path]:
    files: list[Path] = []
    for platform in ATS_PLATFORMS:
        raw_dir = raw_ats_dir(collection_date, data_dir=data_dir, platform=platform)
        if not raw_dir.exists():
            continue
        files.extend(path for path in raw_dir.glob("*.json") if path.name != "manifest.json")
    return sorted(files)


def raw_ats_response_payload(raw_record: dict[str, Any]) -> tuple[dict[str, Any], Any]:
    if (
        raw_record.get("record_type") == RAW_ATS_RESPONSE_RECORD_TYPE
        and "response" in raw_record
    ):
        return raw_record, raw_record["response"]

    return {}, raw_record
