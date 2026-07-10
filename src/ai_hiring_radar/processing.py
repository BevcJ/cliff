from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_hiring_radar.aggregate import aggregate_companies
from ai_hiring_radar.dedupe import (
    MERGED_POSTINGS_FIELD,
    MERGED_ROLE_SEARCH_TERMS_FIELD,
    MERGED_SOURCE_URLS_FIELD,
    dedupe_job_candidates,
)
from ai_hiring_radar.normalizers.ats.registry import normalize_raw_ats_file
from ai_hiring_radar.normalizers.common.raw import ATS_PLATFORMS, iter_raw_ats_response_files
from ai_hiring_radar.storage_json import (
    DEFAULT_DATA_DIR,
    format_date,
    raw_ats_dir,
    write_processed_jsonl,
)


@dataclass(frozen=True)
class ProcessingResult:
    job_candidates_path: Path
    companies_path: Path
    raw_file_count: int
    candidate_count: int
    deduped_candidate_count: int
    company_count: int


def build_job_candidates(
    collection_date: str,
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for raw_file in iter_raw_ats_response_files(collection_date, data_dir=data_dir):
        candidates.extend(normalize_raw_ats_file(raw_file))
    return candidates


def _raw_input_files(
    collection_date: str,
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
) -> list[Path]:
    raw_ats_files = iter_raw_ats_response_files(collection_date, data_dir=data_dir)

    if not raw_ats_files:
        expected_ats_dirs = ", ".join(
            raw_ats_dir(collection_date, data_dir=data_dir, platform=platform).as_posix()
            for platform in ATS_PLATFORMS
        )
        raise FileNotFoundError(
            "No raw ATS input files found for collection date "
            f"{collection_date}. Expected ATS files under one of: {expected_ats_dirs}."
        )

    return raw_ats_files


def _without_dedupe_metadata(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in candidate.items()
        if key
        not in {
            MERGED_POSTINGS_FIELD,
            MERGED_SOURCE_URLS_FIELD,
            MERGED_ROLE_SEARCH_TERMS_FIELD,
        }
    }


def process_collection(
    collection_date: str,
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
) -> ProcessingResult:
    normalized_date = format_date(collection_date)
    raw_ats_files = _raw_input_files(
        normalized_date,
        data_dir=data_dir,
    )

    candidates: list[dict[str, Any]] = []
    for raw_file in raw_ats_files:
        candidates.extend(normalize_raw_ats_file(raw_file))

    deduped_candidates = dedupe_job_candidates(candidates)
    companies = aggregate_companies(deduped_candidates)
    persisted_candidates = [
        _without_dedupe_metadata(candidate) for candidate in deduped_candidates
    ]

    job_candidates_path = write_processed_jsonl(
        f"job_candidates_{normalized_date}.jsonl",
        persisted_candidates,
        data_dir=data_dir,
    )
    companies_path = write_processed_jsonl(
        f"companies_{normalized_date}.jsonl",
        companies,
        data_dir=data_dir,
    )

    return ProcessingResult(
        job_candidates_path=job_candidates_path,
        companies_path=companies_path,
        raw_file_count=len(raw_ats_files),
        candidate_count=len(candidates),
        deduped_candidate_count=len(deduped_candidates),
        company_count=len(companies),
    )
