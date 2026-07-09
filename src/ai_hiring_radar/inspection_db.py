from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ai_hiring_radar.inspection import (
    CompanyInspectionDataset,
    InspectionInputPaths,
    InspectionLoadCounts,
    compact_company_inspection_record,
    load_company_inspection_data,
)
from ai_hiring_radar.storage_json import DEFAULT_DATA_DIR, format_date, processed_dir


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


def load_company_inspection_data_from_database(
    collection_date: str,
    *,
    database_url: str,
) -> CompanyInspectionDataset | None:
    normalized_date = format_date(collection_date)
    if not database_url.strip():
        return None

    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cursor:
            rows = cursor.execute(
                """
                select
                  s.detail_payload,
                  c.synced_at
                from public.inspection_company_snapshots s
                join public.inspection_collections c
                  on c.collection_date = s.collection_date
                where s.collection_date = %s
                order by lower(s.company), s.company_key
                """,
                (normalized_date,),
            ).fetchall()

            collection_row = None
            if not rows:
                collection_row = cursor.execute(
                    """
                    select synced_at
                    from public.inspection_collections
                    where collection_date = %s
                    """,
                    (normalized_date,),
                ).fetchone()

    if not rows:
        if collection_row is None:
            return None
        return CompanyInspectionDataset(
            collection_date=normalized_date,
            records=[],
            paths=_database_dataset_paths(normalized_date),
            missing_optional_files=[],
            counts=_counts_from_records([]),
            data_source="database",
            synced_at=_serialize_value(collection_row.get("synced_at")),
        )

    records = [_json_payload(row.get("detail_payload")) for row in rows]
    records = [record for record in records if record]
    if not records:
        return None

    return CompanyInspectionDataset(
        collection_date=normalized_date,
        records=records,
        paths=_database_dataset_paths(normalized_date),
        missing_optional_files=[],
        counts=_counts_from_records(records),
        data_source="database",
        synced_at=_serialize_value(rows[0].get("synced_at")),
    )


def list_synced_collection_dates(
    *,
    database_url: str,
) -> list[str]:
    if not database_url.strip():
        return []

    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cursor:
            rows = cursor.execute(
                """
                select collection_date
                from public.inspection_collections
                order by collection_date
                """
            ).fetchall()

    dates: list[str] = []
    for row in rows:
        value = _serialize_value(row.get("collection_date"))
        if value:
            dates.append(format_date(value))
    return dates


def build_inspection_company_snapshot(record: dict[str, Any]) -> dict[str, Any]:
    detail_payload = compact_company_inspection_record(record)
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


def _database_dataset_paths(collection_date: str) -> InspectionInputPaths:
    root = processed_dir(data_dir=DEFAULT_DATA_DIR)
    return InspectionInputPaths(
        companies_path=root / f"companies_{collection_date}.jsonl",
        candidates_path=root / f"job_candidates_{collection_date}.jsonl",
        job_description_extracts_path=root
        / f"job_description_extracts_{collection_date}.jsonl",
        company_enrichment_extracts_path=root
        / f"company_enrichment_extracts_{collection_date}.jsonl",
    )


def _counts_from_records(records: list[dict[str, Any]]) -> InspectionLoadCounts:
    return InspectionLoadCounts(
        companies_loaded=len(records),
        candidates_loaded=sum(int(record.get("job_count") or 0) for record in records),
        job_description_extracts_loaded=sum(
            int(record.get("job_description_extract_count") or 0) for record in records
        ),
        company_enrichments_loaded=sum(
            1 for record in records if record.get("has_company_enrichment")
        ),
    )


def _json_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


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


def _serialize_value(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat") and not isinstance(value, str):
        return value.isoformat()
    return str(value)
