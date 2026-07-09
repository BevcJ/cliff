from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from typing import Any

from typer.testing import CliRunner

from ai_hiring_radar import cli
from ai_hiring_radar.company_enrichment import CompanyEnrichmentRunResult
from ai_hiring_radar.job_description_extraction import JobDescriptionExtractionRunResult
from ai_hiring_radar.llm_usage import LLMUsage


runner = CliRunner()


def _settings(**overrides: Any) -> SimpleNamespace:
    values = {
        "job_description_extraction_model": "config-model",
        "job_description_extraction_provider": "default",
        "company_enrichment_model": "company-config-model",
        "inspection_database_url": "postgres://inspection-db",
        "azure_openai_endpoint": None,
        "azure_openai_api_key": None,
        "azure_openai_deployment_name": None,
        "azure_openai_api_version": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _result(
    *,
    dry_run: bool = False,
    model: str = "test-model",
    llm_usage: LLMUsage | None = None,
    llm_estimated_cost_usd: float | None = 0.0,
) -> JobDescriptionExtractionRunResult:
    return JobDescriptionExtractionRunResult(
        collection_date="2026-07-02",
        model=model,
        input_path=Path("data/processed/job_candidates_2026-07-02.jsonl"),
        output_path=Path("data/processed/job_description_extracts_2026-07-02.jsonl"),
        candidates_read=3,
        processable_count=2,
        extracted_count=0 if dry_run else 2,
        skipped_count=1,
        validation_error_count=0,
        llm_error_count=0,
        llm_usage=llm_usage or LLMUsage(),
        llm_estimated_cost_usd=llm_estimated_cost_usd,
        dry_run=dry_run,
    )


def _company_result(
    *, dry_run: bool = False, model: str = "gpt-5-mini"
) -> CompanyEnrichmentRunResult:
    return CompanyEnrichmentRunResult(
        collection_date="2026-07-02",
        model=model,
        company_input_path=Path("data/processed/companies_2026-07-02.jsonl"),
        candidate_input_path=Path("data/processed/job_candidates_2026-07-02.jsonl"),
        output_path=Path("data/processed/company_enrichment_extracts_2026-07-02.jsonl"),
        companies_read=3,
        processable_count=2,
        enriched_count=0 if dry_run else 2,
        skipped_count=1,
        validation_error_count=0,
        llm_error_count=0,
        dry_run=dry_run,
    )


def test_extract_job_descriptions_dry_run_does_not_create_extractor(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_runner(collection_date: str, **kwargs: Any) -> JobDescriptionExtractionRunResult:
        calls.append({"collection_date": collection_date, **kwargs})
        return _result(dry_run=True, model=kwargs["model"])

    def fail_extractor(**_: Any) -> None:
        raise AssertionError("dry run must not create the Pydantic AI extractor")

    monkeypatch.setattr(
        cli,
        "load_settings",
        _settings,
    )
    monkeypatch.setattr(cli, "PydanticAIJobDescriptionExtractor", fail_extractor)
    monkeypatch.setattr(cli, "run_job_description_extraction", fake_runner)

    result = runner.invoke(
        cli.app,
        [
            "extract-job-descriptions",
            "--date",
            "2026-07-02",
            "--limit",
            "3",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert calls[0]["collection_date"] == "2026-07-02"
    assert calls[0]["extractor"] is None
    assert calls[0]["model"] == "config-model"
    assert calls[0]["limit"] == 3
    assert calls[0]["country_codes"] is None
    assert calls[0]["country_names"] is None
    assert calls[0]["dry_run"] is True
    assert "Job description extraction dry run" in result.output
    assert "2 processable" in result.output


def test_extract_job_descriptions_passes_country_filter(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_runner(collection_date: str, **kwargs: Any) -> JobDescriptionExtractionRunResult:
        calls.append({"collection_date": collection_date, **kwargs})
        return _result(dry_run=True, model=kwargs["model"])

    def fail_extractor(**_: Any) -> None:
        raise AssertionError("dry run must not create the Pydantic AI extractor")

    monkeypatch.setattr(cli, "load_settings", _settings)
    monkeypatch.setattr(cli, "PydanticAIJobDescriptionExtractor", fail_extractor)
    monkeypatch.setattr(cli, "run_job_description_extraction", fake_runner)

    result = runner.invoke(
        cli.app,
        [
            "extract-job-descriptions",
            "--date",
            "2026-07-02",
            "--countries",
            "nl,dk",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert calls[0]["country_codes"] == ["nl", "dk"]
    assert calls[0]["country_names"] == ["Netherlands", "Denmark"]
    assert calls[0]["dry_run"] is True


def test_extract_job_descriptions_rejects_unknown_country_filter() -> None:
    result = runner.invoke(
        cli.app,
        [
            "extract-job-descriptions",
            "--date",
            "2026-07-02",
            "--countries",
            "se",
            "--dry-run",
        ],
    )

    assert result.exit_code != 0
    assert "Unknown country code(s): se" in result.output


def test_extract_job_descriptions_uses_model_override(monkeypatch) -> None:
    created_models: list[str] = []
    calls: list[dict[str, Any]] = []

    class FakeExtractor:
        def __init__(self, **kwargs: Any) -> None:
            model = kwargs["model"]
            created_models.append(model)

    monkeypatch.setattr(
        cli,
        "load_settings",
        lambda: _settings(azure_openai_deployment_name="azure-deployment"),
    )

    def fake_runner(collection_date: str, **kwargs: Any) -> JobDescriptionExtractionRunResult:
        calls.append({"collection_date": collection_date, **kwargs})
        return _result(model=kwargs["model"])

    monkeypatch.setattr(cli, "PydanticAIJobDescriptionExtractor", FakeExtractor)
    monkeypatch.setattr(cli, "run_job_description_extraction", fake_runner)

    result = runner.invoke(
        cli.app,
        [
            "extract-job-descriptions",
            "--date",
            "2026-07-02",
            "--model",
            "openai:gpt-5-mini",
        ],
    )

    assert result.exit_code == 0
    assert created_models == ["openai:gpt-5-mini"]
    assert isinstance(calls[0]["extractor"], FakeExtractor)
    assert calls[0]["model"] == "openai:gpt-5-mini"
    assert calls[0]["dry_run"] is False
    assert "Job description extraction complete" in result.output


def test_extract_job_descriptions_prints_llm_usage_summary(monkeypatch) -> None:
    class FakeExtractor:
        def __init__(self, **_: Any) -> None:
            pass

    def fake_runner(collection_date: str, **kwargs: Any) -> JobDescriptionExtractionRunResult:
        return _result(
            model=kwargs["model"],
            llm_usage=LLMUsage(
                input_tokens=1_000,
                output_tokens=500,
                requests=1,
            ),
            llm_estimated_cost_usd=0.00125,
        )

    monkeypatch.setattr(cli, "load_settings", _settings)
    monkeypatch.setattr(cli, "PydanticAIJobDescriptionExtractor", FakeExtractor)
    monkeypatch.setattr(cli, "run_job_description_extraction", fake_runner)

    result = runner.invoke(
        cli.app,
        ["extract-job-descriptions", "--date", "2026-07-02"],
    )

    assert result.exit_code == 0
    assert "LLM usage: 1 request(s), 0 tool call(s)" in result.output
    assert "1,000 input token(s)" in result.output
    assert "500 output token(s)" in result.output
    assert "Estimated LLM cost: $0.001250" in result.output


def test_extract_job_descriptions_uses_azure_deployment_from_settings(monkeypatch) -> None:
    created_kwargs: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []

    class FakeExtractor:
        def __init__(self, **kwargs: Any) -> None:
            created_kwargs.append(kwargs)

    def fake_runner(collection_date: str, **kwargs: Any) -> JobDescriptionExtractionRunResult:
        calls.append({"collection_date": collection_date, **kwargs})
        return _result(model=kwargs["model"])

    monkeypatch.setattr(
        cli,
        "load_settings",
        lambda: _settings(
            job_description_extraction_provider="azure",
            azure_openai_endpoint=(
                "https://dev-aibooking-openai.openai.azure.com/openai/responses?"
                "api-version=2025-04-01-preview"
            ),
            azure_openai_api_key="azure-key",
            azure_openai_deployment_name="gpt-5.4-mini",
        ),
    )
    monkeypatch.setattr(cli, "PydanticAIJobDescriptionExtractor", FakeExtractor)
    monkeypatch.setattr(cli, "run_job_description_extraction", fake_runner)

    result = runner.invoke(
        cli.app,
        [
            "extract-job-descriptions",
            "--date",
            "2026-07-02",
        ],
    )

    assert result.exit_code == 0
    assert created_kwargs == [
        {
            "model": "gpt-5.4-mini",
            "provider": "azure",
            "azure_endpoint": (
                "https://dev-aibooking-openai.openai.azure.com/openai/responses?"
                "api-version=2025-04-01-preview"
            ),
            "azure_api_key": "azure-key",
            "azure_api_version": None,
        }
    ]
    assert calls[0]["model"] == "gpt-5.4-mini"


def test_enrich_companies_dry_run_does_not_create_extractor(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_runner(collection_date: str, **kwargs: Any) -> CompanyEnrichmentRunResult:
        calls.append({"collection_date": collection_date, **kwargs})
        return _company_result(dry_run=True, model=kwargs["model"])

    def fail_extractor(**_: Any) -> None:
        raise AssertionError("dry run must not create the Pydantic AI extractor")

    monkeypatch.setattr(cli, "load_settings", _settings)
    monkeypatch.setattr(cli, "PydanticAICompanyEnrichmentExtractor", fail_extractor)
    monkeypatch.setattr(cli, "run_company_enrichment", fake_runner)

    result = runner.invoke(
        cli.app,
        [
            "enrich-companies",
            "--date",
            "2026-07-02",
            "--limit",
            "3",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert calls[0]["collection_date"] == "2026-07-02"
    assert calls[0]["extractor"] is None
    assert calls[0]["model"] == "company-config-model"
    assert calls[0]["limit"] == 3
    assert calls[0]["country_names"] is None
    assert calls[0]["dry_run"] is True
    assert "Company enrichment dry run" in result.output
    assert "2 processable" in result.output


def test_enrich_companies_passes_country_filter(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_runner(collection_date: str, **kwargs: Any) -> CompanyEnrichmentRunResult:
        calls.append({"collection_date": collection_date, **kwargs})
        return _company_result(dry_run=True, model=kwargs["model"])

    def fail_extractor(**_: Any) -> None:
        raise AssertionError("dry run must not create the Pydantic AI extractor")

    monkeypatch.setattr(cli, "load_settings", _settings)
    monkeypatch.setattr(cli, "PydanticAICompanyEnrichmentExtractor", fail_extractor)
    monkeypatch.setattr(cli, "run_company_enrichment", fake_runner)

    result = runner.invoke(
        cli.app,
        [
            "enrich-companies",
            "--date",
            "2026-07-02",
            "--countries",
            "nl,dk",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert calls[0]["country_names"] == ["Netherlands", "Denmark"]
    assert calls[0]["dry_run"] is True


def test_enrich_companies_rejects_unknown_country_filter() -> None:
    result = runner.invoke(
        cli.app,
        [
            "enrich-companies",
            "--date",
            "2026-07-02",
            "--countries",
            "se",
            "--dry-run",
        ],
    )

    assert result.exit_code != 0
    assert "Unknown country code(s): se" in result.output


def test_enrich_companies_uses_model_override(monkeypatch) -> None:
    created_models: list[str] = []
    calls: list[dict[str, Any]] = []

    class FakeExtractor:
        def __init__(self, **kwargs: Any) -> None:
            created_models.append(kwargs["model"])

    def fake_runner(collection_date: str, **kwargs: Any) -> CompanyEnrichmentRunResult:
        calls.append({"collection_date": collection_date, **kwargs})
        return _company_result(model=kwargs["model"])

    monkeypatch.setattr(cli, "load_settings", _settings)
    monkeypatch.setattr(cli, "PydanticAICompanyEnrichmentExtractor", FakeExtractor)
    monkeypatch.setattr(cli, "run_company_enrichment", fake_runner)

    result = runner.invoke(
        cli.app,
        [
            "enrich-companies",
            "--date",
            "2026-07-02",
            "--model",
            "gpt-5-mini",
        ],
    )

    assert result.exit_code == 0
    assert created_models == ["gpt-5-mini"]
    assert isinstance(calls[0]["extractor"], FakeExtractor)
    assert calls[0]["model"] == "gpt-5-mini"
    assert calls[0]["dry_run"] is False
    assert "Company enrichment complete" in result.output


def test_enrich_companies_uses_azure_settings(monkeypatch) -> None:
    created_kwargs: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []

    class FakeExtractor:
        def __init__(self, **kwargs: Any) -> None:
            created_kwargs.append(kwargs)

    def fake_runner(collection_date: str, **kwargs: Any) -> CompanyEnrichmentRunResult:
        calls.append({"collection_date": collection_date, **kwargs})
        return _company_result(model=kwargs["model"])

    monkeypatch.setattr(
        cli,
        "load_settings",
        lambda: _settings(
            company_enrichment_model="gpt-5-mini",
            azure_openai_endpoint=(
                "https://dev-aibooking-openai.openai.azure.com/openai/responses?"
                "api-version=2025-04-01-preview"
            ),
            azure_openai_api_key="azure-key",
            azure_openai_api_version="2025-04-01-preview",
        ),
    )
    monkeypatch.setattr(cli, "PydanticAICompanyEnrichmentExtractor", FakeExtractor)
    monkeypatch.setattr(cli, "run_company_enrichment", fake_runner)

    result = runner.invoke(
        cli.app,
        [
            "enrich-companies",
            "--date",
            "2026-07-02",
        ],
    )

    assert result.exit_code == 0
    assert created_kwargs == [
        {
            "model": "gpt-5-mini",
            "azure_endpoint": (
                "https://dev-aibooking-openai.openai.azure.com/openai/responses?"
                "api-version=2025-04-01-preview"
            ),
            "azure_api_key": "azure-key",
            "azure_api_version": "2025-04-01-preview",
        }
    ]
    assert calls[0]["model"] == "gpt-5-mini"


def test_inspect_launches_streamlit_with_normalized_date(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(cli, "_launch_inspection_app", calls.append)

    result = runner.invoke(
        cli.app,
        [
            "inspect",
            "--date",
            "2026-07-02",
        ],
    )

    assert result.exit_code == 0
    assert calls == ["2026-07-02"]
    assert "Launching company inspection UI for 2026-07-02" in result.output


def test_export_inspection_writes_artifact(monkeypatch) -> None:
    calls: list[str] = []

    def fake_export(collection_date: str) -> SimpleNamespace:
        calls.append(collection_date)
        return SimpleNamespace(
            path=Path("data/processed/inspection_companies_2026-07-02.jsonl"),
            company_count=2,
            job_count=3,
        )

    monkeypatch.setattr(cli, "export_company_inspection_artifact", fake_export)

    result = runner.invoke(
        cli.app,
        [
            "export-inspection",
            "--date",
            "2026-07-02",
        ],
    )

    assert result.exit_code == 0
    assert calls == ["2026-07-02"]
    assert "Inspection artifact complete: 2 company record(s), 3 job record(s)." in result.output
    assert "data/processed/inspection_companies_2026-07-02.jsonl" in result.output


def test_sync_inspection_db_parses_date_and_uses_database_url(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_sync(collection_date: str, *, database_url: str) -> SimpleNamespace:
        calls.append({"collection_date": collection_date, "database_url": database_url})
        return SimpleNamespace(
            collection_date=collection_date,
            snapshot_count=2,
            job_count=3,
            database_url_configured=True,
        )

    monkeypatch.setattr(
        cli,
        "require_inspection_database_url",
        lambda: "postgres://inspection-db",
    )
    monkeypatch.setattr(cli, "sync_inspection_database", fake_sync)

    result = runner.invoke(
        cli.app,
        ["sync-inspection-db", "--date", "2026-07-02"],
    )

    assert result.exit_code == 0
    assert calls == [
        {"collection_date": "2026-07-02", "database_url": "postgres://inspection-db"}
    ]
    assert "Inspection DB sync complete: 2 company snapshot(s), 3 compact job(s)." in result.output
    assert "Database: configured" in result.output


def test_sync_inspection_db_exits_when_database_url_missing(monkeypatch) -> None:
    def missing_url() -> None:
        raise RuntimeError("AI_HIRING_RADAR_DATABASE_URL is required")

    monkeypatch.setattr(cli, "require_inspection_database_url", missing_url)

    result = runner.invoke(
        cli.app,
        ["sync-inspection-db", "--date", "2026-07-02"],
    )

    assert result.exit_code == 1
    assert "AI_HIRING_RADAR_DATABASE_URL is required" in result.output


def test_sync_inspection_db_reports_sync_failures(monkeypatch) -> None:
    def fail_sync(collection_date: str, *, database_url: str) -> None:
        raise RuntimeError("relation does not exist")

    monkeypatch.setattr(
        cli,
        "require_inspection_database_url",
        lambda: "postgres://inspection-db",
    )
    monkeypatch.setattr(cli, "sync_inspection_database", fail_sync)

    result = runner.invoke(
        cli.app,
        ["sync-inspection-db", "--date", "2026-07-02"],
    )

    assert result.exit_code == 1
    assert "Inspection DB sync failed: relation does not exist" in result.output


def test_sync_inspection_db_rejects_invalid_date() -> None:
    result = runner.invoke(
        cli.app,
        ["sync-inspection-db", "--date", "not-a-date"],
    )

    assert result.exit_code != 0
    assert "Date must use YYYY-MM-DD format" in result.output


def test_inspect_rejects_invalid_date() -> None:
    result = runner.invoke(
        cli.app,
        [
            "inspect",
            "--date",
            "not-a-date",
        ],
    )

    assert result.exit_code != 0
    assert "Date must use YYYY-MM-DD format" in result.output


def test_inspect_propagates_streamlit_exit_code(monkeypatch) -> None:
    def fail_launcher(collection_date: str) -> None:
        raise subprocess.CalledProcessError(returncode=7, cmd=["streamlit", collection_date])

    monkeypatch.setattr(cli, "_launch_inspection_app", fail_launcher)

    result = runner.invoke(
        cli.app,
        [
            "inspect",
            "--date",
            "2026-07-02",
        ],
    )

    assert result.exit_code == 7


def test_launch_inspection_app_runs_streamlit_module(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_run(command: list[str], *, check: bool) -> None:
        calls.append({"command": command, "check": check})

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    cli._launch_inspection_app("2026-07-02")

    command = calls[0]["command"]
    assert calls[0]["check"] is True
    assert command[:4] == [sys.executable, "-m", "streamlit", "run"]
    assert command[-3:] == ["--", "--date", "2026-07-02"]
    assert command[4].endswith("inspection_app.py")


def test_discover_teamtailor_dry_run_prints_queries() -> None:
    result = runner.invoke(
        cli.app,
        [
            "discover-teamtailor",
            "--countries",
            "nl",
            "--limit",
            "1",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert "Generated 1 Teamtailor discovery queries." in result.output
    assert "site:*.teamtailor.com" in result.output


def test_collect_teamtailor_board_url_dry_run_prints_normalized_board() -> None:
    result = runner.invoke(
        cli.app,
        [
            "collect-teamtailor",
            "--board-url",
            "https://acme.teamtailor.com/jobs/123-ai-engineer",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert "Normalized 1 Teamtailor board URL(s)." in result.output
    assert "https://acme.teamtailor.com" in result.output
