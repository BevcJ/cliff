from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
from typer.testing import CliRunner

from ai_hiring_radar import cli
from ai_hiring_radar.sources.collection_resilience import (
    is_valid_raw_ats_resume_file,
)
from ai_hiring_radar.sources.greenhouse import (
    GreenhouseClient,
    build_raw_greenhouse_response_record,
    collect_greenhouse_boards,
    greenhouse_board_from_slug,
)
from ai_hiring_radar.storage_json import read_json, write_raw_ats_response


runner = CliRunner()


class FakeGreenhouseClient:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.fetched_boards: list[str] = []

    def fetch_board(self, board_url_or_slug: str) -> dict[str, Any]:
        self.fetched_boards.append(board_url_or_slug)
        return self.response


def _greenhouse_response() -> dict[str, Any]:
    return {"jobs": [], "meta": {"total": 0}}


def _fail_discovery(*_: Any, **__: Any) -> None:
    raise AssertionError("explicit board collection must not touch Serper or discovery")


def test_us_1_operator_collects_discovery_jsonl_without_serper(
    monkeypatch,
    tmp_path: Path,
) -> None:
    boards_path = tmp_path / "boards.jsonl"
    boards_path.write_text(
        '{"record_type":"ats_company_board","platform":"greenhouse",'
        '"platform_company_slug":"acme","board_url":'
        '"https://boards.greenhouse.io/acme/jobs/123"}\n'
        '{"record_type":"ats_company_board","platform":"greenhouse",'
        '"platform_company_slug":"beta","board_url":"beta"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "require_serper_api_key", _fail_discovery)

    result = runner.invoke(
        cli.app,
        [
            "ats",
            "collect",
            "greenhouse",
            "--boards-file",
            str(boards_path),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Normalized 2 Greenhouse board URL(s)." in result.output
    assert "https://boards.greenhouse.io/acme" in result.output
    assert "https://boards.greenhouse.io/beta" in result.output


def test_us_2_resume_skips_valid_raw_and_fetches_missing_in_board_order(
    tmp_path: Path,
) -> None:
    collection_date = "2026-07-08"
    resumed_path = write_raw_ats_response(
        build_raw_greenhouse_response_record(
            board=greenhouse_board_from_slug("existing"),
            response=_greenhouse_response(),
            collected_at="2026-07-08T08:00:00Z",
        ),
        platform_company_slug="existing",
        collection_date=collection_date,
        data_dir=tmp_path,
        platform="greenhouse",
    )
    client = FakeGreenhouseClient(_greenhouse_response())
    timestamps = iter(
        [
            "2026-07-08T09:00:00Z",
            "2026-07-08T09:00:01Z",
            "2026-07-08T09:00:02Z",
        ]
    )

    result = collect_greenhouse_boards(
        ["existing", "missing"],
        client=client,  # type: ignore[arg-type]
        data_dir=tmp_path,
        clock=lambda: next(timestamps),
        collection_date=collection_date,
        resume=True,
    )

    assert client.fetched_boards == ["https://boards.greenhouse.io/missing"]
    assert result.resumed_files == [resumed_path.as_posix()]
    assert [Path(path).stem for path in result.written_files] == ["missing"]
    assert result.result_files == [resumed_path.as_posix(), result.written_files[0]]


def test_us_3_plain_text_boards_file_prints_normalized_boards_without_discovery(
    monkeypatch,
    tmp_path: Path,
) -> None:
    boards_path = tmp_path / "boards.txt"
    boards_path.write_text(
        "acme\nhttps://boards.greenhouse.io/beta/jobs/456\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "require_serper_api_key", _fail_discovery)

    result = runner.invoke(
        cli.app,
        [
            "ats",
            "collect",
            "greenhouse",
            "--boards-file",
            str(boards_path),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Normalized 2 Greenhouse board URL(s)." in result.output
    assert "https://boards.greenhouse.io/acme" in result.output
    assert "https://boards.greenhouse.io/beta" in result.output


def test_us_4_greenhouse_client_retries_transient_response_and_succeeds() -> None:
    requests: list[httpx.Request] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(429, headers={"Retry-After": "2"})
        return httpx.Response(200, json=_greenhouse_response())

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = GreenhouseClient(
            http_client=http_client,
            request_delay_seconds=0,
            max_retries=1,
            sleeper=sleeps.append,
        )
        payload = client.fetch_board("acme")

    assert payload == _greenhouse_response()
    assert len(requests) == 2
    assert sleeps == [2.0]


def test_us_5_mismatched_resume_candidate_is_refetched_and_replaced(
    tmp_path: Path,
) -> None:
    collection_date = "2026-07-08"
    candidate_path = write_raw_ats_response(
        build_raw_greenhouse_response_record(
            board=greenhouse_board_from_slug("wrong-company"),
            response={"jobs": [{"id": "stale"}]},
            collected_at="2026-07-08T08:00:00Z",
        ),
        platform_company_slug="expected-company",
        collection_date=collection_date,
        data_dir=tmp_path,
        platform="greenhouse",
    )
    client = FakeGreenhouseClient(_greenhouse_response())
    timestamps = iter(
        [
            "2026-07-08T09:00:00Z",
            "2026-07-08T09:00:01Z",
            "2026-07-08T09:00:02Z",
        ]
    )

    result = collect_greenhouse_boards(
        ["expected-company"],
        client=client,  # type: ignore[arg-type]
        data_dir=tmp_path,
        clock=lambda: next(timestamps),
        collection_date=collection_date,
        resume=True,
    )

    assert client.fetched_boards == ["https://boards.greenhouse.io/expected-company"]
    assert result.result_files == [candidate_path.as_posix()]
    assert result.written_files == [candidate_path.as_posix()]
    assert result.resumed_files == []
    replaced = read_json(candidate_path)
    assert replaced["record_type"] == "raw_ats_response"
    assert replaced["platform"] == "greenhouse"
    assert replaced["platform_company_slug"] == "expected-company"
    assert replaced["board_url"] == "https://boards.greenhouse.io/expected-company"
    assert replaced["collected_at"] == "2026-07-08T09:00:01Z"
    assert is_valid_raw_ats_resume_file(
        candidate_path,
        platform="greenhouse",
        platform_company_slug="expected-company",
    )
