from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from ai_hiring_radar import cli
from ai_hiring_radar.country_inference import CountryInference
from ai_hiring_radar.normalizers.ats import registry
from ai_hiring_radar.normalizers.common.candidate import build_ats_candidate
from ai_hiring_radar.processing import process_collection
from ai_hiring_radar.sources.ashby import ashby_board_from_slug, build_raw_ashby_response_record
from ai_hiring_radar.storage_json import read_jsonl, write_json, write_raw_ats_response


def _ashby_response() -> dict[str, object]:
    return {
        "data": {
            "jobBoard": {
                "teams": [],
                "jobPostings": [
                    {
                        "id": "job-ai-engineer",
                        "title": "AI Engineer",
                        "teamId": None,
                        "locationName": "Netherlands",
                        "workplaceType": "Remote",
                        "employmentType": "FullTime",
                        "secondaryLocations": [],
                        "compensationTierSummary": None,
                    }
                ],
            }
        }
    }


def test_process_normalizes_ats_only_candidates(tmp_path) -> None:
    """(06-normalization-refactor, US-1)"""
    write_raw_ats_response(
        build_raw_ashby_response_record(
            board=ashby_board_from_slug("acme-ai"),
            response=_ashby_response(),
            collected_at="2026-06-16T10:00:01Z",
        ),
        platform_company_slug="acme-ai",
        collection_date="2026-06-16",
        data_dir=tmp_path,
    )
    legacy_search_path = tmp_path / "raw" / "searches" / "2026-06-16" / "serper_google"
    legacy_search_path.mkdir(parents=True)
    write_json(legacy_search_path / "legacy.json", {"organic_results": []})

    result = process_collection("2026-06-16", data_dir=tmp_path)

    assert result.raw_file_count == 1
    assert result.candidate_count == 1
    candidates = read_jsonl(result.job_candidates_path)
    assert candidates[0]["source"] == "ashby"
    assert candidates[0]["company_normalized"] == "Acme Ai"


def test_provider_normalizers_are_isolated_by_provider_folder() -> None:
    """(06-normalization-refactor, US-2)"""
    base = Path("src/ai_hiring_radar/normalizers/ats")
    providers = {
        "ashby",
        "greenhouse",
        "lever",
        "personio",
        "recruitee",
        "smartrecruiters",
        "teamtailor",
        "workable",
    }

    for provider in providers:
        assert (base / provider / "normalizer.py").exists()
    assert not Path("src/ai_hiring_radar/normalize.py").exists()
    assert set(registry.ATS_NORMALIZERS) == providers


def test_candidate_builder_rejects_base_field_conflicts() -> None:
    """(06-normalization-refactor, US-3)"""
    with pytest.raises(ValueError, match="platform_job_id"):
        build_ats_candidate(
            source="ashby",
            metadata={},
            raw_file=Path("raw.json"),
            platform_company_slug="acme-ai",
            platform_job_id="job-ai-engineer",
            board_url="https://jobs.ashbyhq.com/acme-ai",
            source_url="https://jobs.ashbyhq.com/acme-ai",
            job_title_raw="AI Engineer",
            company_raw="Acme AI",
            country_inference=CountryInference(country_codes=[], countries=[]),
            extra_fields={"platform_job_id": "override"},
        )


def test_legacy_linkedin_cli_commands_are_removed() -> None:
    """(06-normalization-refactor, US-4)"""
    runner = CliRunner()

    assert runner.invoke(cli.app, ["collect", "--help"]).exit_code != 0
    assert runner.invoke(cli.app, ["run", "--help"]).exit_code != 0
    assert runner.invoke(cli.app, ["collect-ashby", "--help"]).exit_code == 0


def test_missing_platform_raw_file_falls_back_to_ashby(tmp_path) -> None:
    """(06-normalization-refactor, US-5)"""
    raw_file = tmp_path / "missing-platform.json"
    write_json(
        raw_file,
        {
            "record_type": "raw_ats_response",
            "platform_company_slug": "acme-ai",
            "board_url": "https://jobs.ashbyhq.com/acme-ai",
            "response": _ashby_response(),
        },
    )

    candidates = registry.normalize_raw_ats_file(raw_file)

    assert len(candidates) == 1
    assert candidates[0]["source"] == "ashby"
    assert candidates[0]["platform_job_id"] == "job-ai-engineer"


def test_ats_discovery_commands_still_use_serper_client(monkeypatch) -> None:
    """(06-normalization-refactor, US-6)"""
    created_clients: list[object] = []
    discovered_clients: list[object] = []

    class FakeSerperGoogleClient:
        def __init__(self, *, api_key: str) -> None:
            self.api_key = api_key
            created_clients.append(self)

        def close(self) -> None:
            pass

    def fake_discover_ashby_boards(search_queries, *, client):  # noqa: ANN001
        discovered_clients.append(client)
        return SimpleNamespace(
            board_count=0,
            query_count=len(search_queries),
            error_count=0,
            boards_path=Path("boards.jsonl"),
            manifest_path=Path("manifest.json"),
        )

    monkeypatch.setattr(cli, "require_serper_api_key", lambda: "serper-key")
    monkeypatch.setattr(cli, "SerperGoogleClient", FakeSerperGoogleClient)
    monkeypatch.setattr(cli, "discover_ashby_boards", fake_discover_ashby_boards)

    result = CliRunner().invoke(
        cli.app,
        ["discover-ashby", "--countries", "nl", "--limit", "1"],
    )

    assert result.exit_code == 0
    assert created_clients
    assert discovered_clients == created_clients
