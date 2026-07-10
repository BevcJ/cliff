from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from typing import Any

import pytest
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


def test_collect_workable_jsonl_file_skips_serper(monkeypatch, tmp_path: Path) -> None:
    boards_path = tmp_path / "boards.jsonl"
    boards_path.write_text(
        '{"board_url": "https://apply.workable.com/acme/jobs"}\n'
        '{"board_url": "beta"}\n',
        encoding="utf-8",
    )
    client_kwargs: list[dict[str, Any]] = []
    collection_calls: list[dict[str, Any]] = []

    class FakeWorkableClient:
        def __init__(self, **kwargs: Any) -> None:
            client_kwargs.append(kwargs)

        def close(self) -> None:
            pass

    def fake_collect(board_values: list[str], **kwargs: Any) -> SimpleNamespace:
        collection_calls.append({"board_values": list(board_values), **kwargs})
        return SimpleNamespace(
            manifest_path=Path("manifest.json"),
            board_count=2,
            result_files=["acme.json", "beta.json"],
            written_count=2,
            resumed_count=0,
            error_count=0,
        )

    def fail_serper() -> None:
        raise AssertionError("explicit board files must not access Serper")

    monkeypatch.setattr(cli, "require_serper_api_key", fail_serper)
    monkeypatch.setattr(cli, "WorkableClient", FakeWorkableClient)
    monkeypatch.setattr(cli, "collect_workable_boards", fake_collect)

    result = runner.invoke(
        cli.app,
        ["collect-workable", "--boards-file", str(boards_path)],
    )

    assert result.exit_code == 0
    assert client_kwargs == [{"request_delay_seconds": 0.5, "max_retries": 3}]
    assert collection_calls[0]["board_values"] == [
        "https://apply.workable.com/acme",
        "https://apply.workable.com/beta",
    ]
    assert collection_calls[0]["collection_date"] is None
    assert collection_calls[0]["resume"] is True


def test_collect_teamtailor_plain_text_file_dry_run(
    monkeypatch,
    tmp_path: Path,
) -> None:
    boards_path = tmp_path / "boards.txt"
    boards_path.write_text(
        "acme\nhttps://beta.teamtailor.com/jobs/123\n",
        encoding="utf-8",
    )

    def fail_client(**_: Any) -> None:
        raise AssertionError("dry run must not create a Teamtailor client")

    monkeypatch.setattr(cli, "TeamtailorClient", fail_client)

    result = runner.invoke(
        cli.app,
        ["collect-teamtailor", "--boards-file", str(boards_path), "--dry-run"],
    )

    assert result.exit_code == 0
    assert "Normalized 2 Teamtailor board URL(s)." in result.output
    assert "https://acme.teamtailor.com" in result.output
    assert "https://beta.teamtailor.com" in result.output


def test_collect_workable_combines_and_dedupes_explicit_inputs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    boards_path = tmp_path / "boards.txt"
    boards_path.write_text(
        "https://apply.workable.com/ACME/jobs\nbeta\n",
        encoding="utf-8",
    )

    def fail_client(**_: Any) -> None:
        raise AssertionError("dry run must not create a Workable client")

    monkeypatch.setattr(cli, "WorkableClient", fail_client)

    result = runner.invoke(
        cli.app,
        [
            "collect-workable",
            "--board-url",
            "acme",
            "--board-url",
            "gamma",
            "--boards-file",
            str(boards_path),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert "Normalized 3 Workable board URL(s)." in result.output
    assert result.output.count("https://apply.workable.com/acme") == 1
    assert result.output.index("https://apply.workable.com/acme") < result.output.index(
        "https://apply.workable.com/gamma"
    )
    assert result.output.index("https://apply.workable.com/gamma") < result.output.index(
        "https://apply.workable.com/beta"
    )


def test_collect_workable_empty_file_is_explicit_and_skips_discovery(
    monkeypatch,
    tmp_path: Path,
) -> None:
    boards_path = tmp_path / "empty.txt"
    boards_path.write_text("", encoding="utf-8")

    def fail_discovery(**_: Any) -> None:
        raise AssertionError("an explicitly empty board file must not trigger discovery")

    monkeypatch.setattr(cli, "_build_workable_discovery_queries", fail_discovery)

    result = runner.invoke(
        cli.app,
        ["collect-workable", "--boards-file", str(boards_path), "--dry-run"],
    )

    assert result.exit_code == 0
    assert "Normalized 0 Workable board URL(s)." in result.output


@pytest.mark.parametrize("invalid_date", ["not-a-date", "20260702", "2026-W27-4"])
def test_collect_workable_rejects_invalid_collection_date(invalid_date: str) -> None:
    result = runner.invoke(
        cli.app,
        [
            "collect-workable",
            "--board-url",
            "acme",
            "--collection-date",
            invalid_date,
            "--dry-run",
        ],
    )

    assert result.exit_code != 0
    assert "Date must use YYYY-MM-DD format" in result.output


def test_collect_workable_passes_resilience_options_and_reports_counts(
    monkeypatch,
) -> None:
    client_kwargs: list[dict[str, Any]] = []
    collection_calls: list[dict[str, Any]] = []

    class FakeWorkableClient:
        def __init__(self, **kwargs: Any) -> None:
            client_kwargs.append(kwargs)

        def close(self) -> None:
            pass

    def fake_collect(board_values: list[str], **kwargs: Any) -> SimpleNamespace:
        collection_calls.append({"board_values": list(board_values), **kwargs})
        return SimpleNamespace(
            manifest_path=Path("manifest.json"),
            board_count=3,
            result_files=["written.json", "resumed.json"],
            written_count=1,
            resumed_count=1,
            error_count=1,
        )

    monkeypatch.setattr(cli, "WorkableClient", FakeWorkableClient)
    monkeypatch.setattr(cli, "collect_workable_boards", fake_collect)

    result = runner.invoke(
        cli.app,
        [
            "collect-workable",
            "--board-url",
            "acme",
            "--collection-date",
            "2026-07-02",
            "--request-delay",
            "1.25",
            "--max-retries",
            "5",
            "--no-resume",
        ],
    )

    assert result.exit_code == 0
    assert client_kwargs == [{"request_delay_seconds": 1.25, "max_retries": 5}]
    assert collection_calls[0]["board_values"] == [
        "https://apply.workable.com/acme"
    ]
    assert collection_calls[0]["collection_date"] == "2026-07-02"
    assert collection_calls[0]["resume"] is False
    assert collection_calls[0]["client"].__class__ is FakeWorkableClient
    normalized_output = " ".join(result.output.split())
    assert (
        "3 board(s), 2 result file(s) available, 1 written, 1 resumed, 1 error(s)."
        in normalized_output
    )


def test_collect_workable_reports_board_file_errors(
    monkeypatch,
    tmp_path: Path,
) -> None:
    boards_path = tmp_path / "invalid.jsonl"
    boards_path.write_text("not valid", encoding="utf-8")

    def fail_read(_: Path) -> list[str]:
        raise ValueError("invalid JSONL record")

    monkeypatch.setattr(cli, "read_ats_board_file", fail_read)

    result = runner.invoke(
        cli.app,
        ["collect-workable", "--boards-file", str(boards_path)],
    )

    assert result.exit_code == 1
    assert "Could not read boards file: invalid JSONL record" in result.output


def test_all_collect_commands_expose_resilience_options() -> None:
    commands = (
        "collect-ashby",
        "collect-greenhouse",
        "collect-lever",
        "collect-personio",
        "collect-recruitee",
        "collect-teamtailor",
        "collect-smartrecruiters",
        "collect-workable",
    )
    options = (
        "--boards-file",
        "--collection-date",
        "--resume",
        "--no-resume",
        "--request-delay",
        "--max-retries",
    )

    for command in commands:
        result = runner.invoke(cli.app, [command, "--help"])
        assert result.exit_code == 0, result.output
        for option in options:
            assert option in result.output


@pytest.mark.parametrize(
    ("command", "client_name", "collector_name"),
    [
        ("collect-ashby", "AshbyClient", "collect_ashby_boards"),
        ("collect-greenhouse", "GreenhouseClient", "collect_greenhouse_boards"),
        ("collect-lever", "LeverClient", "collect_lever_boards"),
        ("collect-personio", "PersonioClient", "collect_personio_boards"),
        ("collect-recruitee", "RecruiteeClient", "collect_recruitee_boards"),
        ("collect-teamtailor", "TeamtailorClient", "collect_teamtailor_boards"),
        (
            "collect-smartrecruiters",
            "SmartRecruitersClient",
            "collect_smartrecruiters_boards",
        ),
        ("collect-workable", "WorkableClient", "collect_workable_boards"),
    ],
)
def test_all_collect_commands_pass_resilience_options(
    monkeypatch,
    command: str,
    client_name: str,
    collector_name: str,
) -> None:
    client_calls: list[dict[str, Any]] = []
    collector_calls: list[dict[str, Any]] = []

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            client_calls.append(kwargs)

        def close(self) -> None:
            pass

    def fake_collect(board_values: list[str], **kwargs: Any) -> SimpleNamespace:
        collector_calls.append({"board_values": list(board_values), **kwargs})
        return SimpleNamespace(
            manifest_path=Path("manifest.json"),
            board_count=1,
            result_files=["result.json"],
            written_count=1,
            resumed_count=0,
            error_count=0,
        )

    monkeypatch.setattr(cli, client_name, FakeClient)
    monkeypatch.setattr(cli, collector_name, fake_collect)
    monkeypatch.setattr(
        cli,
        "require_serper_api_key",
        lambda: (_ for _ in ()).throw(
            AssertionError("explicit board input must not access Serper")
        ),
    )

    result = runner.invoke(
        cli.app,
        [
            command,
            "--board-url",
            "acme",
            "--collection-date",
            "2026-07-02",
            "--request-delay",
            "0.25",
            "--max-retries",
            "2",
            "--no-resume",
        ],
    )

    assert result.exit_code == 0, result.output
    assert client_calls[0]["request_delay_seconds"] == 0.25
    assert client_calls[0]["max_retries"] == 2
    assert collector_calls[0]["collection_date"] == "2026-07-02"
    assert collector_calls[0]["resume"] is False
    assert collector_calls[0]["board_values"]
    assert "1 result file(s) available, 1 written, 0 resumed" in " ".join(
        result.output.split()
    )
