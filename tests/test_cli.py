from __future__ import annotations

from dataclasses import replace
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
from ai_hiring_radar.sources.ats_providers import (
    AtsClientOptions,
    AtsProvider,
    AtsProviderSpec,
    get_ats_provider_spec,
)


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


def _install_cli_spec(
    monkeypatch,
    provider: AtsProvider,
    **changes: Any,
) -> AtsProviderSpec:
    spec = replace(get_ats_provider_spec(provider), **changes)

    def fake_get_spec(selected_provider: AtsProvider) -> AtsProviderSpec:
        assert selected_provider is provider
        return spec

    monkeypatch.setattr(cli, "get_ats_provider_spec", fake_get_spec)
    return spec


def _fake_discovery_query(provider: AtsProvider) -> SimpleNamespace:
    return SimpleNamespace(
        country_code="nl",
        search_location_label="Netherlands",
        discovery_query_type="site_only",
        page=1,
        search_query=f"site:{provider.value}.example",
    )


def _fake_discovery_result(
    *,
    boards: list[dict[str, str]] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        manifest_path=Path("discovery-manifest.json"),
        boards_path=Path("boards.jsonl"),
        query_count=2,
        boards=boards or [],
        board_count=len(boards or []),
        errors=[{"error": "one failed query"}],
        error_count=1,
    )


def _fake_collection_result() -> SimpleNamespace:
    return SimpleNamespace(
        manifest_path=Path("collection-manifest.json"),
        board_count=3,
        result_files=["written.json", "resumed.json"],
        written_count=1,
        resumed_count=1,
        error_count=1,
    )


def test_ats_help_exposes_only_discover_and_collect() -> None:
    ats_help = runner.invoke(cli.app, ["ats", "--help"])
    discover_help = runner.invoke(cli.app, ["ats", "discover", "--help"])
    collect_help = runner.invoke(cli.app, ["ats", "collect", "--help"])

    assert ats_help.exit_code == 0, ats_help.output
    assert "discover" in ats_help.output
    assert "collect" in ats_help.output
    assert "PROVIDER:{ashby|greenhouse|lever|personio" in discover_help.output
    assert "PROVIDER:{ashby|greenhouse|lever|personio" in collect_help.output
    for option in (
        "--countries",
        "--limit",
        "--dry-run",
        "--location-depth",
        "--discovery-depth",
        "--results-per-query",
        "--pages",
    ):
        assert option in discover_help.output
        assert option in collect_help.output
    for option in (
        "--board-url",
        "--boards-file",
        "--collection-date",
        "--resume",
        "--no-resume",
        "--request-delay",
        "--max-retries",
        "--language",
    ):
        assert option in collect_help.output
    normalized_collect_help = " ".join(collect_help.output.split())
    assert "Defaults to the" in normalized_collect_help
    assert "setting (currently" in normalized_collect_help
    assert "Personio feed" in normalized_collect_help
    assert "ignored by other" in normalized_collect_help


@pytest.mark.parametrize(
    "command",
    [
        f"{operation}-{provider.value}"
        for operation in ("discover", "collect")
        for provider in AtsProvider
    ],
)
def test_old_ats_commands_are_absent(command: str) -> None:
    result = runner.invoke(cli.app, [command, "--help"])

    assert result.exit_code != 0
    assert f"No such command '{command}'" in result.output


def test_debug_ashby_discovery_command_remains_registered() -> None:
    result = runner.invoke(cli.app, ["debug-ashby-discovery", "--help"])

    assert result.exit_code == 0, result.output
    assert "Ashby discovery error summary" in result.output


def test_ats_rejects_unknown_provider() -> None:
    result = runner.invoke(cli.app, ["ats", "discover", "unknown", "--dry-run"])

    assert result.exit_code != 0
    assert "Invalid value for" in result.output
    assert "unknown" in result.output


@pytest.mark.parametrize("provider", list(AtsProvider))
def test_ats_discover_dry_run_dispatches_every_provider(
    monkeypatch,
    provider: AtsProvider,
) -> None:
    generated: list[dict[str, Any]] = []
    real_spec = get_ats_provider_spec(provider)

    def fake_generate(**kwargs: Any) -> list[SimpleNamespace]:
        generated.append(kwargs)
        return [_fake_discovery_query(provider)]

    _install_cli_spec(
        monkeypatch,
        provider,
        generate_discovery_queries=fake_generate,
    )
    monkeypatch.setattr(
        cli,
        "require_serper_api_key",
        lambda: pytest.fail("dry-run discovery must not access Serper"),
    )

    result = runner.invoke(
        cli.app,
        [
            "ats",
            "discover",
            provider.value,
            "--countries",
            "nl",
            "--limit",
            "1",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.output
    assert generated[0]["country_codes"] == ["nl"]
    assert generated[0]["limit"] == 1
    assert generated[0]["num"] == real_spec.default_results_per_query
    assert generated[0]["pages"] == real_spec.default_pages
    assert generated[0]["location_depth"] is cli.LocationDepth.CITIES
    assert generated[0]["discovery_depth"] is cli.AtsDiscoveryDepth.EXHAUSTIVE
    assert generated[0]["role_terms"] == cli.load_taxonomy_config().all_roles
    assert f"Generated 1 {real_spec.display_name} discovery queries." in result.output


@pytest.mark.parametrize("provider", list(AtsProvider))
def test_ats_collect_dispatches_every_provider(
    monkeypatch,
    provider: AtsProvider,
) -> None:
    options_seen: list[AtsClientOptions] = []
    collection_calls: list[dict[str, Any]] = []
    clients: list[SimpleNamespace] = []

    def fake_make_client(options: AtsClientOptions) -> SimpleNamespace:
        options_seen.append(options)
        client = SimpleNamespace(closed=False)

        def close() -> None:
            client.closed = True

        client.close = close
        clients.append(client)
        return client

    def fake_collect(board_values: list[str], **kwargs: Any) -> SimpleNamespace:
        collection_calls.append({"board_values": list(board_values), **kwargs})
        return _fake_collection_result()

    spec = _install_cli_spec(
        monkeypatch,
        provider,
        make_client=fake_make_client,
        collect_boards=fake_collect,
    )
    monkeypatch.setattr(
        cli,
        "require_serper_api_key",
        lambda: pytest.fail("explicit board input must not access Serper"),
    )

    result = runner.invoke(
        cli.app,
        ["ats", "collect", provider.value, "--board-url", "acme"],
    )

    assert result.exit_code == 0, result.output
    assert options_seen == [
        AtsClientOptions(request_delay_seconds=0.5, max_retries=3, language=None)
    ]
    assert collection_calls[0]["board_values"] == [
        spec.normalize_board("acme").board_url
    ]
    assert collection_calls[0]["collection_date"] is None
    assert collection_calls[0]["resume"] is True
    assert collection_calls[0]["client"] is clients[0]
    assert clients[0].closed is True
    assert f"{spec.display_name} collection complete" in result.output


def test_ats_discover_uses_provider_defaults_and_validates_maximum(
    monkeypatch,
) -> None:
    generated: list[dict[str, Any]] = []

    def fake_generate(**kwargs: Any) -> list[SimpleNamespace]:
        generated.append(kwargs)
        return [_fake_discovery_query(AtsProvider.WORKABLE)]

    _install_cli_spec(
        monkeypatch,
        AtsProvider.WORKABLE,
        generate_discovery_queries=fake_generate,
        default_results_per_query=4,
        max_results_per_query=5,
        default_pages=3,
    )

    default_result = runner.invoke(
        cli.app,
        ["ats", "discover", "workable", "--countries", "nl", "--dry-run"],
    )
    invalid_result = runner.invoke(
        cli.app,
        [
            "ats",
            "discover",
            "workable",
            "--results-per-query",
            "6",
            "--dry-run",
        ],
    )

    assert default_result.exit_code == 0, default_result.output
    assert generated[0]["num"] == 4
    assert generated[0]["pages"] == 3
    assert invalid_result.exit_code != 0
    normalized_error = " ".join(invalid_result.output.split())
    assert "Workable accepts at most 5" in normalized_error
    assert "per query." in normalized_error
    assert len(generated) == 1


def test_ats_discover_passes_explicit_discovery_options(monkeypatch) -> None:
    generated: list[dict[str, Any]] = []

    def fake_generate(**kwargs: Any) -> list[SimpleNamespace]:
        generated.append(kwargs)
        return [_fake_discovery_query(AtsProvider.GREENHOUSE)]

    _install_cli_spec(
        monkeypatch,
        AtsProvider.GREENHOUSE,
        generate_discovery_queries=fake_generate,
    )

    result = runner.invoke(
        cli.app,
        [
            "ats",
            "discover",
            "greenhouse",
            "--countries",
            "nl,dk",
            "--limit",
            "2",
            "--location-depth",
            "country",
            "--discovery-depth",
            "broad",
            "--results-per-query",
            "4",
            "--pages",
            "5",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.output
    assert generated[0]["country_codes"] == ["nl", "dk"]
    assert generated[0]["limit"] == 2
    assert generated[0]["location_depth"] is cli.LocationDepth.COUNTRY
    assert generated[0]["discovery_depth"] is cli.AtsDiscoveryDepth.BROAD
    assert generated[0]["num"] == 4
    assert generated[0]["pages"] == 5


def test_ats_discover_calls_registry_and_reports_counts(monkeypatch) -> None:
    discovery_calls: list[dict[str, Any]] = []
    search_clients: list[SimpleNamespace] = []

    def fake_generate(**_: Any) -> list[SimpleNamespace]:
        return [_fake_discovery_query(AtsProvider.ASHBY)]

    def fake_discover(queries: list[SimpleNamespace], **kwargs: Any) -> SimpleNamespace:
        discovery_calls.append({"queries": queries, **kwargs})
        return _fake_discovery_result(
            boards=[{"board_url": "https://jobs.ashbyhq.com/acme"}]
        )

    def fake_search_client(*, api_key: str) -> SimpleNamespace:
        client = SimpleNamespace(api_key=api_key, closed=False)

        def close() -> None:
            client.closed = True

        client.close = close
        search_clients.append(client)
        return client

    _install_cli_spec(
        monkeypatch,
        AtsProvider.ASHBY,
        generate_discovery_queries=fake_generate,
        discover_boards=fake_discover,
    )
    monkeypatch.setattr(cli, "require_serper_api_key", lambda: "serper-key")
    monkeypatch.setattr(cli, "SerperGoogleClient", fake_search_client)

    result = runner.invoke(
        cli.app,
        ["ats", "discover", "ashby", "--countries", "nl"],
    )

    assert result.exit_code == 0, result.output
    assert discovery_calls[0]["client"] is search_clients[0]
    assert search_clients[0].api_key == "serper-key"
    assert search_clients[0].closed is True
    normalized_output = " ".join(result.output.split())
    assert "1 board(s), 2 querie(s), 1 error(s)." in normalized_output
    assert "Boards: boards.jsonl" in normalized_output
    assert "Manifest: discovery-manifest.json" in normalized_output


@pytest.mark.parametrize(
    ("provider", "filename", "contents", "expected_urls"),
    [
        (
            AtsProvider.GREENHOUSE,
            "boards.jsonl",
            '{"board_url": "https://boards.greenhouse.io/acme/jobs/1"}\n'
            '{"board_url": "beta"}\n',
            [
                "https://boards.greenhouse.io/acme",
                "https://boards.greenhouse.io/beta",
            ],
        ),
        (
            AtsProvider.TEAMTAILOR,
            "boards.txt",
            "acme\nhttps://beta.teamtailor.com/jobs/123\n",
            ["https://acme.teamtailor.com", "https://beta.teamtailor.com"],
        ),
    ],
)
def test_ats_collect_reads_jsonl_and_plain_text_files(
    monkeypatch,
    tmp_path: Path,
    provider: AtsProvider,
    filename: str,
    contents: str,
    expected_urls: list[str],
) -> None:
    boards_path = tmp_path / filename
    boards_path.write_text(contents, encoding="utf-8")
    monkeypatch.setattr(
        cli,
        "require_serper_api_key",
        lambda: pytest.fail("explicit files must not access Serper"),
    )

    result = runner.invoke(
        cli.app,
        [
            "ats",
            "collect",
            provider.value,
            "--boards-file",
            str(boards_path),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.output
    for expected_url in expected_urls:
        assert expected_url in result.output


def test_ats_collect_combines_and_dedupes_explicit_inputs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    boards_path = tmp_path / "boards.txt"
    boards_path.write_text(
        "https://apply.workable.com/ACME/jobs\nbeta\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        cli,
        "require_serper_api_key",
        lambda: pytest.fail("explicit inputs must not access Serper"),
    )

    result = runner.invoke(
        cli.app,
        [
            "ats",
            "collect",
            "workable",
            "--board-url",
            "acme",
            "--board-url",
            "gamma",
            "--boards-file",
            str(boards_path),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Normalized 3 Workable board URL(s)." in result.output
    assert result.output.count("https://apply.workable.com/acme") == 1
    assert result.output.index("https://apply.workable.com/acme") < result.output.index(
        "https://apply.workable.com/gamma"
    )
    assert result.output.index("https://apply.workable.com/gamma") < result.output.index(
        "https://apply.workable.com/beta"
    )


def test_ats_collect_empty_file_skips_discovery_serper_and_client(
    monkeypatch,
    tmp_path: Path,
) -> None:
    boards_path = tmp_path / "empty.txt"
    boards_path.write_text("", encoding="utf-8")

    def fail(*_: Any, **__: Any) -> None:
        raise AssertionError("empty explicit files must skip discovery and clients")

    _install_cli_spec(
        monkeypatch,
        AtsProvider.WORKABLE,
        generate_discovery_queries=fail,
        discover_boards=fail,
        make_client=fail,
    )
    monkeypatch.setattr(cli, "require_serper_api_key", fail)

    result = runner.invoke(
        cli.app,
        ["ats", "collect", "workable", "--boards-file", str(boards_path)],
    )

    assert result.exit_code == 0, result.output
    assert "No Workable boards to collect." in result.output


@pytest.mark.parametrize("invalid_date", ["not-a-date", "20260702", "2026-W27-4"])
def test_ats_collect_rejects_non_strict_collection_dates(invalid_date: str) -> None:
    result = runner.invoke(
        cli.app,
        [
            "ats",
            "collect",
            "workable",
            "--board-url",
            "acme",
            "--collection-date",
            invalid_date,
            "--dry-run",
        ],
    )

    assert result.exit_code != 0
    assert "Date must use YYYY-MM-DD format" in result.output


def test_ats_collect_passes_options_and_reports_counts(monkeypatch) -> None:
    options_seen: list[AtsClientOptions] = []
    collection_calls: list[dict[str, Any]] = []
    client = SimpleNamespace(closed=False)

    def close() -> None:
        client.closed = True

    client.close = close

    def fake_make_client(options: AtsClientOptions) -> SimpleNamespace:
        options_seen.append(options)
        return client

    def fake_collect(board_values: list[str], **kwargs: Any) -> SimpleNamespace:
        collection_calls.append({"board_values": list(board_values), **kwargs})
        return _fake_collection_result()

    _install_cli_spec(
        monkeypatch,
        AtsProvider.WORKABLE,
        make_client=fake_make_client,
        collect_boards=fake_collect,
    )

    result = runner.invoke(
        cli.app,
        [
            "ats",
            "collect",
            "workable",
            "--board-url",
            "acme",
            "--collection-date",
            "2026-07-02",
            "--request-delay",
            "1.25",
            "--max-retries",
            "5",
            "--language",
            "de",
            "--no-resume",
        ],
    )

    assert result.exit_code == 0, result.output
    assert options_seen == [
        AtsClientOptions(request_delay_seconds=1.25, max_retries=5, language="de")
    ]
    assert collection_calls[0]["collection_date"] == "2026-07-02"
    assert collection_calls[0]["resume"] is False
    assert collection_calls[0]["client"] is client
    assert client.closed is True
    normalized_output = " ".join(result.output.split())
    assert (
        "3 board(s), 2 result file(s) available, 1 written, 1 resumed, 1 error(s)."
        in normalized_output
    )
    assert "Manifest: collection-manifest.json" in normalized_output


@pytest.mark.parametrize(
    ("provider", "expected_language"),
    [
        (AtsProvider.PERSONIO, "de"),
        (AtsProvider.WORKABLE, None),
    ],
)
def test_ats_collect_language_is_used_by_personio_and_ignored_by_other_factory(
    monkeypatch,
    provider: AtsProvider,
    expected_language: str | None,
) -> None:
    observed_languages: list[str | None] = []

    def fake_collect(board_values: list[str], **kwargs: Any) -> SimpleNamespace:
        observed_languages.append(getattr(kwargs["client"], "language", None))
        return _fake_collection_result()

    _install_cli_spec(
        monkeypatch,
        provider,
        collect_boards=fake_collect,
    )

    result = runner.invoke(
        cli.app,
        [
            "ats",
            "collect",
            provider.value,
            "--board-url",
            "acme",
            "--language",
            "de",
            "--request-delay",
            "0",
        ],
    )

    assert result.exit_code == 0, result.output
    assert observed_languages == [expected_language]


def test_ats_collect_discovers_then_collects_board_urls(monkeypatch) -> None:
    collected_values: list[str] = []
    search_client = SimpleNamespace(closed=False)
    provider_client = SimpleNamespace(closed=False)

    def close_search_client() -> None:
        search_client.closed = True

    def close_provider_client() -> None:
        provider_client.closed = True

    search_client.close = close_search_client
    provider_client.close = close_provider_client

    def fake_generate(**_: Any) -> list[SimpleNamespace]:
        return [_fake_discovery_query(AtsProvider.GREENHOUSE)]

    def fake_discover(*_: Any, **__: Any) -> SimpleNamespace:
        return _fake_discovery_result(
            boards=[
                {"board_url": "https://boards.greenhouse.io/acme"},
                {"board_url": "https://boards.greenhouse.io/beta"},
            ]
        )

    def fake_collect(board_values: list[str], **_: Any) -> SimpleNamespace:
        collected_values.extend(board_values)
        return _fake_collection_result()

    _install_cli_spec(
        monkeypatch,
        AtsProvider.GREENHOUSE,
        generate_discovery_queries=fake_generate,
        discover_boards=fake_discover,
        make_client=lambda options: provider_client,
        collect_boards=fake_collect,
    )
    monkeypatch.setattr(cli, "require_serper_api_key", lambda: "serper-key")
    monkeypatch.setattr(
        cli,
        "SerperGoogleClient",
        lambda *, api_key: search_client,
    )

    result = runner.invoke(
        cli.app,
        ["ats", "collect", "greenhouse", "--countries", "nl"],
    )

    assert result.exit_code == 0, result.output
    assert collected_values == [
        "https://boards.greenhouse.io/acme",
        "https://boards.greenhouse.io/beta",
    ]
    assert search_client.closed is True
    assert provider_client.closed is True
    assert "Greenhouse discovery complete" in result.output
    assert "Greenhouse collection complete" in result.output


def test_ats_collect_reports_board_file_errors(monkeypatch, tmp_path: Path) -> None:
    boards_path = tmp_path / "invalid.jsonl"
    boards_path.write_text("not valid", encoding="utf-8")

    def fail_read(_: Path) -> list[str]:
        raise ValueError("invalid JSONL record")

    monkeypatch.setattr(cli, "read_ats_board_file", fail_read)

    result = runner.invoke(
        cli.app,
        ["ats", "collect", "workable", "--boards-file", str(boards_path)],
    )

    assert result.exit_code == 1
    assert "Could not read boards file: invalid JSONL record" in result.output
