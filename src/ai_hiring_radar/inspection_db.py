from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from ai_hiring_radar.inspection import (
    CompanyInspectionDataset,
    build_company_snapshot_payload,
    load_company_inspection_data,
)
from ai_hiring_radar.storage_json import DEFAULT_DATA_DIR, format_date


@dataclass(frozen=True)
class InspectionDatabaseSyncResult:
    collection_date: str
    snapshot_count: int
    job_count: int
    database_url_configured: bool


SUMMARY_PAYLOAD_FIELDS = (
    "inspection_artifact_version",
    "record_type",
    "company",
    "company_key",
    "countries",
    "role_classification",
    "role_groups",
    "sources",
    "workplace_modes",
    "ai_team_contexts",
    "delivery_contexts",
    "company_type",
    "company_size",
    "ai_tech_forward_signal",
    "job_count",
    "job_description_extract_count",
    "has_contacts",
    "has_job_description_extracts",
    "has_company_enrichment",
)


def sync_inspection_database(
    collection_date: str,
    *,
    database_url: str,
    data_dir: Path = DEFAULT_DATA_DIR,
) -> InspectionDatabaseSyncResult:
    normalized_date = format_date(collection_date)
    if not database_url.strip():
        raise ValueError("database_url is required")

    dataset = load_company_inspection_data(normalized_date, data_dir=data_dir)
    snapshots = [build_inspection_company_snapshot(record) for record in dataset.records]
    snapshot_count = len(snapshots)
    job_count = sum(int(snapshot["job_count"] or 0) for snapshot in snapshots)
    sync_summary = _sync_summary(dataset, data_dir=data_dir)

    with psycopg.connect(database_url) as conn:
        with conn.transaction():
            with conn.cursor() as cursor:
                cursor.execute(
                    "delete from public.inspection_collections where collection_date = %s",
                    (normalized_date,),
                )
                cursor.execute(
                    """
                    insert into public.inspection_collections (
                      collection_date,
                      source_kind,
                      snapshot_count,
                      job_count,
                      sync_summary,
                      synced_at
                    ) values (%s, %s, %s, %s, %s, now())
                    """,
                    (
                        normalized_date,
                        "jsonl",
                        snapshot_count,
                        job_count,
                        Jsonb(sync_summary),
                    ),
                )
                if snapshots:
                    cursor.executemany(
                        """
                        insert into public.inspection_company_snapshots (
                          collection_date,
                          company_key,
                          company,
                          countries,
                          sources,
                          workplace_modes,
                          ai_team_contexts,
                          delivery_contexts,
                          role_classification,
                          role_groups,
                          company_type,
                          company_size,
                          ai_tech_forward_signal,
                          job_count,
                          job_description_extract_count,
                          has_contacts,
                          has_job_description_extracts,
                          has_company_enrichment,
                          search_text,
                          summary_payload,
                          detail_payload,
                          updated_at
                        ) values (
                          %(collection_date)s,
                          %(company_key)s,
                          %(company)s,
                          %(countries)s,
                          %(sources)s,
                          %(workplace_modes)s,
                          %(ai_team_contexts)s,
                          %(delivery_contexts)s,
                          %(role_classification)s,
                          %(role_groups)s,
                          %(company_type)s,
                          %(company_size)s,
                          %(ai_tech_forward_signal)s,
                          %(job_count)s,
                          %(job_description_extract_count)s,
                          %(has_contacts)s,
                          %(has_job_description_extracts)s,
                          %(has_company_enrichment)s,
                          %(search_text)s,
                          %(summary_payload)s,
                          %(detail_payload)s,
                          now()
                        )
                        """,
                        [
                            _snapshot_insert_payload(normalized_date, snapshot)
                            for snapshot in snapshots
                        ],
                    )

    return InspectionDatabaseSyncResult(
        collection_date=normalized_date,
        snapshot_count=snapshot_count,
        job_count=job_count,
        database_url_configured=True,
    )


def build_inspection_company_snapshot(record: dict[str, Any]) -> dict[str, Any]:
    detail_payload = build_company_snapshot_payload(record)
    company_key = _clean_text(detail_payload.get("company_key"))
    if not company_key:
        raise ValueError("company_key is required for inspection database snapshots")
    company = _clean_text(detail_payload.get("company")) or company_key

    snapshot = {
        "company_key": company_key,
        "company": company,
        "countries": _clean_list(detail_payload.get("countries")),
        "sources": _record_sources(detail_payload),
        "workplace_modes": _clean_list(detail_payload.get("workplace_modes")),
        "ai_team_contexts": _clean_list(detail_payload.get("ai_team_contexts")),
        "delivery_contexts": _clean_list(detail_payload.get("delivery_contexts")),
        "role_classification": _clean_text(detail_payload.get("role_classification")) or None,
        "role_groups": _clean_list(detail_payload.get("role_groups")),
        "company_type": _clean_text(detail_payload.get("company_type")) or None,
        "company_size": _clean_text(detail_payload.get("company_size")) or None,
        "ai_tech_forward_signal": _clean_text(detail_payload.get("ai_tech_forward_signal"))
        or None,
        "job_count": _int_value(detail_payload.get("job_count")),
        "job_description_extract_count": _int_value(
            detail_payload.get("job_description_extract_count")
        ),
        "has_contacts": bool(detail_payload.get("has_contacts")),
        "has_job_description_extracts": bool(
            detail_payload.get("has_job_description_extracts")
        ),
        "has_company_enrichment": bool(detail_payload.get("has_company_enrichment")),
        "search_text": build_inspection_snapshot_search_text(detail_payload),
        "summary_payload": _summary_payload(detail_payload),
        "detail_payload": detail_payload,
    }
    return snapshot


def build_inspection_snapshot_search_text(record: dict[str, Any]) -> str:
    values: list[str] = [
        _clean_text(record.get("company")),
        _clean_text(record.get("industry")),
        _clean_text(record.get("company_description")),
    ]
    values.extend(_clean_list(record.get("ai_execution_titles")))
    values.extend(_clean_list(record.get("ai_product_titles")))
    values.extend(_clean_list(record.get("data_science_titles")))
    values.extend(_clean_list(record.get("machine_learning_titles")))
    values.extend(_clean_list(record.get("matched_search_terms")))
    for title_count in record.get("ai_role_title_counts") or []:
        if isinstance(title_count, dict):
            values.append(_clean_text(title_count.get("title")))
    for job in record.get("jobs") or []:
        if not isinstance(job, dict):
            continue
        values.append(_clean_text(job.get("job_title_raw")))
        values.append(_clean_text(job.get("job_title_normalized")))
    return " ".join(value for value in values if value)


def _snapshot_insert_payload(
    collection_date: str,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    payload = dict(snapshot)
    payload["collection_date"] = collection_date
    payload["summary_payload"] = Jsonb(payload["summary_payload"])
    payload["detail_payload"] = Jsonb(payload["detail_payload"])
    return payload


def _sync_summary(
    dataset: CompanyInspectionDataset,
    *,
    data_dir: Path,
) -> dict[str, Any]:
    paths = {
        "companies": dataset.paths.companies_path.as_posix(),
        "job_candidates": dataset.paths.candidates_path.as_posix(),
        "job_description_extracts": dataset.paths.job_description_extracts_path.as_posix(),
        "company_enrichment_extracts": dataset.paths.company_enrichment_extracts_path.as_posix(),
    }
    return {
        "source_kind": "jsonl",
        "data_dir": data_dir.as_posix(),
        "source_paths": paths,
        "missing_optional_files": [
            path.as_posix() for path in dataset.missing_optional_files
        ],
        "load_counts": asdict(dataset.counts),
    }


def _summary_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {
        field: record[field]
        for field in SUMMARY_PAYLOAD_FIELDS
        if field in record and record[field] not in (None, [], {})
    }


def _record_sources(record: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for source in _clean_list(record.get("sources")):
        _append_unique(values, source)
    for job in record.get("jobs") or []:
        if not isinstance(job, dict):
            continue
        _append_unique(values, job.get("platform"))
        _append_unique(values, job.get("source"))
    return values


def _clean_list(value: object | None) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    values: list[str] = []
    for item in value:
        _append_unique(values, item)
    return values


def _append_unique(values: list[str], value: object | None) -> None:
    cleaned = _clean_text(value)
    if cleaned and cleaned not in values:
        values.append(cleaned)


def _clean_text(value: object | None) -> str:
    return " ".join(str(value or "").split()).strip()


def _int_value(value: object | None) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        return int(str(value or "0"))
    except ValueError:
        return 0
