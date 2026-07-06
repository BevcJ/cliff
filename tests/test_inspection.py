from __future__ import annotations

import json

import pytest

from ai_hiring_radar.inspection import (
    export_company_inspection_artifact,
    inspection_artifact_filename,
    load_company_inspection_data,
)
from ai_hiring_radar.storage_json import processed_dir, write_processed_jsonl


def _company(**overrides):  # noqa: ANN001, ANN202 - compact test fixture helper.
    company = {
        "record_type": "company_intelligence_title_only",
        "company": "Acme AI",
        "countries": ["Netherlands"],
        "role_classification": "AI Execution Role",
        "ai_execution_titles": ["AI Engineer"],
        "ai_product_titles": [],
        "ai_role_title_counts": [{"title": "Senior AI Engineer", "count": 1}],
        "matched_search_terms": ["AI Engineer"],
        "evidence_urls": ["https://jobs.example.com/acme"],
        "sources": ["lever"],
        "evidence_quality": ["title_only_ats_listing"],
        "needs_review": True,
        "review_status": "new",
        "why_interesting": "Title-only signal.",
    }
    company.update(overrides)
    return company


def _candidate(**overrides):  # noqa: ANN001, ANN202 - compact test fixture helper.
    candidate = {
        "record_type": "job_candidate",
        "job_id": "job-1",
        "source": "lever",
        "platform": "lever",
        "platform_company_slug": "acme-ai",
        "platform_job_id": "senior-ai-engineer",
        "company_normalized": "Acme AI",
        "job_title_raw": "Senior AI Engineer",
        "job_title_normalized": "AI Engineer",
        "role_group": "AI Execution Role",
        "role_search_term": "AI Engineer",
        "source_url": "https://jobs.example.com/acme",
        "job_url": "https://jobs.example.com/acme/job-1",
        "country": "Netherlands",
        "job_countries": ["Netherlands"],
        "team": "Engineering",
        "department": "AI",
        "location": "Amsterdam, Netherlands",
        "employment_type": "Full-time",
        "workplace_type": "Hybrid",
        "description": "<p>HTML description</p>",
        "description_plain": "Plain description",
    }
    candidate.update(overrides)
    return candidate


def _jd_extract(**overrides):  # noqa: ANN001, ANN202 - compact test fixture helper.
    extract = {
        "record_type": "job_description_extract",
        "job_id": "job-1",
        "source": "lever",
        "platform": "lever",
        "company_normalized": "Acme AI",
        "job_title_raw": "Senior AI Engineer",
        "job_url": "https://jobs.example.com/acme/job-1",
        "workplace_mode": "remote",
        "ai_team_context": "existing_ai_team",
        "delivery_context": "internal",
        "contacts": [
            {
                "name": "Ada Lovelace",
                "role": "cto",
                "title": "CTO",
                "email": "ada@example.com",
            }
        ],
        "posted_at": "2026-07-01T00:00:00Z",
        "updated_at": "2026-07-02T00:00:00Z",
    }
    extract.update(overrides)
    return extract


def _enrichment(**overrides):  # noqa: ANN001, ANN202 - compact test fixture helper.
    enrichment = {
        "record_type": "company_enrichment_extract",
        "company": "Acme AI",
        "company_key": "acme-ai",
        "company_description": "Acme AI builds internal AI tools.",
        "company_description_source_urls": ["https://example.com/about"],
        "industry": "Software",
        "company_size": "101-500",
        "founded_year": 2020,
        "company_type": "ai_native",
        "funding_summary": None,
        "ai_tech_forward_signal": "strong",
        "ai_tech_forward_reason": "Public AI product evidence.",
        "contacts": [
            {
                "name": "Ada Lovelace",
                "role": "cto",
                "title": "CTO",
                "email": "ada@example.com",
                "source_urls": ["https://example.com/team"],
            }
        ],
        "source_urls": ["https://example.com/about", "https://example.com/team"],
        "enriched_at": "2026-07-02T10:00:00Z",
    }
    enrichment.update(overrides)
    return enrichment


def test_load_company_inspection_data_joins_and_aggregates_records(tmp_path) -> None:
    write_processed_jsonl(
        "companies_2026-07-02.jsonl",
        [_company()],
        data_dir=tmp_path,
    )
    write_processed_jsonl(
        "job_candidates_2026-07-02.jsonl",
        [_candidate()],
        data_dir=tmp_path,
    )
    write_processed_jsonl(
        "job_description_extracts_2026-07-02.jsonl",
        [
            _jd_extract(),
            _jd_extract(
                job_id="orphan-job",
                job_title_raw="AI Consultant",
                workplace_mode="hybrid",
                ai_team_context=None,
                delivery_context="external_clients",
                contacts=[
                    {
                        "name": "Grace Hopper",
                        "role": "hiring_manager",
                        "linkedin_url": "https://www.linkedin.com/in/grace",
                    }
                ],
            ),
        ],
        data_dir=tmp_path,
    )
    write_processed_jsonl(
        "company_enrichment_extracts_2026-07-02.jsonl",
        [
            _enrichment(company_type="traditional_company"),
            _enrichment(company_type="ai_native"),
        ],
        data_dir=tmp_path,
    )

    dataset = load_company_inspection_data("2026-07-02", data_dir=tmp_path)

    assert dataset.counts.companies_loaded == 1
    assert dataset.counts.candidates_loaded == 1
    assert dataset.counts.job_description_extracts_loaded == 2
    assert dataset.counts.company_enrichments_loaded == 2
    assert dataset.missing_optional_files == []

    record = dataset.records[0]
    assert record["company_key"] == "acme ai"
    assert record["company_type"] == "ai_native"
    assert record["company_size"] == "101-500"
    assert record["industry"] == "Software"
    assert record["ai_tech_forward_signal"] == "strong"
    assert record["company_source_urls"] == [
        "https://example.com/about",
        "https://example.com/team",
    ]
    assert record["workplace_modes"] == ["remote", "hybrid"]
    assert record["ai_team_contexts"] == ["existing_ai_team"]
    assert record["delivery_contexts"] == ["internal", "external_clients"]
    assert record["job_count"] == 2
    assert record["job_description_extract_count"] == 2
    assert record["has_company_enrichment"] is True
    assert record["has_job_description_extracts"] is True
    assert record["has_contacts"] is True
    assert len(record["company_contacts"]) == 1
    assert len(record["job_contacts"]) == 2
    assert len(record["contacts"]) == 2

    matched_job = record["jobs"][0]
    assert matched_job["job_id"] == "job-1"
    assert matched_job["description"] == "Plain description"
    assert matched_job["workplace_mode"] == "remote"
    assert matched_job["has_description"] is True

    orphan_job = record["jobs"][1]
    assert orphan_job["job_id"] == "orphan-job"
    assert orphan_job["job_title_raw"] == "AI Consultant"
    assert orphan_job["has_description"] is False
    assert orphan_job["delivery_context"] == "external_clients"


def test_load_company_inspection_data_handles_missing_optional_files(tmp_path) -> None:
    write_processed_jsonl(
        "companies_2026-07-02.jsonl",
        [_company()],
        data_dir=tmp_path,
    )

    dataset = load_company_inspection_data("2026-07-02", data_dir=tmp_path)

    assert dataset.counts.companies_loaded == 1
    assert dataset.counts.candidates_loaded == 0
    assert dataset.counts.job_description_extracts_loaded == 0
    assert dataset.counts.company_enrichments_loaded == 0
    assert [path.name for path in dataset.missing_optional_files] == [
        "job_candidates_2026-07-02.jsonl",
        "job_description_extracts_2026-07-02.jsonl",
        "company_enrichment_extracts_2026-07-02.jsonl",
    ]
    assert dataset.records[0]["jobs"] == []
    assert dataset.records[0]["has_company_enrichment"] is False
    assert dataset.records[0]["has_job_description_extracts"] is False


def test_load_company_inspection_data_fails_when_companies_file_missing(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="Required companies file"):
        load_company_inspection_data("2026-07-02", data_dir=tmp_path)


def test_load_company_inspection_data_counts_malformed_rows(tmp_path) -> None:
    root = processed_dir(data_dir=tmp_path)
    root.mkdir(parents=True)
    (root / "companies_2026-07-02.jsonl").write_text(
        "\n".join(
            [
                json.dumps(_company()),
                json.dumps(["not", "a", "dict"]),
                "{bad-json",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (root / "job_candidates_2026-07-02.jsonl").write_text(
        "\n".join(
            [
                json.dumps(_candidate()),
                json.dumps("not-a-dict"),
                "{bad-json",
            ]
        ),
        encoding="utf-8",
    )

    dataset = load_company_inspection_data("2026-07-02", data_dir=tmp_path)

    assert dataset.counts.companies_loaded == 1
    assert dataset.counts.candidates_loaded == 1
    assert dataset.counts.skipped_companies == 2
    assert dataset.counts.skipped_candidates == 2
    assert dataset.records[0]["job_count"] == 1


def test_export_company_inspection_artifact_writes_compact_records(tmp_path) -> None:
    write_processed_jsonl(
        "companies_2026-07-02.jsonl",
        [_company()],
        data_dir=tmp_path,
    )
    write_processed_jsonl(
        "job_candidates_2026-07-02.jsonl",
        [_candidate()],
        data_dir=tmp_path,
    )
    write_processed_jsonl(
        "job_description_extracts_2026-07-02.jsonl",
        [_jd_extract()],
        data_dir=tmp_path,
    )
    write_processed_jsonl(
        "company_enrichment_extracts_2026-07-02.jsonl",
        [_enrichment()],
        data_dir=tmp_path,
    )

    result = export_company_inspection_artifact("2026-07-02", data_dir=tmp_path)

    assert result.path == processed_dir(data_dir=tmp_path) / inspection_artifact_filename(
        "2026-07-02"
    )
    assert result.company_count == 1
    assert result.job_count == 1

    record = json.loads(result.path.read_text(encoding="utf-8"))
    assert record["inspection_artifact_version"] == 1
    assert record["company"] == "Acme AI"
    assert record["company_type"] == "ai_native"
    assert record["jobs"][0]["job_title_raw"] == "Senior AI Engineer"
    assert record["jobs"][0]["has_description"] is True
    assert "description" not in record["jobs"][0]
    assert "raw_candidate_record" not in record["jobs"][0]
    assert "raw_job_description_extract" not in record["jobs"][0]
    assert "raw_company_record" not in record
    assert "raw_company_enrichment_record" not in record


def test_load_company_inspection_data_falls_back_to_artifact(tmp_path) -> None:
    write_processed_jsonl(
        "companies_2026-07-02.jsonl",
        [_company()],
        data_dir=tmp_path,
    )
    write_processed_jsonl(
        "job_candidates_2026-07-02.jsonl",
        [_candidate()],
        data_dir=tmp_path,
    )
    write_processed_jsonl(
        "job_description_extracts_2026-07-02.jsonl",
        [_jd_extract()],
        data_dir=tmp_path,
    )
    write_processed_jsonl(
        "company_enrichment_extracts_2026-07-02.jsonl",
        [_enrichment()],
        data_dir=tmp_path,
    )
    export_company_inspection_artifact("2026-07-02", data_dir=tmp_path)

    root = processed_dir(data_dir=tmp_path)
    for filename in (
        "companies_2026-07-02.jsonl",
        "job_candidates_2026-07-02.jsonl",
        "job_description_extracts_2026-07-02.jsonl",
        "company_enrichment_extracts_2026-07-02.jsonl",
    ):
        (root / filename).unlink()

    dataset = load_company_inspection_data("2026-07-02", data_dir=tmp_path)

    assert dataset.counts.companies_loaded == 1
    assert dataset.counts.candidates_loaded == 1
    assert dataset.counts.job_description_extracts_loaded == 1
    assert dataset.counts.company_enrichments_loaded == 1
    assert dataset.missing_optional_files == []
    assert dataset.records[0]["jobs"][0]["has_description"] is True
    assert "description" not in dataset.records[0]["jobs"][0]
