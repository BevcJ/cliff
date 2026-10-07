from __future__ import annotations

import csv
import json
from pathlib import Path

import httpx
import pytest

from ai_hiring_radar.contact_email_evaluation import (
    ProviderResult,
    _load_or_run_prospeo,
    build_comparison_rows,
    load_evaluation_contacts,
    run_contact_email_evaluation,
)


def _write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "collection_date",
        "company_key",
        "company",
        "countries",
        "fit_status",
        "outreach_status",
        "workflow",
        "contact_name",
        "contact_role",
        "contact_title",
        "existing_email",
        "contact_linkedin_url",
        "contact_source_urls",
        "company_source_urls",
    ]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _row(**overrides: str) -> dict[str, str]:
    row = {
        "collection_date": "2026-07-24",
        "company_key": "acme ai",
        "company": "Acme AI",
        "countries": '["Netherlands"]',
        "fit_status": "best_fit",
        "outreach_status": "not_started",
        "workflow": "shortlist",
        "contact_name": "Ada Lovelace",
        "contact_role": "cto",
        "contact_title": "CTO",
        "existing_email": "",
        "contact_linkedin_url": "https://www.linkedin.com/in/ada-lovelace",
        "contact_source_urls": "[]",
        "company_source_urls": "[]",
    }
    row.update(overrides)
    return row


def test_load_evaluation_contacts_splits_names_and_preserves_ineligible_rows(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "contacts.csv"
    _write_manifest(
        input_path,
        [
            _row(existing_email="null"),
            _row(
                company_key="beta",
                company="Beta",
                contact_name="",
                contact_role="",
                contact_title="",
                contact_linkedin_url="",
            ),
            _row(
                company_key="gamma",
                company="Gamma",
                contact_name="Grace Hopper",
                existing_email="grace@gamma.example",
            ),
        ],
    )

    contacts = load_evaluation_contacts(input_path)

    assert [(contact.first_name, contact.last_name) for contact in contacts] == [
        ("Ada", "Lovelace"),
        (None, None),
        ("Grace", "Hopper"),
    ]
    assert [contact.can_enrich for contact in contacts] == [True, False, False]
    assert contacts[0].existing_email is None


def test_run_contact_email_evaluation_calls_both_providers_and_writes_reports(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "contacts.csv"
    run_dir = tmp_path / "run"
    _write_manifest(
        input_path,
        [
            _row(),
            _row(
                company_key="beta",
                company="Beta",
                contact_name="Grace Hopper",
                contact_linkedin_url="",
            ),
        ],
    )
    requests: list[httpx.Request] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/bulk-enrich-person":
            payload = json.loads(request.content)
            assert payload["only_verified_email"] is True
            assert payload["data"] == [
                {
                    "identifier": "acme ai",
                    "full_name": "Ada Lovelace",
                    "company_name": "Acme AI",
                    "linkedin_url": "https://www.linkedin.com/in/ada-lovelace",
                }
            ]
            prospeo_request_count = sum(
                saved.url.path == "/bulk-enrich-person" for saved in requests
            )
            if prospeo_request_count == 1:
                return httpx.Response(
                    429,
                    headers={
                        "x-minute-request-left": "0",
                        "x-minute-reset-seconds": "2",
                    },
                    json={"error": True, "error_code": "Rate limit exceeded"},
                )
            return httpx.Response(
                200,
                json={
                    "error": False,
                    "total_cost": 1,
                    "matched": [
                        {
                            "identifier": "acme ai",
                            "person": {
                                "full_name": "Ada Lovelace",
                                "email": {
                                    "email": "ada@acme.example",
                                    "status": "VERIFIED",
                                },
                            },
                            "company": {"name": "Acme AI"},
                        }
                    ],
                    "not_matched": [],
                    "invalid_datapoints": [],
                },
            )
        if request.url.path == "/api/v2/contact/enrich/bulk" and request.method == "POST":
            payload = json.loads(request.content)
            assert payload["data"] == [
                {
                    "first_name": "Ada",
                    "last_name": "Lovelace",
                    "company_name": "Acme AI",
                    "enrich_fields": ["contact.work_emails"],
                    "custom": {"evaluation_id": "acme ai"},
                    "linkedin_url": "https://www.linkedin.com/in/ada-lovelace",
                }
            ]
            return httpx.Response(200, json={"enrichment_id": "enrichment-1"})
        if request.url.path == "/api/v2/contact/enrich/bulk/enrichment-1":
            return httpx.Response(
                200,
                json={
                    "status": "FINISHED",
                    "cost": {"credits": 1},
                    "data": [
                        {
                            "custom": {"evaluation_id": "acme ai"},
                            "contact_info": {
                                "most_probable_work_email": {
                                    "email": "ada@acme.example",
                                    "status": "DELIVERABLE",
                                }
                            },
                            "profile": {
                                "full_name": "Ada Lovelace",
                                "employment": {
                                    "current": {"company": {"name": "Acme AI"}}
                                },
                            },
                        }
                    ],
                },
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = run_contact_email_evaluation(
            input_path,
            fullenrich_api_key="fullenrich-key",
            prospeo_api_key="prospeo-key",
            limit=1,
            output_dir=run_dir,
            fullenrich_poll_seconds=0,
            http_client=client,
            sleep=sleeps.append,
        )

    assert result.manifest_count == 1
    assert result.eligible_count == 1
    assert result.fullenrich_found_count == 1
    assert result.prospeo_found_count == 1
    assert result.recommended_count == 1
    assert len(requests) == 4
    assert sleeps == [2.0]
    comparison = (run_dir / "comparison.csv").read_text(encoding="utf-8")
    assert "ada@acme.example" in comparison
    assert "both_providers_agree" in comparison
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["provider_agreement_count"] == 1
    assert (run_dir / "prospeo-raw.json").exists()
    assert (run_dir / "fullenrich-raw.json").exists()


def test_comparison_requires_manual_review_when_verified_providers_disagree(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "contacts.csv"
    _write_manifest(input_path, [_row(contact_linkedin_url="")])
    contact = load_evaluation_contacts(input_path)[0]

    rows = build_comparison_rows(
        [contact],
        fullenrich_results=[
            ProviderResult(
                identifier=contact.identifier,
                provider="fullenrich",
                status="found",
                email="ada@acme.example",
                verification_status="DELIVERABLE",
                matched_company="Acme AI",
                employer_match=True,
            )
        ],
        prospeo_results=[
            ProviderResult(
                identifier=contact.identifier,
                provider="prospeo",
                status="found",
                email="a.lovelace@acme.example",
                verification_status="VERIFIED",
                matched_company="Acme AI",
                employer_match=True,
            )
        ],
    )

    assert rows[0]["recommended_email"] == ""
    assert rows[0]["recommendation"] == "provider_disagreement"


def test_prospeo_paces_and_resumes_from_each_completed_contact(tmp_path: Path) -> None:
    input_path = tmp_path / "contacts.csv"
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_manifest(
        input_path,
        [
            _row(),
            _row(
                company_key="beta",
                company="Beta",
                contact_name="Grace Hopper",
                contact_linkedin_url="",
            ),
        ],
    )
    contacts = load_evaluation_contacts(input_path)
    sleeps: list[float] = []

    def interrupted_handler(request: httpx.Request) -> httpx.Response:
        identifier = json.loads(request.content)["data"][0]["identifier"]
        if identifier == "acme ai":
            return httpx.Response(
                400,
                headers={"x-second-rate-limit": "1"},
                json={"error": True, "error_code": "NO_MATCH"},
            )
        raise httpx.ConnectError("offline", request=request)

    with httpx.Client(transport=httpx.MockTransport(interrupted_handler)) as client:
        with pytest.raises(httpx.ConnectError, match="offline"):
            _load_or_run_prospeo(
                run_dir,
                contacts=contacts,
                api_key="prospeo-key",
                http_client=client,
                sleep=sleeps.append,
            )

    raw = json.loads((run_dir / "prospeo-raw.json").read_text(encoding="utf-8"))
    assert raw["completed_identifiers"] == ["acme ai"]
    assert sleeps == [1.0]
    resumed_identifiers: list[str] = []

    def resumed_handler(request: httpx.Request) -> httpx.Response:
        identifier = json.loads(request.content)["data"][0]["identifier"]
        resumed_identifiers.append(identifier)
        return httpx.Response(
            400,
            json={"error": True, "error_code": "NO_MATCH"},
        )

    with httpx.Client(transport=httpx.MockTransport(resumed_handler)) as client:
        results = _load_or_run_prospeo(
            run_dir,
            contacts=contacts,
            api_key="prospeo-key",
            http_client=client,
            sleep=sleeps.append,
        )

    assert resumed_identifiers == ["beta"]
    assert [result.status for result in results] == ["not_found", "not_found"]


def test_interrupted_fullenrich_run_resumes_without_repeating_posts(tmp_path: Path) -> None:
    input_path = tmp_path / "contacts.csv"
    run_dir = tmp_path / "run"
    _write_manifest(
        input_path,
        [
            _row(),
            _row(
                company_key="beta",
                company="Beta",
                contact_name="Grace Hopper",
                contact_linkedin_url="",
            ),
        ],
    )
    first_requests: list[httpx.Request] = []

    def first_handler(request: httpx.Request) -> httpx.Response:
        first_requests.append(request)
        if request.url.path == "/bulk-enrich-person":
            return httpx.Response(
                400,
                json={"error": True, "error_code": "NO_MATCH"},
            )
        if request.url.path == "/api/v2/contact/enrich/bulk" and request.method == "POST":
            return httpx.Response(200, json={"enrichment_id": "enrichment-1"})
        if request.url.path == "/api/v2/contact/enrich/bulk/enrichment-1":
            return httpx.Response(
                400,
                json={
                    "code": "error.enrichment.in_progress",
                    "message": "Try again later",
                },
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    with httpx.Client(transport=httpx.MockTransport(first_handler)) as client:
        with pytest.raises(RuntimeError, match=f"Run state is preserved in {run_dir}"):
            run_contact_email_evaluation(
                input_path,
                fullenrich_api_key="fullenrich-key",
                prospeo_api_key="prospeo-key",
                limit=1,
                output_dir=run_dir,
                fullenrich_poll_seconds=0,
                fullenrich_timeout_seconds=0,
                http_client=client,
                sleep=lambda _: None,
            )

    assert [request.method for request in first_requests] == ["POST", "POST", "GET"]
    resumed_requests: list[httpx.Request] = []

    def resumed_handler(request: httpx.Request) -> httpx.Response:
        resumed_requests.append(request)
        assert request.method == "GET"
        assert request.url.path == "/api/v2/contact/enrich/bulk/enrichment-1"
        return httpx.Response(
            200,
            json={"status": "FINISHED", "cost": {"credits": 0}, "data": []},
        )

    with httpx.Client(transport=httpx.MockTransport(resumed_handler)) as client:
        result = run_contact_email_evaluation(
            input_path,
            fullenrich_api_key="fullenrich-key",
            prospeo_api_key="prospeo-key",
            output_dir=run_dir,
            fullenrich_poll_seconds=0,
            http_client=client,
            sleep=lambda _: None,
        )

    assert result.eligible_count == 1
    assert result.manifest_count == 1
    assert len(resumed_requests) == 1
