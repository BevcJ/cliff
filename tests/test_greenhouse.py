from pathlib import Path
from typing import Any

import httpx

from ai_hiring_radar.config import load_countries_config
from ai_hiring_radar.normalize import normalize_raw_ats_file, process_collection
from ai_hiring_radar.query_builder import LocationDepth
from ai_hiring_radar.sources.ats_discovery import AtsDiscoveryDepth
from ai_hiring_radar.sources.greenhouse import (
    GreenhouseClient,
    build_raw_greenhouse_response_record,
    collect_greenhouse_boards,
    discover_greenhouse_boards,
    generate_greenhouse_discovery_queries,
    greenhouse_board_from_slug,
    parse_greenhouse_board_url,
)
from ai_hiring_radar.storage_json import read_json, read_jsonl, write_raw_ats_response


class FakeSearchClient:
    def __init__(self, responses: list[dict[str, Any] | Exception]) -> None:
        self.responses = responses
        self.searches = []

    def search(self, search_query):  # noqa: ANN001
        self.searches.append(search_query)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeGreenhouseClient:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.fetched_boards: list[str] = []

    def fetch_board(self, board_url_or_slug: str) -> dict[str, Any]:
        self.fetched_boards.append(board_url_or_slug)
        return self.response


def _sample_greenhouse_response() -> dict[str, Any]:
    return {
        "jobs": [
            {
                "id": 7995153,
                "title": "Senior AI Engineer",
                "updated_at": "2026-06-16T00:00:00Z",
                "location": {"name": "Amsterdam, Netherlands"},
                "absolute_url": "https://boards.greenhouse.io/acme-ai/jobs/7995153",
                "content": "<p>Build AI systems.</p>",
                "departments": [{"name": "Engineering"}],
                "offices": [
                    {"name": "Amsterdam", "location": "Amsterdam, Netherlands"}
                ],
            },
            {
                "id": 7995154,
                "title": "Backend Engineer",
                "updated_at": "2026-06-16T00:00:00Z",
                "location": {"name": "Amsterdam, Netherlands"},
                "absolute_url": "https://boards.greenhouse.io/acme-ai/jobs/7995154",
                "content": "<p>Build services.</p>",
                "departments": [{"name": "Engineering"}],
                "offices": [],
            },
            {
                "id": 7995155,
                "title": "AI Product Manager",
                "updated_at": "2026-06-16T00:00:00Z",
                "location": {"name": "Remote - Netherlands"},
                "absolute_url": "https://boards.greenhouse.io/acme-ai/jobs/7995155",
                "content": "<p>Shape AI products.</p>",
                "departments": [{"name": "Product"}],
                "offices": [{"location": {"name": "Netherlands"}}],
            },
        ],
        "meta": {"total": 3},
    }


def test_parse_greenhouse_board_url_extracts_first_path_segment() -> None:
    board = parse_greenhouse_board_url("https://boards.greenhouse.io/acme/jobs/123")

    assert board is not None
    assert board.platform_company_slug == "acme"
    assert board.board_url == "https://boards.greenhouse.io/acme"
    assert parse_greenhouse_board_url("https://boards.greenhouse.io/embed/job_board") is None
    assert parse_greenhouse_board_url("https://boards-api.greenhouse.io/v1/boards/acme") is None
    assert parse_greenhouse_board_url("https://example.com/acme") is None


def test_discover_greenhouse_boards_writes_deduped_board_records(tmp_path) -> None:
    query = generate_greenhouse_discovery_queries(
        countries_config=load_countries_config(),
        country_codes=["nl"],
    )[0]
    client = FakeSearchClient(
        [
            {
                "organic_results": [
                    {
                        "position": 1,
                        "title": "Acme jobs",
                        "link": "https://boards.greenhouse.io/acme/jobs/123",
                        "snippet": "Acme is hiring in Amsterdam.",
                    },
                    {
                        "position": 2,
                        "title": "Acme careers",
                        "link": "https://boards.greenhouse.io/acme",
                    },
                    {
                        "position": 3,
                        "title": "Other result",
                        "link": "https://example.com/jobs",
                    },
                ]
            }
        ]
    )
    timestamps = iter(
        [
            "2026-06-16T10:00:00Z",
            "2026-06-16T10:00:01Z",
            "2026-06-16T10:00:02Z",
        ]
    )

    result = discover_greenhouse_boards(
        [query],
        client=client,
        data_dir=tmp_path,
        clock=lambda: next(timestamps),
    )

    assert result.query_count == 1
    assert result.board_count == 1
    boards = read_jsonl(result.boards_path)
    assert boards[0]["record_type"] == "ats_company_board"
    assert boards[0]["platform"] == "greenhouse"
    assert boards[0]["platform_company_slug"] == "acme"
    assert boards[0]["board_url"] == "https://boards.greenhouse.io/acme"

    manifest = read_json(result.manifest_path)
    assert manifest["platform"] == "greenhouse"
    assert manifest["board_count"] == 1
    assert manifest["boards_file"] == result.boards_path.as_posix()
    assert manifest["query_types"] == ["site_only"]
    assert manifest["pages"] == [1]


def test_generate_greenhouse_discovery_queries_uses_shared_exhaustive_depth() -> None:
    queries = generate_greenhouse_discovery_queries(
        countries_config=load_countries_config(),
        country_codes=["nl"],
        role_terms=["AI Engineer"],
        signal_terms=["LLM"],
        pages=1,
        location_depth=LocationDepth.CITIES,
        discovery_depth=AtsDiscoveryDepth.EXHAUSTIVE,
    )

    query_types = {query.discovery_query_type for query in queries}
    assert "role_location" in query_types
    assert "ai_signal_location" in query_types
    assert any(
        query.search_query == 'site:boards.greenhouse.io "AI Engineer" "Amsterdam"'
        for query in queries
    )


def test_greenhouse_client_gets_public_jobs_endpoint() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "GET"
        assert str(request.url) == (
            "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true"
        )
        assert "greenhouse" in request.headers["User-Agent"]
        return httpx.Response(200, json={"jobs": [], "meta": {"total": 0}})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as http_client:
        client = GreenhouseClient(http_client=http_client)
        payload = client.fetch_board("https://boards.greenhouse.io/acme")

    assert len(requests) == 1
    assert payload == {"jobs": [], "meta": {"total": 0}}


def test_collect_greenhouse_boards_writes_raw_response_and_manifest(tmp_path) -> None:
    client = FakeGreenhouseClient(_sample_greenhouse_response())
    timestamps = iter(
        [
            "2026-06-16T10:00:00Z",
            "2026-06-16T10:00:01Z",
            "2026-06-16T10:00:02Z",
        ]
    )

    result = collect_greenhouse_boards(
        ["https://boards.greenhouse.io/acme-ai"],
        client=client,  # type: ignore[arg-type]
        data_dir=tmp_path,
        clock=lambda: next(timestamps),
    )

    assert result.successful_count == 1
    assert result.board_count == 1
    assert result.error_count == 0
    raw_record = read_json(Path(result.result_files[0]))
    assert raw_record["record_type"] == "raw_ats_response"
    assert raw_record["platform"] == "greenhouse"
    assert raw_record["platform_company_slug"] == "acme-ai"
    assert raw_record["request_params"] == {"content": "true"}
    assert raw_record["endpoint"] == (
        "https://boards-api.greenhouse.io/v1/boards/acme-ai/jobs?content=true"
    )
    assert read_json(result.manifest_path)["result_files"] == result.result_files


def test_normalize_raw_greenhouse_file_keeps_title_ai_signals_only(tmp_path) -> None:
    board = greenhouse_board_from_slug("acme-ai")
    raw_record = build_raw_greenhouse_response_record(
        board=board,
        response=_sample_greenhouse_response(),
        collected_at="2026-06-16T10:00:01Z",
    )
    raw_path = write_raw_ats_response(
        raw_record,
        platform_company_slug="acme-ai",
        collection_date="2026-06-16",
        data_dir=tmp_path,
        platform="greenhouse",
    )

    candidates = normalize_raw_ats_file(raw_path)

    assert [candidate["job_title_raw"] for candidate in candidates] == [
        "Senior AI Engineer",
        "AI Product Manager",
    ]
    assert candidates[0]["source"] == "greenhouse"
    assert candidates[0]["source_mode"] == "public_job_board_endpoint"
    assert candidates[0]["source_url"] == (
        "https://boards.greenhouse.io/acme-ai/jobs/7995153"
    )
    assert candidates[0]["board_url"] == "https://boards.greenhouse.io/acme-ai"
    assert candidates[0]["platform_company_slug"] == "acme-ai"
    assert candidates[0]["platform_job_id"] == "7995153"
    assert candidates[0]["company_normalized"] == "Acme Ai"
    assert candidates[0]["job_title_normalized"] == "AI Engineer"
    assert candidates[0]["role_group"] == "AI Execution Role"
    assert candidates[0]["team"] == "Engineering"
    assert candidates[0]["teams"] == ["Engineering"]
    assert candidates[0]["offices"] == ["Amsterdam, Netherlands"]
    assert candidates[0]["country"] == "Netherlands"
    assert candidates[0]["country_code"] == "nl"
    assert candidates[0]["job_countries"] == ["Netherlands"]
    assert candidates[0]["job_country_codes"] == ["nl"]
    assert candidates[0]["job_locations_raw"] == [
        "Amsterdam, Netherlands",
    ]
    assert candidates[0]["description"] == "<p>Build AI systems.</p>"
    assert candidates[0]["source_updated_at"] == "2026-06-16T00:00:00Z"
    assert candidates[0]["evidence_quality"] == "title_only_ats_listing"
    assert candidates[1]["role_group"] == "AI Product Role"
    assert candidates[1]["job_countries"] == ["Netherlands"]


def test_normalize_greenhouse_prefers_office_country_over_remote_location(
    tmp_path,
) -> None:
    board = greenhouse_board_from_slug("acme-ai")
    raw_record = build_raw_greenhouse_response_record(
        board=board,
        response={
            "jobs": [
                {
                    "id": 7995156,
                    "title": "AI Engineer - FDE",
                    "updated_at": "2026-06-16T00:00:00Z",
                    "location": {"name": "Remote - Netherlands"},
                    "absolute_url": "https://boards.greenhouse.io/acme-ai/jobs/7995156",
                    "content": "<p>Build AI systems.</p>",
                    "departments": [{"name": "Engineering"}],
                    "offices": [
                        {"name": "Bavaria", "location": "Bavaria, Germany"}
                    ],
                }
            ],
            "meta": {"total": 1},
        },
        collected_at="2026-06-16T10:00:01Z",
    )
    raw_path = write_raw_ats_response(
        raw_record,
        platform_company_slug="acme-ai",
        collection_date="2026-06-16",
        data_dir=tmp_path,
        platform="greenhouse",
    )

    candidates = normalize_raw_ats_file(raw_path)

    assert len(candidates) == 1
    assert candidates[0]["location"] == "Remote - Netherlands"
    assert candidates[0]["offices"] == ["Bavaria, Germany"]
    assert candidates[0]["country"] == "Germany"
    assert candidates[0]["country_code"] == "de"
    assert candidates[0]["job_countries"] == ["Germany"]
    assert candidates[0]["job_country_codes"] == ["de"]


def test_process_collection_includes_greenhouse_raw_files(tmp_path) -> None:
    board = greenhouse_board_from_slug("acme-ai")
    raw_record = build_raw_greenhouse_response_record(
        board=board,
        response=_sample_greenhouse_response(),
        collected_at="2026-06-16T10:00:01Z",
    )
    write_raw_ats_response(
        raw_record,
        platform_company_slug="acme-ai",
        collection_date="2026-06-16",
        data_dir=tmp_path,
        platform="greenhouse",
    )

    result = process_collection("2026-06-16", data_dir=tmp_path)

    assert result.raw_file_count == 1
    assert result.candidate_count == 2
    assert result.deduped_candidate_count == 2
    assert result.company_count == 1

    candidates = read_jsonl(result.job_candidates_path)
    assert candidates[0]["source"] == "greenhouse"
    assert candidates[0]["source_url"] == (
        "https://boards.greenhouse.io/acme-ai/jobs/7995153"
    )

    companies = read_jsonl(result.companies_path)
    assert companies[0]["company"] == "Acme Ai"
    assert companies[0]["countries"] == ["Netherlands"]
    assert companies[0]["sources"] == ["greenhouse"]
    assert companies[0]["matched_search_terms"] == [
        "AI Engineer",
        "AI Product Manager",
    ]
