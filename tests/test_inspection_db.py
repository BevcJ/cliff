from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from ai_hiring_radar import inspection_db
from ai_hiring_radar.storage_json import write_processed_jsonl


def _record(**overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "company": "Acme AI",
        "company_key": "acme ai",
        "countries": ["Netherlands"],
        "sources": ["lever"],
        "role_classification": "AI Execution Role",
        "ai_execution_titles": ["AI Engineer"],
        "ai_product_titles": [],
        "ai_role_title_counts": [{"title": "Senior AI Engineer", "count": 1}],
        "matched_search_terms": ["AI Engineer"],
        "industry": "Software",
        "company_description": "Builds AI workflow tooling.",
        "company_type": "ai_native",
        "company_size": "101-500",
        "ai_tech_forward_signal": "strong",
        "workplace_modes": ["remote"],
        "ai_team_contexts": ["existing_ai_team"],
        "delivery_contexts": ["internal"],
        "job_count": 1,
        "job_description_extract_count": 1,
        "has_contacts": True,
        "has_job_description_extracts": True,
        "has_company_enrichment": True,
        "raw_company_record": {"secret": "raw"},
        "raw_company_enrichment_record": {"secret": "raw enrichment"},
        "jobs": [
            {
                "job_id": "job-1",
                "job_title_raw": "Senior AI Engineer",
                "job_title_normalized": "AI Engineer",
                "platform": "ashby",
                "source": "ats",
                "workplace_mode": "remote",
                "has_description": True,
                "description": "Secret full job description text.",
                "description_plain": "Secret plain description.",
                "raw_candidate_record": {"secret": "candidate"},
                "raw_job_description_extract": {"secret": "extract"},
            }
        ],
    }
    record.update(overrides)
    return record


def test_build_inspection_company_snapshot_strips_descriptions_and_raw_payloads() -> None:
    snapshot = inspection_db.build_inspection_company_snapshot(_record())

    detail = snapshot["detail_payload"]
    assert "raw_company_record" not in detail
    assert "raw_company_enrichment_record" not in detail
    assert detail["jobs"][0]["has_description"] is True
    assert "description" not in detail["jobs"][0]
    assert "description_plain" not in detail["jobs"][0]
    assert "raw_candidate_record" not in detail["jobs"][0]
    assert "raw_job_description_extract" not in detail["jobs"][0]
    assert "Secret full job description text" not in snapshot["search_text"]


def test_build_inspection_company_snapshot_columns_and_search_text() -> None:
    snapshot = inspection_db.build_inspection_company_snapshot(_record())

    assert snapshot["company_key"] == "acme ai"
    assert snapshot["company"] == "Acme AI"
    assert snapshot["countries"] == ["Netherlands"]
    assert snapshot["sources"] == ["lever", "ashby", "ats"]
    assert snapshot["workplace_modes"] == ["remote"]
    assert snapshot["ai_team_contexts"] == ["existing_ai_team"]
    assert snapshot["delivery_contexts"] == ["internal"]
    assert snapshot["role_classification"] == "AI Execution Role"
    assert snapshot["company_type"] == "ai_native"
    assert snapshot["company_size"] == "101-500"
    assert snapshot["ai_tech_forward_signal"] == "strong"
    assert snapshot["job_count"] == 1
    assert snapshot["job_description_extract_count"] == 1
    assert snapshot["has_contacts"] is True
    assert snapshot["has_job_description_extracts"] is True
    assert snapshot["has_company_enrichment"] is True
    assert "Acme AI" in snapshot["search_text"]
    assert "Software" in snapshot["search_text"]
    assert "Senior AI Engineer" in snapshot["search_text"]
    assert "Secret plain description" not in snapshot["search_text"]
    assert "jobs" not in snapshot["summary_payload"]


def test_build_inspection_company_snapshot_requires_company_key() -> None:
    with pytest.raises(ValueError, match="company_key is required"):
        inspection_db.build_inspection_company_snapshot(_record(company_key=""))


def test_sync_inspection_database_replaces_existing_date_rows(monkeypatch, tmp_path) -> None:
    conn = FakeConnection()
    _write_sync_fixture(tmp_path)

    def fake_connect(database_url: str, **kwargs: object) -> FakeConnection:
        conn.connect_calls.append({"database_url": database_url, "kwargs": kwargs})
        return conn

    monkeypatch.setattr(inspection_db.psycopg, "connect", fake_connect)

    result = inspection_db.sync_inspection_database(
        "2026-07-02",
        database_url="postgres://test",
        data_dir=tmp_path,
    )

    assert result.collection_date == "2026-07-02"
    assert result.snapshot_count == 1
    assert result.job_count == 1
    assert result.database_url_configured is True
    assert conn.events == ["begin", "commit"]
    assert conn.connect_calls[0]["database_url"] == "postgres://test"
    assert any(
        "delete from public.inspection_collections" in call["query"]
        for call in conn.calls
        if call["kind"] == "execute"
    )
    assert not any(
        "company_review_state" in call["query"]
        for call in conn.calls
        if "query" in call
    )
    snapshot_call = next(call for call in conn.calls if call["kind"] == "executemany")
    assert len(snapshot_call["params_seq"]) == 1
    assert snapshot_call["params_seq"][0]["company_key"] == "acme ai"
    assert snapshot_call["params_seq"][0]["job_count"] == 1


def test_sync_inspection_database_rolls_back_on_snapshot_insert_failure(
    monkeypatch,
    tmp_path,
) -> None:
    conn = FakeConnection(fail_executemany=True)
    _write_sync_fixture(tmp_path)

    def fake_connect(database_url: str, **kwargs: object) -> FakeConnection:
        return conn

    monkeypatch.setattr(inspection_db.psycopg, "connect", fake_connect)

    with pytest.raises(RuntimeError, match="insert failed"):
        inspection_db.sync_inspection_database(
            "2026-07-02",
            database_url="postgres://test",
            data_dir=tmp_path,
        )

    assert conn.events == ["begin", "rollback"]


def test_load_company_inspection_data_from_database_returns_dataset(monkeypatch) -> None:
    synced_at = datetime(2026, 7, 2, 10, 30, tzinfo=timezone.utc)
    conn = FakeConnection(
        fetchall_rows=[
            [
                {
                    "detail_payload": _record(raw_company_record=None, raw_company_enrichment_record=None),
                    "synced_at": synced_at,
                }
            ]
        ]
    )

    def fake_connect(database_url: str, **kwargs: object) -> FakeConnection:
        conn.connect_calls.append({"database_url": database_url, "kwargs": kwargs})
        return conn

    monkeypatch.setattr(inspection_db.psycopg, "connect", fake_connect)

    dataset = inspection_db.load_company_inspection_data_from_database(
        "2026-07-02",
        database_url="postgres://test",
    )

    assert dataset is not None
    assert dataset.collection_date == "2026-07-02"
    assert dataset.data_source == "database"
    assert dataset.synced_at == "2026-07-02T10:30:00+00:00"
    assert dataset.counts.companies_loaded == 1
    assert dataset.counts.candidates_loaded == 1
    assert dataset.counts.job_description_extracts_loaded == 1
    assert dataset.counts.company_enrichments_loaded == 1
    assert dataset.missing_optional_files == []
    assert conn.connect_calls[0]["database_url"] == "postgres://test"
    assert conn.connect_calls[0]["kwargs"]["row_factory"] == inspection_db.dict_row


def test_load_company_inspection_data_from_database_returns_none_when_unsynced(
    monkeypatch,
) -> None:
    conn = FakeConnection(fetchall_rows=[[]])

    def fake_connect(database_url: str, **kwargs: object) -> FakeConnection:
        return conn

    monkeypatch.setattr(inspection_db.psycopg, "connect", fake_connect)

    assert (
        inspection_db.load_company_inspection_data_from_database(
            "2026-07-02",
            database_url="postgres://test",
        )
        is None
    )


def test_load_company_inspection_data_from_database_returns_empty_synced_dataset(
    monkeypatch,
) -> None:
    synced_at = datetime(2026, 7, 2, 10, 30, tzinfo=timezone.utc)
    conn = FakeConnection(fetchall_rows=[[]], fetchone_rows=[{"synced_at": synced_at}])

    def fake_connect(database_url: str, **kwargs: object) -> FakeConnection:
        return conn

    monkeypatch.setattr(inspection_db.psycopg, "connect", fake_connect)

    dataset = inspection_db.load_company_inspection_data_from_database(
        "2026-07-02",
        database_url="postgres://test",
    )

    assert dataset is not None
    assert dataset.records == []
    assert dataset.data_source == "database"
    assert dataset.synced_at == "2026-07-02T10:30:00+00:00"
    assert dataset.counts.companies_loaded == 0


def test_list_synced_collection_dates_returns_normalized_dates(monkeypatch) -> None:
    conn = FakeConnection(
        fetchall_rows=[
            [
                {"collection_date": date(2026, 7, 1)},
                {"collection_date": "2026-07-02"},
            ]
        ]
    )

    def fake_connect(database_url: str, **kwargs: object) -> FakeConnection:
        return conn

    monkeypatch.setattr(inspection_db.psycopg, "connect", fake_connect)

    assert inspection_db.list_synced_collection_dates(database_url="postgres://test") == [
        "2026-07-01",
        "2026-07-02",
    ]


def _write_sync_fixture(data_dir: Path) -> None:
    write_processed_jsonl(
        "companies_2026-07-02.jsonl",
        [
            {
                "record_type": "company_intelligence_title_only",
                "company": "Acme AI",
                "countries": ["Netherlands"],
                "sources": ["lever"],
            }
        ],
        data_dir=data_dir,
    )
    write_processed_jsonl(
        "job_candidates_2026-07-02.jsonl",
        [
            {
                "record_type": "job_candidate",
                "job_id": "job-1",
                "company_normalized": "Acme AI",
                "job_title_raw": "Senior AI Engineer",
                "job_title_normalized": "AI Engineer",
                "source": "lever",
                "platform": "lever",
                "description": "Full description must not sync.",
            }
        ],
        data_dir=data_dir,
    )


class FakeCursor:
    def __init__(self, conn: "FakeConnection") -> None:
        self.conn = conn

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, query: str, params: object | None = None) -> "FakeCursor":
        self.conn.calls.append(
            {"kind": "execute", "query": " ".join(query.split()), "params": params}
        )
        return self

    def executemany(self, query: str, params_seq: Any) -> "FakeCursor":
        if self.conn.fail_executemany:
            raise RuntimeError("insert failed")
        self.conn.calls.append(
            {
                "kind": "executemany",
                "query": " ".join(query.split()),
                "params_seq": list(params_seq),
            }
        )
        return self

    def fetchall(self) -> list[dict[str, object]]:
        if self.conn.fetchall_rows:
            return self.conn.fetchall_rows.pop(0)
        return []

    def fetchone(self) -> dict[str, object] | None:
        if self.conn.fetchone_rows:
            return self.conn.fetchone_rows.pop(0)
        return None


class FakeTransaction:
    def __init__(self, conn: "FakeConnection") -> None:
        self.conn = conn

    def __enter__(self) -> "FakeTransaction":
        self.conn.events.append("begin")
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        self.conn.events.append("rollback" if exc_type else "commit")
        return False


class FakeConnection:
    def __init__(
        self,
        *,
        fetchall_rows: list[list[dict[str, object]]] | None = None,
        fetchone_rows: list[dict[str, object]] | None = None,
        fail_executemany: bool = False,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self.connect_calls: list[dict[str, Any]] = []
        self.events: list[str] = []
        self.fetchall_rows = fetchall_rows or []
        self.fetchone_rows = fetchone_rows or []
        self.fail_executemany = fail_executemany

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def transaction(self) -> FakeTransaction:
        return FakeTransaction(self)
