from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from ai_hiring_radar import review_state


def test_outreach_status_options_match_workflow_contract() -> None:
    assert review_state.OUTREACH_STATUS_OPTIONS == (
        "not_started",
        "message_sent",
        "follow_up_sent",
        "active_conversation",
        "closed",
        "lost_client_rejection",
        "lost_no_response",
    )


def test_default_review_state_returns_expected_defaults() -> None:
    state = review_state.default_review_state(" acme ai ", "Acme AI")

    assert state == {
        "company_key": "acme ai",
        "company": "Acme AI",
        "fit_status": "unreviewed",
        "outreach_status": "not_started",
        "notes": "",
        "communication_history": "",
        "last_outreach_date": None,
        "inspected_at": None,
        "last_seen_collection_date": None,
        "created_at": None,
        "last_updated_at": None,
        "last_updated_by": None,
    }


def test_merge_review_state_overlays_persisted_state_by_company_key() -> None:
    records = [
        {"company_key": "acme ai", "company": "Acme AI", "job_count": 2},
        {"company_key": "beta ai", "company": "Beta AI", "job_count": 1},
    ]
    persisted = {
        "acme ai": {
            "fit_status": "best_fit",
            "outreach_status": "message_sent",
            "notes": "Strong signal.",
            "communication_history": "Message sent to CTO.",
            "last_outreach_date": "2026-07-06",
            "inspected_at": "2026-07-07T10:30:00+00:00",
            "last_seen_collection_date": "2026-07-07",
            "last_updated_at": "2026-07-07T10:35:00+00:00",
            "last_updated_by": "Jakob",
        }
    }

    merged = review_state.merge_review_state(records, persisted)

    assert merged[0]["fit_status"] == "best_fit"
    assert merged[0]["outreach_status"] == "message_sent"
    assert merged[0]["review_notes"] == "Strong signal."
    assert merged[0]["review_communication_history"] == "Message sent to CTO."
    assert merged[0]["last_outreach_date"] == "2026-07-06"
    assert merged[0]["inspected_at"] == "2026-07-07T10:30:00+00:00"
    assert merged[0]["last_reviewed_at"] == "2026-07-07T10:35:00+00:00"
    assert merged[0]["last_reviewed_by"] == "Jakob"
    assert merged[0]["has_review_state"] is True
    assert merged[1]["fit_status"] == "unreviewed"
    assert merged[1]["outreach_status"] == "not_started"
    assert merged[1]["review_notes"] == ""
    assert merged[1]["review_communication_history"] == ""
    assert merged[1]["last_outreach_date"] is None
    assert merged[1]["has_review_state"] is False


def test_merge_review_state_preserves_generated_fields_and_input_records() -> None:
    records = [{"company_key": "acme ai", "company": "Acme AI", "review_status": "new"}]

    merged = review_state.merge_review_state(records, {})

    assert merged[0]["review_status"] == "new"
    assert "fit_status" not in records[0]


def test_build_review_state_payload_sets_inspected_at_for_reviewed_status() -> None:
    now = datetime(2026, 7, 7, 10, 30, tzinfo=timezone.utc)

    payload = review_state.build_review_state_payload(
        company_key="acme ai",
        company="Acme AI",
        fit_status="possible_fit",
        outreach_status="follow_up_sent",
        notes=" Follow-up sent. ",
        communication_history=" Sent message on LinkedIn. ",
        last_outreach_date="2026-07-06",
        collection_date="2026-07-07",
        reviewer_name=" Jakob ",
        now=now,
    )

    assert payload == {
        "company_key": "acme ai",
        "company": "Acme AI",
        "fit_status": "possible_fit",
        "outreach_status": "follow_up_sent",
        "notes": "Follow-up sent.",
        "communication_history": "Sent message on LinkedIn.",
        "last_outreach_date": date(2026, 7, 6),
        "inspected_at": now,
        "last_seen_collection_date": "2026-07-07",
        "last_updated_by": "Jakob",
    }


def test_build_review_state_payload_leaves_inspected_at_empty_for_unreviewed() -> None:
    payload = review_state.build_review_state_payload(
        company_key="acme ai",
        company="Acme AI",
        fit_status="unreviewed",
        outreach_status="not_started",
        notes=None,
        communication_history=None,
        last_outreach_date=None,
        collection_date="2026-07-07",
        reviewer_name="",
    )

    assert payload["inspected_at"] is None
    assert payload["last_updated_by"] is None


def test_build_review_state_payload_rejects_invalid_status_values() -> None:
    with pytest.raises(ValueError, match="Invalid fit_status"):
        review_state.build_review_state_payload(
            company_key="acme ai",
            company="Acme AI",
            fit_status="good",
            outreach_status="not_started",
            notes="",
            communication_history="",
            last_outreach_date=None,
            collection_date="2026-07-07",
            reviewer_name=None,
        )

    with pytest.raises(ValueError, match="Invalid outreach_status"):
        review_state.build_review_state_payload(
            company_key="acme ai",
            company="Acme AI",
            fit_status="best_fit",
            outreach_status="emailed",
            notes="",
            communication_history="",
            last_outreach_date=None,
            collection_date="2026-07-07",
            reviewer_name=None,
        )


def test_build_review_state_payload_requires_company_key() -> None:
    with pytest.raises(ValueError, match="company_key is required"):
        review_state.build_review_state_payload(
            company_key="",
            company="Acme AI",
            fit_status="best_fit",
            outreach_status="message_sent",
            notes="",
            communication_history="",
            last_outreach_date=None,
            collection_date="2026-07-07",
            reviewer_name=None,
        )


def test_build_review_state_payload_rejects_future_last_outreach_date() -> None:
    with pytest.raises(ValueError, match="cannot be in the future"):
        review_state.build_review_state_payload(
            company_key="acme ai",
            company="Acme AI",
            fit_status="best_fit",
            outreach_status="message_sent",
            notes="",
            communication_history="",
            last_outreach_date=date.today() + timedelta(days=1),
            collection_date="2026-07-07",
            reviewer_name=None,
        )


@pytest.mark.parametrize(
    ("legacy_status", "canonical_status"),
    [
        ("follow_up_needed", "follow_up_sent"),
        ("replied", "active_conversation"),
    ],
)
def test_normalize_review_state_row_maps_legacy_outreach_statuses(
    legacy_status: str,
    canonical_status: str,
) -> None:
    state = review_state._normalize_review_state_row(
        {
            "company_key": "acme ai",
            "company": "Acme AI",
            "fit_status": "best_fit",
            "outreach_status": legacy_status,
        }
    )

    assert state["outreach_status"] == canonical_status


def test_load_review_state_returns_empty_without_company_keys(monkeypatch) -> None:
    def fail_connect(*args: object, **kwargs: object) -> None:
        raise AssertionError("database should not be queried")

    monkeypatch.setattr(review_state.psycopg, "connect", fail_connect)

    assert review_state.load_review_state(["", "   "], database_url="postgres://test") == {}


def test_load_review_state_fetches_unique_company_keys_in_one_batch(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    loaded_at = datetime(2026, 7, 7, 10, 30, tzinfo=timezone.utc)

    class FakeCursor:
        def __enter__(self) -> FakeCursor:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def execute(self, query: str, params: tuple[list[str]]) -> FakeCursor:
            calls.append({"query": query, "params": params})
            return self

        def fetchall(self) -> list[dict[str, object]]:
            return [
                {
                    "company_key": "acme ai",
                    "company": "Acme AI",
                    "fit_status": "best_fit",
                    "outreach_status": "message_sent",
                    "notes": "Strong signal.",
                    "communication_history": "Message sent to CTO.",
                    "last_outreach_date": loaded_at.date(),
                    "inspected_at": loaded_at,
                    "last_seen_collection_date": loaded_at.date(),
                    "last_updated_at": loaded_at,
                    "last_updated_by": "Jakob",
                }
            ]

    class FakeConnection:
        def __enter__(self) -> FakeConnection:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def cursor(self) -> FakeCursor:
            return FakeCursor()

    def fake_connect(database_url: str, **kwargs: object) -> FakeConnection:
        calls.append({"database_url": database_url, "kwargs": kwargs})
        return FakeConnection()

    monkeypatch.setattr(review_state.psycopg, "connect", fake_connect)

    loaded = review_state.load_review_state(
        ["acme ai", "acme ai", " beta ai "],
        database_url="postgres://test",
    )

    assert calls[0]["database_url"] == "postgres://test"
    assert calls[1]["params"] == (["acme ai", "beta ai"],)
    assert loaded["acme ai"]["inspected_at"] == "2026-07-07T10:30:00+00:00"
    assert loaded["acme ai"]["last_seen_collection_date"] == "2026-07-07"
    assert loaded["acme ai"]["communication_history"] == "Message sent to CTO."
    assert loaded["acme ai"]["last_outreach_date"] == "2026-07-07"


def _capture_single_row_query(
    monkeypatch: pytest.MonkeyPatch,
    returned_row: dict[str, object],
) -> dict[str, object]:
    captured: dict[str, object] = {}

    class FakeCursor:
        def __enter__(self) -> FakeCursor:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def execute(self, query: str, params: dict[str, object]) -> FakeCursor:
            captured["query"] = query
            captured["params"] = params
            return self

        def fetchone(self) -> dict[str, object]:
            return returned_row

    class FakeConnection:
        def __enter__(self) -> FakeConnection:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def cursor(self) -> FakeCursor:
            return FakeCursor()

    monkeypatch.setattr(
        review_state.psycopg,
        "connect",
        lambda *args, **kwargs: FakeConnection(),
    )
    return captured


def _persisted_review_row() -> dict[str, object]:
    return {
        "company_key": "acme ai",
        "company": "Acme AI",
        "fit_status": "best_fit",
        "outreach_status": "message_sent",
        "notes": "Strong signal.",
        "communication_history": "Message sent to CTO.",
        "last_outreach_date": "2026-07-06",
        "inspected_at": None,
        "last_seen_collection_date": "2026-07-07",
        "created_at": None,
        "last_updated_at": None,
        "last_updated_by": "Jakob",
    }


def test_upsert_review_state_writes_both_note_fields(monkeypatch) -> None:
    captured = _capture_single_row_query(monkeypatch, _persisted_review_row())

    review_state.upsert_review_state(
        _persisted_review_row(),
        database_url="postgres://test",
    )

    query = str(captured["query"])
    params = captured["params"]
    assert isinstance(params, dict)
    assert "notes = excluded.notes" in query
    assert "communication_history = excluded.communication_history" in query
    assert "last_outreach_date = excluded.last_outreach_date" in query
    assert params["notes"] == "Strong signal."
    assert params["communication_history"] == "Message sent to CTO."
    assert params["last_outreach_date"] == date(2026, 7, 6)


def test_upsert_review_statuses_does_not_write_note_fields(monkeypatch) -> None:
    captured = _capture_single_row_query(monkeypatch, _persisted_review_row())

    review_state.upsert_review_statuses(
        _persisted_review_row(),
        database_url="postgres://test",
    )

    write_query = str(captured["query"]).split("returning", 1)[0]
    params = captured["params"]
    assert isinstance(params, dict)
    assert "notes" not in write_query
    assert "communication_history" not in write_query
    assert "last_outreach_date" not in write_query
    assert "notes" not in params
    assert "communication_history" not in params
    assert "last_outreach_date" not in params


def test_upsert_last_outreach_date_writes_only_date_field(monkeypatch) -> None:
    captured = _capture_single_row_query(monkeypatch, _persisted_review_row())

    review_state.upsert_last_outreach_date(
        _persisted_review_row(),
        database_url="postgres://test",
    )

    write_query = str(captured["query"]).split("returning", 1)[0]
    params = captured["params"]
    assert isinstance(params, dict)
    assert "last_outreach_date = excluded.last_outreach_date" in write_query
    assert "fit_status" not in write_query
    assert "outreach_status" not in write_query
    assert "notes" not in write_query
    assert "communication_history" not in write_query
    assert params["last_outreach_date"] == date(2026, 7, 6)
    assert "fit_status" not in params
    assert "outreach_status" not in params
    assert "notes" not in params
    assert "communication_history" not in params


def test_upsert_review_notes_writes_only_note_fields(monkeypatch) -> None:
    captured = _capture_single_row_query(monkeypatch, _persisted_review_row())

    review_state.upsert_review_notes(
        _persisted_review_row(),
        database_url="postgres://test",
    )

    write_query = str(captured["query"]).split("returning", 1)[0]
    params = captured["params"]
    assert isinstance(params, dict)
    assert "notes = excluded.notes" in write_query
    assert "communication_history = excluded.communication_history" in write_query
    assert "fit_status" not in write_query
    assert "outreach_status" not in write_query
    assert "last_outreach_date" not in write_query
    assert params["notes"] == "Strong signal."
    assert params["communication_history"] == "Message sent to CTO."
    assert "fit_status" not in params
    assert "outreach_status" not in params
    assert "last_outreach_date" not in params


def test_communication_history_schema_migration_is_idempotent() -> None:
    repository_root = Path(__file__).parents[1]
    setup_sql = (
        repository_root
        / "architecture-design-documents/04-company-review-state/setup.sql"
    ).read_text()
    migration_sql = (
        repository_root
        / "architecture-design-documents/04-company-review-state/migrate_add_communication_history.sql"
    ).read_text()

    assert "communication_history text not null default ''" in setup_sql
    assert (
        "add column if not exists communication_history text not null default ''"
        in migration_sql
    )


def test_last_outreach_date_schema_migration_is_idempotent() -> None:
    repository_root = Path(__file__).parents[1]
    setup_sql = (
        repository_root
        / "architecture-design-documents/04-company-review-state/setup.sql"
    ).read_text()
    migration_sql = (
        repository_root
        / "architecture-design-documents/04-company-review-state/migrate_add_last_outreach_date.sql"
    ).read_text()

    assert "last_outreach_date date" in setup_sql
    assert "add column if not exists last_outreach_date date" in migration_sql
