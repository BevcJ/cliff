from __future__ import annotations

import csv
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from ai_hiring_radar.storage_json import DEFAULT_DATA_DIR, read_json, write_json


FULLENRICH_BASE_URL = "https://app.fullenrich.com/api/v2"
PROSPEO_BASE_URL = "https://api.prospeo.io"
ACCEPTED_FULLENRICH_STATUSES = {"DELIVERABLE"}
ACCEPTED_PROSPEO_STATUSES = {"VERIFIED"}
PROSPEO_RATE_LIMIT_ATTEMPTS = 4


@dataclass(frozen=True)
class EvaluationContact:
    identifier: str
    company_key: str
    company: str
    contact_name: str | None
    first_name: str | None
    last_name: str | None
    contact_role: str | None
    contact_title: str | None
    existing_email: str | None
    linkedin_url: str | None
    collection_date: str | None
    countries: str | None
    fit_status: str | None
    outreach_status: str | None
    workflow: str | None

    @property
    def can_enrich(self) -> bool:
        return bool(
            self.contact_name
            and self.first_name
            and self.last_name
            and not self.existing_email
        )


@dataclass(frozen=True)
class ProviderResult:
    identifier: str
    provider: str
    status: str
    email: str | None = None
    verification_status: str | None = None
    matched_name: str | None = None
    matched_company: str | None = None
    employer_match: bool | None = None
    credits: float | None = None
    message: str | None = None

    @property
    def accepted(self) -> bool:
        accepted_statuses = (
            ACCEPTED_FULLENRICH_STATUSES
            if self.provider == "fullenrich"
            else ACCEPTED_PROSPEO_STATUSES
        )
        return bool(
            self.email
            and self.verification_status in accepted_statuses
            and self.employer_match is not False
        )


@dataclass(frozen=True)
class ContactEmailEvaluationResult:
    run_dir: Path
    manifest_count: int
    eligible_count: int
    existing_email_count: int
    missing_contact_count: int
    fullenrich_found_count: int
    prospeo_found_count: int
    recommended_count: int


def run_contact_email_evaluation(
    input_path: Path,
    *,
    fullenrich_api_key: str,
    prospeo_api_key: str,
    limit: int | None = None,
    output_dir: Path | None = None,
    data_dir: Path = DEFAULT_DATA_DIR,
    fullenrich_poll_seconds: float = 30.0,
    fullenrich_timeout_seconds: float = 900.0,
    http_client: httpx.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> ContactEmailEvaluationResult:
    run_dir = output_dir or _default_run_dir(data_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        contacts = _load_saved_manifest(manifest_path)
    else:
        contacts = load_evaluation_contacts(input_path)
        if limit is not None:
            if limit < 1:
                raise ValueError("limit must be at least 1")
            contacts = [contact for contact in contacts if contact.can_enrich][:limit]
        write_json(manifest_path, [asdict(contact) for contact in contacts])

    eligible = [contact for contact in contacts if contact.can_enrich]
    client = http_client or httpx.Client(timeout=60.0)
    owns_client = http_client is None
    try:
        try:
            prospeo_results = _load_or_run_prospeo(
                run_dir,
                contacts=eligible,
                api_key=prospeo_api_key,
                http_client=client,
                sleep=sleep,
            )
            fullenrich_results = _load_or_run_fullenrich(
                run_dir,
                contacts=eligible,
                api_key=fullenrich_api_key,
                poll_seconds=fullenrich_poll_seconds,
                timeout_seconds=fullenrich_timeout_seconds,
                http_client=client,
                sleep=sleep,
            )
        except Exception as exc:
            raise RuntimeError(
                f"{exc} Run state is preserved in {run_dir}. Re-run with "
                f"--output-dir {run_dir} to resume without repeating completed requests."
            ) from exc
    finally:
        if owns_client:
            client.close()

    comparison_rows = build_comparison_rows(
        contacts,
        fullenrich_results=fullenrich_results,
        prospeo_results=prospeo_results,
    )
    _write_comparison_csv(run_dir / "comparison.csv", comparison_rows)
    summary = _build_summary(
        contacts,
        comparison_rows=comparison_rows,
        fullenrich_results=fullenrich_results,
        prospeo_results=prospeo_results,
    )
    write_json(run_dir / "summary.json", summary)

    return ContactEmailEvaluationResult(
        run_dir=run_dir,
        manifest_count=len(contacts),
        eligible_count=len(eligible),
        existing_email_count=summary["existing_email_count"],
        missing_contact_count=summary["missing_contact_count"],
        fullenrich_found_count=summary["providers"]["fullenrich"]["accepted_count"],
        prospeo_found_count=summary["providers"]["prospeo"]["accepted_count"],
        recommended_count=summary["recommended_count"],
    )


def load_evaluation_contacts(path: Path) -> list[EvaluationContact]:
    if not path.exists():
        raise FileNotFoundError(f"Contact evaluation CSV not found: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        required = {"company_key", "company", "contact_name"}
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(
                "Contact evaluation CSV is missing required column(s): "
                + ", ".join(sorted(missing))
            )

        contacts: list[EvaluationContact] = []
        seen_identifiers: set[str] = set()
        for index, row in enumerate(reader, start=1):
            company_key = _clean(row.get("company_key"))
            company = _clean(row.get("company"))
            if not company_key or not company:
                raise ValueError(f"CSV row {index + 1} requires company_key and company.")

            identifier = _unique_identifier(company_key, seen_identifiers)
            contact_name = _clean(row.get("contact_name"))
            first_name, last_name = _contact_name_parts(row, contact_name)
            contacts.append(
                EvaluationContact(
                    identifier=identifier,
                    company_key=company_key,
                    company=company,
                    contact_name=contact_name,
                    first_name=first_name,
                    last_name=last_name,
                    contact_role=_clean(row.get("contact_role")),
                    contact_title=_clean(row.get("contact_title")),
                    existing_email=_clean(row.get("existing_email")),
                    linkedin_url=_clean(row.get("contact_linkedin_url")),
                    collection_date=_clean(row.get("collection_date")),
                    countries=_clean(row.get("countries")),
                    fit_status=_clean(row.get("fit_status")),
                    outreach_status=_clean(row.get("outreach_status")),
                    workflow=_clean(row.get("workflow")),
                )
            )
    return contacts


def _load_saved_manifest(path: Path) -> list[EvaluationContact]:
    payload = read_json(path)
    if not isinstance(payload, list):
        raise ValueError(f"Invalid saved evaluation manifest: {path}")
    try:
        return [EvaluationContact(**item) for item in payload if isinstance(item, dict)]
    except TypeError as exc:
        raise ValueError(f"Invalid saved evaluation manifest: {path}") from exc


def _contact_name_parts(
    row: dict[str, str | None],
    contact_name: str | None,
) -> tuple[str | None, str | None]:
    first_name = _clean(row.get("first_name"))
    last_name = _clean(row.get("last_name"))
    if first_name and last_name:
        return first_name, last_name
    if not contact_name:
        return None, None
    parts = contact_name.split()
    if len(parts) < 2:
        return None, None
    return parts[0], " ".join(parts[1:])


def _unique_identifier(company_key: str, seen: set[str]) -> str:
    base = company_key
    identifier = base
    suffix = 2
    while identifier in seen:
        identifier = f"{base}-{suffix}"
        suffix += 1
    seen.add(identifier)
    return identifier


def _load_or_run_prospeo(
    run_dir: Path,
    *,
    contacts: list[EvaluationContact],
    api_key: str,
    http_client: httpx.Client,
    sleep: Callable[[float], None],
) -> list[ProviderResult]:
    raw_path = run_dir / "prospeo-raw.json"
    if raw_path.exists():
        raw = read_json(raw_path)
        completed = raw.get("completed_identifiers") if isinstance(raw, dict) else None
        pending = (
            [contact for contact in contacts if contact.identifier not in completed]
            if isinstance(completed, list)
            else []
        )
    else:
        raw = {
            "error": False,
            "total_cost": 0,
            "matched": [],
            "not_matched": [],
            "invalid_datapoints": [],
            "completed_identifiers": [],
        }
        pending = contacts
    if pending:
        raw = _run_prospeo(
            pending,
            api_key=api_key,
            http_client=http_client,
            sleep=sleep,
            combined=raw,
            save=lambda payload: write_json(raw_path, payload),
        )
    write_json(raw_path, raw)
    results = _normalize_prospeo_results(contacts, raw)
    write_json(run_dir / "prospeo-results.json", [asdict(result) for result in results])
    return results


def _run_prospeo(
    contacts: list[EvaluationContact],
    *,
    api_key: str,
    http_client: httpx.Client,
    sleep: Callable[[float], None],
    combined: dict[str, Any],
    save: Callable[[dict[str, Any]], object],
) -> dict[str, Any]:
    for index, chunk in enumerate(_chunks(contacts, 1)):
        response = _post_prospeo_chunk(
            chunk,
            api_key=api_key,
            http_client=http_client,
            sleep=sleep,
        )
        payload = _json_object(response)
        if response.status_code == 400 and payload.get("error_code") == "NO_MATCH":
            combined["not_matched"].extend(contact.identifier for contact in chunk)
        elif response.is_error:
            detail = response.text.strip() or response.reason_phrase
            raise RuntimeError(
                f"Prospeo returned HTTP {response.status_code}: {detail[:500]}"
            )
        elif payload.get("error"):
            raise RuntimeError(
                f"Prospeo enrichment failed: {payload.get('error_code', 'unknown error')}"
            )
        else:
            combined["total_cost"] += _number(payload.get("total_cost")) or 0
            for field in ("matched", "not_matched", "invalid_datapoints"):
                values = payload.get(field)
                if isinstance(values, list):
                    combined[field].extend(values)
        combined["completed_identifiers"].extend(
            contact.identifier for contact in chunk
        )
        save(combined)
        if index < len(contacts) - 1:
            sleep(_prospeo_next_request_delay(response))
    return combined


def _post_prospeo_chunk(
    contacts: list[EvaluationContact],
    *,
    api_key: str,
    http_client: httpx.Client,
    sleep: Callable[[float], None],
) -> httpx.Response:
    for attempt in range(PROSPEO_RATE_LIMIT_ATTEMPTS):
        response = http_client.post(
            f"{PROSPEO_BASE_URL}/bulk-enrich-person",
            headers={"X-KEY": api_key, "Content-Type": "application/json"},
            json={
                "only_verified_email": True,
                "data": [_prospeo_input(contact) for contact in contacts],
            },
        )
        if response.status_code != 429 or attempt == PROSPEO_RATE_LIMIT_ATTEMPTS - 1:
            return response
        if response.headers.get("x-daily-request-left") == "0":
            return response
        sleep(_prospeo_rate_limit_delay(response))
    raise AssertionError("Prospeo retry loop did not return a response.")


def _prospeo_rate_limit_delay(response: httpx.Response) -> float:
    raw_delay = response.headers.get("retry-after")
    if raw_delay is None and response.headers.get("x-minute-request-left") == "0":
        raw_delay = response.headers.get("x-minute-reset-seconds")
    try:
        return max(float(raw_delay or 1), 1.0)
    except ValueError:
        return 1.0


def _prospeo_next_request_delay(response: httpx.Response) -> float:
    if response.headers.get("x-minute-request-left") == "0":
        raw_delay = response.headers.get("x-minute-reset-seconds")
        try:
            return max(float(raw_delay or 60), 1.0)
        except ValueError:
            return 60.0
    raw_limit = response.headers.get("x-second-rate-limit")
    try:
        return max(1 / float(raw_limit or 1), 0.05)
    except (ValueError, ZeroDivisionError):
        return 1.0


def _prospeo_input(contact: EvaluationContact) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "identifier": contact.identifier,
        "full_name": contact.contact_name,
        "company_name": contact.company,
    }
    if contact.linkedin_url:
        payload["linkedin_url"] = contact.linkedin_url
    return payload


def _normalize_prospeo_results(
    contacts: list[EvaluationContact],
    payload: object,
) -> list[ProviderResult]:
    raw = payload if isinstance(payload, dict) else {}
    contacts_by_id = {contact.identifier: contact for contact in contacts}
    results: dict[str, ProviderResult] = {}
    total_cost = _number(raw.get("total_cost"))
    matched = _list_value(raw.get("matched"))
    per_match_cost = total_cost / len(matched) if total_cost is not None and matched else None

    for item in matched:
        if not isinstance(item, dict):
            continue
        identifier = _clean(item.get("identifier"))
        contact = contacts_by_id.get(identifier or "")
        if contact is None or identifier is None:
            continue
        person = _dict_value(item.get("person"))
        company = _dict_value(item.get("company"))
        email_data = _dict_value(person.get("email"))
        email = _clean(email_data.get("email"))
        verification_status = _clean(email_data.get("status"))
        matched_company = _clean(company.get("name"))
        results[identifier] = ProviderResult(
            identifier=identifier,
            provider="prospeo",
            status="found" if email else "not_found",
            email=email,
            verification_status=verification_status,
            matched_name=_clean(person.get("full_name")),
            matched_company=matched_company,
            employer_match=_employer_matches(contact.company, matched_company),
            credits=per_match_cost,
        )

    for identifier in _list_value(raw.get("invalid_datapoints")):
        cleaned = _clean(identifier)
        if cleaned in contacts_by_id:
            results[cleaned] = ProviderResult(
                identifier=cleaned,
                provider="prospeo",
                status="invalid_input",
                message="Prospeo rejected the identifying data.",
            )
    for identifier in _list_value(raw.get("not_matched")):
        cleaned = _clean(identifier)
        if cleaned in contacts_by_id:
            results[cleaned] = ProviderResult(
                identifier=cleaned,
                provider="prospeo",
                status="not_found",
            )

    return [
        results.get(
            contact.identifier,
            ProviderResult(
                identifier=contact.identifier,
                provider="prospeo",
                status="not_found",
            ),
        )
        for contact in contacts
    ]


def _load_or_run_fullenrich(
    run_dir: Path,
    *,
    contacts: list[EvaluationContact],
    api_key: str,
    poll_seconds: float,
    timeout_seconds: float,
    http_client: httpx.Client,
    sleep: Callable[[float], None],
) -> list[ProviderResult]:
    raw_path = run_dir / "fullenrich-raw.json"
    state_path = run_dir / "fullenrich-state.json"
    if raw_path.exists():
        raw = read_json(raw_path)
    elif not contacts:
        raw = {"status": "FINISHED", "cost": {"credits": 0}, "data": []}
        write_json(raw_path, raw)
    else:
        if state_path.exists():
            state = read_json(state_path)
            enrichment_id = _clean(state.get("enrichment_id") if isinstance(state, dict) else None)
            if not enrichment_id:
                raise ValueError(f"Invalid FullEnrich state file: {state_path}")
        else:
            enrichment_id = _start_fullenrich(
                contacts,
                api_key=api_key,
                http_client=http_client,
            )
            write_json(state_path, {"enrichment_id": enrichment_id})
        raw = _wait_for_fullenrich(
            enrichment_id,
            api_key=api_key,
            poll_seconds=poll_seconds,
            timeout_seconds=timeout_seconds,
            http_client=http_client,
            sleep=sleep,
        )
        write_json(raw_path, raw)
    results = _normalize_fullenrich_results(contacts, raw)
    write_json(run_dir / "fullenrich-results.json", [asdict(result) for result in results])
    return results


def _start_fullenrich(
    contacts: list[EvaluationContact],
    *,
    api_key: str,
    http_client: httpx.Client,
) -> str:
    response = http_client.post(
        f"{FULLENRICH_BASE_URL}/contact/enrich/bulk",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "name": f"Pareto contact email evaluation {datetime.now(timezone.utc).isoformat()}",
            "data": [_fullenrich_input(contact) for contact in contacts],
        },
    )
    response.raise_for_status()
    payload = _json_object(response)
    enrichment_id = _clean(payload.get("enrichment_id"))
    if not enrichment_id:
        raise ValueError("FullEnrich did not return an enrichment_id.")
    return enrichment_id


def _fullenrich_input(contact: EvaluationContact) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "first_name": contact.first_name,
        "last_name": contact.last_name,
        "company_name": contact.company,
        "enrich_fields": ["contact.work_emails"],
        "custom": {"evaluation_id": contact.identifier},
    }
    if contact.linkedin_url:
        payload["linkedin_url"] = contact.linkedin_url
    return payload


def _wait_for_fullenrich(
    enrichment_id: str,
    *,
    api_key: str,
    poll_seconds: float,
    timeout_seconds: float,
    http_client: httpx.Client,
    sleep: Callable[[float], None],
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while True:
        response = http_client.get(
            f"{FULLENRICH_BASE_URL}/contact/enrich/bulk/{enrichment_id}",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        payload = _json_object(response)
        if response.status_code == 200:
            status = _clean(payload.get("status"))
            if status == "FINISHED":
                return payload
            if status in {"CANCELED", "CREDITS_INSUFFICIENT", "RATE_LIMIT"}:
                raise RuntimeError(f"FullEnrich enrichment ended with status {status}.")
        elif not (
            response.status_code == 400
            and payload.get("code") == "error.enrichment.in_progress"
        ):
            response.raise_for_status()

        if time.monotonic() >= deadline:
            raise TimeoutError(
                "FullEnrich is still processing. Re-run the same command with "
                "--output-dir set to this run directory to resume without spending credits again."
            )
        sleep(poll_seconds)


def _normalize_fullenrich_results(
    contacts: list[EvaluationContact],
    payload: object,
) -> list[ProviderResult]:
    raw = payload if isinstance(payload, dict) else {}
    contacts_by_id = {contact.identifier: contact for contact in contacts}
    results: dict[str, ProviderResult] = {}
    data = _list_value(raw.get("data"))
    total_credits = _number(
        raw.get("cost", {}).get("credits") if isinstance(raw.get("cost"), dict) else None
    )
    per_record_cost = total_credits / len(data) if total_credits is not None and data else None

    for item in data:
        if not isinstance(item, dict):
            continue
        custom = _dict_value(item.get("custom"))
        identifier = _clean(custom.get("evaluation_id"))
        contact = contacts_by_id.get(identifier or "")
        if contact is None or identifier is None:
            continue
        contact_info = _dict_value(item.get("contact_info"))
        email_data = _dict_value(contact_info.get("most_probable_work_email"))
        profile = _dict_value(item.get("profile"))
        current_employment = _nested_dict(profile, "employment", "current")
        company = _dict_value(current_employment.get("company"))
        matched_company = _clean(company.get("name"))
        email = _clean(email_data.get("email"))
        results[identifier] = ProviderResult(
            identifier=identifier,
            provider="fullenrich",
            status="found" if email else "not_found",
            email=email,
            verification_status=_clean(email_data.get("status")),
            matched_name=_clean(profile.get("full_name")),
            matched_company=matched_company,
            employer_match=_employer_matches(contact.company, matched_company),
            credits=per_record_cost,
        )

    return [
        results.get(
            contact.identifier,
            ProviderResult(
                identifier=contact.identifier,
                provider="fullenrich",
                status="not_found",
            ),
        )
        for contact in contacts
    ]


def build_comparison_rows(
    contacts: list[EvaluationContact],
    *,
    fullenrich_results: list[ProviderResult],
    prospeo_results: list[ProviderResult],
) -> list[dict[str, Any]]:
    fullenrich_by_id = {result.identifier: result for result in fullenrich_results}
    prospeo_by_id = {result.identifier: result for result in prospeo_results}
    rows: list[dict[str, Any]] = []
    for contact in contacts:
        fullenrich = fullenrich_by_id.get(contact.identifier)
        prospeo = prospeo_by_id.get(contact.identifier)
        recommended_email, recommendation = _recommend_email(
            contact,
            fullenrich=fullenrich,
            prospeo=prospeo,
        )
        rows.append(
            {
                "company_key": contact.company_key,
                "company": contact.company,
                "workflow": contact.workflow or "",
                "outreach_status": contact.outreach_status or "",
                "contact_name": contact.contact_name or "",
                "contact_role": contact.contact_role or "",
                "contact_title": contact.contact_title or "",
                "linkedin_url": contact.linkedin_url or "",
                "first_name": contact.first_name or "",
                "last_name": contact.last_name or "",
                "existing_email": contact.existing_email or "",
                "eligible_for_enrichment": contact.can_enrich,
                **_provider_columns("fullenrich", fullenrich),
                **_provider_columns("prospeo", prospeo),
                "recommended_email": recommended_email or "",
                "recommendation": recommendation,
            }
        )
    return rows


def _provider_columns(
    prefix: str,
    result: ProviderResult | None,
) -> dict[str, Any]:
    return {
        f"{prefix}_status": result.status if result else "not_run",
        f"{prefix}_email": result.email if result and result.email else "",
        f"{prefix}_verification_status": (
            result.verification_status if result and result.verification_status else ""
        ),
        f"{prefix}_matched_company": (
            result.matched_company if result and result.matched_company else ""
        ),
        f"{prefix}_employer_match": (
            result.employer_match if result and result.employer_match is not None else ""
        ),
        f"{prefix}_credits": result.credits if result and result.credits is not None else "",
        f"{prefix}_accepted": result.accepted if result else False,
    }


def _recommend_email(
    contact: EvaluationContact,
    *,
    fullenrich: ProviderResult | None,
    prospeo: ProviderResult | None,
) -> tuple[str | None, str]:
    if contact.existing_email:
        return contact.existing_email, "existing_email"
    if not contact.contact_name:
        return None, "missing_named_contact"
    if not contact.first_name or not contact.last_name:
        return None, "name_requires_review"

    accepted = [
        result
        for result in (fullenrich, prospeo)
        if result is not None and result.accepted and result.email
    ]
    if not accepted:
        return None, "no_verified_email"
    emails = {result.email.casefold(): result.email for result in accepted if result.email}
    if len(emails) > 1:
        return None, "provider_disagreement"
    email = next(iter(emails.values()))
    if len(accepted) == 2:
        return email, "both_providers_agree"
    return email, f"{accepted[0].provider}_only"


def _build_summary(
    contacts: list[EvaluationContact],
    *,
    comparison_rows: list[dict[str, Any]],
    fullenrich_results: list[ProviderResult],
    prospeo_results: list[ProviderResult],
) -> dict[str, Any]:
    return {
        "manifest_count": len(contacts),
        "eligible_count": sum(contact.can_enrich for contact in contacts),
        "existing_email_count": sum(bool(contact.existing_email) for contact in contacts),
        "missing_contact_count": sum(not contact.contact_name for contact in contacts),
        "name_requires_review_count": sum(
            bool(contact.contact_name and (not contact.first_name or not contact.last_name))
            for contact in contacts
        ),
        "recommended_count": sum(bool(row["recommended_email"]) for row in comparison_rows),
        "provider_agreement_count": sum(
            row["recommendation"] == "both_providers_agree" for row in comparison_rows
        ),
        "provider_disagreement_count": sum(
            row["recommendation"] == "provider_disagreement" for row in comparison_rows
        ),
        "providers": {
            "fullenrich": _provider_summary(fullenrich_results),
            "prospeo": _provider_summary(prospeo_results),
        },
    }


def _provider_summary(results: list[ProviderResult]) -> dict[str, Any]:
    return {
        "attempted_count": len(results),
        "found_count": sum(bool(result.email) for result in results),
        "accepted_count": sum(result.accepted for result in results),
        "employer_mismatch_count": sum(result.employer_match is False for result in results),
        "credits": round(sum(result.credits or 0 for result in results), 2),
    }


def _write_comparison_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _default_run_dir(data_dir: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return data_dir / "evaluations" / f"contact-email-{timestamp}"


def _chunks(values: list[EvaluationContact], size: int) -> list[list[EvaluationContact]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _nested_dict(value: dict[str, Any], *fields: str) -> dict[str, Any]:
    current: object = value
    for field in fields:
        if not isinstance(current, dict):
            return {}
        current = current.get(field)
    return current if isinstance(current, dict) else {}


def _dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_value(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _employer_matches(expected: str, actual: str | None) -> bool | None:
    if not actual:
        return None
    expected_key = _company_match_key(expected)
    actual_key = _company_match_key(actual)
    return bool(
        expected_key
        and actual_key
        and (
            expected_key == actual_key
            or expected_key in actual_key
            or actual_key in expected_key
        )
    )


def _company_match_key(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _json_object(response: httpx.Response) -> dict[str, Any]:
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"Expected {response.request.url.host} to return a JSON object.")
    return payload


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _clean(value: object | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(str(value).split()).strip()
    if cleaned.casefold() in {"null", "\\n"}:
        return None
    return cleaned or None
