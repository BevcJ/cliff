from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row


FIT_STATUS_OPTIONS = ("unreviewed", "best_fit", "possible_fit", "not_interesting")
OUTREACH_STATUS_OPTIONS = (
    "not_started",
    "message_sent",
    "follow_up_needed",
    "replied",
    "closed",
)
REVIEWED_FIT_STATUSES = tuple(
    status for status in FIT_STATUS_OPTIONS if status != "unreviewed"
)

REVIEW_STATE_COLUMNS = (
    "company_key",
    "company",
    "fit_status",
    "outreach_status",
    "notes",
    "communication_history",
    "inspected_at",
    "last_seen_collection_date",
    "created_at",
    "last_updated_at",
    "last_updated_by",
)


def default_review_state(company_key: str, company: str) -> dict[str, Any]:
    return {
        "company_key": _clean_one_line(company_key),
        "company": _clean_one_line(company),
        "fit_status": "unreviewed",
        "outreach_status": "not_started",
        "notes": "",
        "communication_history": "",
        "inspected_at": None,
        "last_seen_collection_date": None,
        "created_at": None,
        "last_updated_at": None,
        "last_updated_by": None,
    }


def merge_review_state(
    records: list[dict[str, Any]],
    review_state_by_company_key: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    merged_records: list[dict[str, Any]] = []
    for record in records:
        company_key = _clean_one_line(record.get("company_key"))
        default_state = default_review_state(company_key, _clean_one_line(record.get("company")))
        persisted_state = review_state_by_company_key.get(company_key)
        state = {**default_state, **(persisted_state or {})}

        merged = dict(record)
        merged["fit_status"] = state["fit_status"]
        merged["outreach_status"] = state["outreach_status"]
        merged["review_notes"] = state["notes"]
        merged["review_communication_history"] = state["communication_history"]
        merged["inspected_at"] = state.get("inspected_at")
        merged["last_seen_collection_date"] = state.get("last_seen_collection_date")
        merged["last_reviewed_at"] = state.get("last_updated_at")
        merged["last_reviewed_by"] = state.get("last_updated_by")
        merged["has_review_state"] = persisted_state is not None
        merged_records.append(merged)
    return merged_records


def load_review_state(
    company_keys: list[str],
    *,
    database_url: str,
) -> dict[str, dict[str, Any]]:
    keys = _unique_company_keys(company_keys)
    if not keys:
        return {}

    query = f"""
        select {", ".join(REVIEW_STATE_COLUMNS)}
        from company_review_state
        where company_key = any(%s::text[])
    """
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cursor:
            rows = cursor.execute(query, (keys,)).fetchall()
    return {
        _clean_one_line(row.get("company_key")): _normalize_review_state_row(row)
        for row in rows
        if _clean_one_line(row.get("company_key"))
    }


def build_review_state_payload(
    *,
    company_key: str,
    company: str,
    fit_status: str,
    outreach_status: str,
    notes: str | None,
    communication_history: str | None,
    collection_date: str | None,
    reviewer_name: str | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    payload = _build_review_status_payload(
        company_key=company_key,
        company=company,
        fit_status=fit_status,
        outreach_status=outreach_status,
        collection_date=collection_date,
        reviewer_name=reviewer_name,
        now=now,
    )
    payload["notes"] = _clean_notes(notes)
    payload["communication_history"] = _clean_notes(communication_history)
    return payload


def _build_review_status_payload(
    *,
    company_key: str,
    company: str,
    fit_status: str,
    outreach_status: str,
    collection_date: str | None,
    reviewer_name: str | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    cleaned_company_key = _clean_one_line(company_key)
    if not cleaned_company_key:
        raise ValueError("company_key is required to save review state")

    validate_statuses(fit_status=fit_status, outreach_status=outreach_status)
    reviewed_at = now or datetime.now(timezone.utc)
    return {
        "company_key": cleaned_company_key,
        "company": _clean_one_line(company),
        "fit_status": fit_status,
        "outreach_status": outreach_status,
        "inspected_at": reviewed_at if fit_status in REVIEWED_FIT_STATUSES else None,
        "last_seen_collection_date": _clean_one_line(collection_date) or None,
        "last_updated_by": _clean_one_line(reviewer_name) or None,
    }


def upsert_review_state(
    review_state: dict[str, Any],
    *,
    database_url: str,
) -> dict[str, Any]:
    payload = build_review_state_payload(
        company_key=str(review_state.get("company_key") or ""),
        company=str(review_state.get("company") or ""),
        fit_status=str(review_state.get("fit_status") or ""),
        outreach_status=str(review_state.get("outreach_status") or ""),
        notes=str(review_state.get("notes") or ""),
        communication_history=str(review_state.get("communication_history") or ""),
        collection_date=review_state.get("last_seen_collection_date"),
        reviewer_name=review_state.get("last_updated_by"),
        now=review_state.get("inspected_at"),
    )

    query = f"""
        insert into company_review_state (
          company_key,
          company,
          fit_status,
          outreach_status,
          notes,
          communication_history,
          inspected_at,
          last_seen_collection_date,
          last_updated_at,
          last_updated_by
        ) values (
          %(company_key)s,
          %(company)s,
          %(fit_status)s,
          %(outreach_status)s,
          %(notes)s,
          %(communication_history)s,
          %(inspected_at)s,
          %(last_seen_collection_date)s,
          now(),
          %(last_updated_by)s
        )
        on conflict (company_key) do update set
          company = excluded.company,
          fit_status = excluded.fit_status,
          outreach_status = excluded.outreach_status,
          notes = excluded.notes,
          communication_history = excluded.communication_history,
          inspected_at = coalesce(company_review_state.inspected_at, excluded.inspected_at),
          last_seen_collection_date = excluded.last_seen_collection_date,
          last_updated_at = now(),
          last_updated_by = excluded.last_updated_by
        returning {", ".join(REVIEW_STATE_COLUMNS)}
    """
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cursor:
            row = cursor.execute(query, payload).fetchone()
    if row is None:
        raise RuntimeError("Review state upsert did not return a row")
    return _normalize_review_state_row(row)


def upsert_review_statuses(
    review_state: dict[str, Any],
    *,
    database_url: str,
) -> dict[str, Any]:
    payload = _build_review_status_payload(
        company_key=str(review_state.get("company_key") or ""),
        company=str(review_state.get("company") or ""),
        fit_status=str(review_state.get("fit_status") or ""),
        outreach_status=str(review_state.get("outreach_status") or ""),
        collection_date=review_state.get("last_seen_collection_date"),
        reviewer_name=review_state.get("last_updated_by"),
        now=review_state.get("inspected_at"),
    )

    query = f"""
        insert into company_review_state (
          company_key,
          company,
          fit_status,
          outreach_status,
          inspected_at,
          last_seen_collection_date,
          last_updated_at,
          last_updated_by
        ) values (
          %(company_key)s,
          %(company)s,
          %(fit_status)s,
          %(outreach_status)s,
          %(inspected_at)s,
          %(last_seen_collection_date)s,
          now(),
          %(last_updated_by)s
        )
        on conflict (company_key) do update set
          company = excluded.company,
          fit_status = excluded.fit_status,
          outreach_status = excluded.outreach_status,
          inspected_at = coalesce(company_review_state.inspected_at, excluded.inspected_at),
          last_seen_collection_date = excluded.last_seen_collection_date,
          last_updated_at = now(),
          last_updated_by = excluded.last_updated_by
        returning {", ".join(REVIEW_STATE_COLUMNS)}
    """
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cursor:
            row = cursor.execute(query, payload).fetchone()
    if row is None:
        raise RuntimeError("Review status upsert did not return a row")
    return _normalize_review_state_row(row)


def validate_statuses(*, fit_status: str, outreach_status: str) -> None:
    if fit_status not in FIT_STATUS_OPTIONS:
        raise ValueError(
            f"Invalid fit_status {fit_status!r}; expected one of {FIT_STATUS_OPTIONS}"
        )
    if outreach_status not in OUTREACH_STATUS_OPTIONS:
        raise ValueError(
            "Invalid outreach_status "
            f"{outreach_status!r}; expected one of {OUTREACH_STATUS_OPTIONS}"
        )


def _normalize_review_state_row(row: dict[str, Any]) -> dict[str, Any]:
    state = default_review_state(
        _clean_one_line(row.get("company_key")),
        _clean_one_line(row.get("company")),
    )
    for field in REVIEW_STATE_COLUMNS:
        if field not in row:
            continue
        state[field] = _serialize_value(row[field])
    validate_statuses(
        fit_status=str(state["fit_status"]),
        outreach_status=str(state["outreach_status"]),
    )
    state["notes"] = _clean_notes(state.get("notes"))
    state["communication_history"] = _clean_notes(state.get("communication_history"))
    return state


def _unique_company_keys(company_keys: list[str]) -> list[str]:
    keys: list[str] = []
    for company_key in company_keys:
        cleaned = _clean_one_line(company_key)
        if cleaned and cleaned not in keys:
            keys.append(cleaned)
    return keys


def _clean_one_line(value: object | None) -> str:
    return " ".join(str(value or "").split()).strip()


def _clean_notes(value: object | None) -> str:
    return str(value or "").strip()


def _serialize_value(value: Any) -> Any:
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if hasattr(value, "isoformat") and not isinstance(value, str):
        return value.isoformat()
    return value
