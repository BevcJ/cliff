from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ai_hiring_radar import review_state


def test_default_review_state_returns_expected_defaults() -> None:
    state = review_state.default_review_state(" acme ai ", "Acme AI")

    assert state == {
        "company_key": "acme ai",
        "company": "Acme AI",
        "fit_status": "unreviewed",
        "outreach_status": "not_started",
        "notes": "",
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
    assert merged[0]["inspected_at"] == "2026-07-07T10:30:00+00:00"
    assert merged[0]["last_reviewed_at"] == "2026-07-07T10:35:00+00:00"
    assert merged[0]["last_reviewed_by"] == "Jakob"
    assert merged[0]["has_review_state"] is True
    assert merged[1]["fit_status"] == "unreviewed"
    assert merged[1]["outreach_status"] == "not_started"
    assert merged[1]["review_notes"] == ""
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
        outreach_status="follow_up_needed",
        notes=" Needs follow-up. ",
        collection_date="2026-07-07",
        reviewer_name=" Jakob ",
        now=now,
    )

    assert payload == {
        "company_key": "acme ai",
        "company": "Acme AI",
        "fit_status": "possible_fit",
        "outreach_status": "follow_up_needed",
        "notes": "Needs follow-up.",
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
            collection_date="2026-07-07",
            reviewer_name=None,
        )


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
