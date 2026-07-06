from pathlib import Path
from typing import Any

import httpx

from ai_hiring_radar.config import load_countries_config
from ai_hiring_radar.normalize import normalize_raw_ats_file, process_collection
from ai_hiring_radar.query_builder import LocationDepth
from ai_hiring_radar.sources.ats_discovery import AtsDiscoveryDepth
from ai_hiring_radar.sources.lever import (
    LEVER_EU_PUBLIC_API_BASE_URL,
    LEVER_PUBLIC_API_BASE_URL,
    LeverClient,
    LeverFetchResult,
    build_lever_postings_endpoint,
    build_raw_lever_response_record,
    collect_lever_boards,
    discover_lever_boards,
    generate_lever_discovery_queries,
    lever_board_from_slug,
    parse_lever_board_url,
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


class FakeLeverClient:
    def __init__(self, response: list[Any]) -> None:
        self.response = response
        self.fetched_boards: list[str] = []

    def fetch_board(self, board_url_or_slug: str) -> LeverFetchResult:
        self.fetched_boards.append(board_url_or_slug)
        return LeverFetchResult(
            response=self.response,
            endpoint="https://api.lever.co/v0/postings/acme-ai?mode=json",
            api_region="global",
        )


def _sample_lever_response() -> list[dict[str, Any]]:
    return [
        {
            "id": "job-ai-engineer",
            "text": "Senior AI Engineer",
            "hostedUrl": "https://jobs.lever.co/acme-ai/job-ai-engineer",
            "applyUrl": "https://jobs.lever.co/acme-ai/job-ai-engineer/apply",
            "categories": {
                "team": "Engineering",
                "location": "Amsterdam, Netherlands",
                "commitment": "Full-time",
            },
            "description": "<p>Build AI systems.</p>",
            "descriptionPlain": "Build AI systems.",
            "lists": [],
            "createdAt": 1780000000000,
        },
        {
            "id": "job-backend",
            "text": "Backend Engineer",
            "hostedUrl": "https://jobs.lever.co/acme-ai/job-backend",
            "categories": {
                "team": "Engineering",
                "location": "Amsterdam, Netherlands",
                "commitment": "Full-time",
            },
            "description": "<p>Build services.</p>",
            "descriptionPlain": "Build services.",
            "lists": [],
        },
        {
            "id": "job-ai-product",
            "text": "AI Product Manager",
            "hostedUrl": "https://jobs.lever.co/acme-ai/job-ai-product",
            "applyUrl": "https://jobs.lever.co/acme-ai/job-ai-product/apply",
            "categories": {
                "team": "Product",
                "department": "Product Management",
                "location": "Remote - Netherlands",
                "commitment": "Full-time",
            },
            "description": "<p>Shape AI products.</p>",
            "descriptionPlain": "Shape AI products.",
            "lists": [{"text": "Responsibilities", "content": "Shape AI products."}],
            "createdAt": 1780000001000,
        },
    ]


def test_parse_lever_board_url_extracts_first_path_segment() -> None:
    board = parse_lever_board_url("https://jobs.lever.co/insiderone/a2c2944d")

    assert board is not None
    assert board.platform_company_slug == "insiderone"
    assert board.board_url == "https://jobs.lever.co/insiderone"
    assert parse_lever_board_url("jobs.lever.co/acme/jobs/123") is not None
    assert parse_lever_board_url("https://api.lever.co/v0/postings/acme") is None
    assert parse_lever_board_url("https://example.com/acme") is None


def test_discover_lever_boards_writes_deduped_board_records(tmp_path) -> None:
    query = generate_lever_discovery_queries(
        countries_config=load_countries_config(),
        country_codes=["nl"],
    )[0]
    client = FakeSearchClient(
        [
            {
                "organic_results": [
                    {
                        "position": 1,
                        "title": "Acme AI jobs",
                        "link": "https://jobs.lever.co/acme-ai/job-ai-engineer",
                        "snippet": "Acme AI is hiring in Amsterdam.",
                    },
                    {
                        "position": 2,
                        "title": "Acme AI careers",
                        "link": "https://jobs.lever.co/acme-ai",
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

    result = discover_lever_boards(
        [query],
        client=client,
        data_dir=tmp_path,
        clock=lambda: next(timestamps),
    )

    assert result.query_count == 1
    assert result.board_count == 1
    boards = read_jsonl(result.boards_path)
    assert boards[0]["record_type"] == "ats_company_board"
    assert boards[0]["platform"] == "lever"
    assert boards[0]["platform_company_slug"] == "acme-ai"
    assert boards[0]["board_url"] == "https://jobs.lever.co/acme-ai"

    manifest = read_json(result.manifest_path)
    assert manifest["platform"] == "lever"
    assert manifest["board_count"] == 1
    assert manifest["boards_file"] == result.boards_path.as_posix()


def test_generate_lever_discovery_queries_uses_shared_exhaustive_depth() -> None:
    queries = generate_lever_discovery_queries(
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
        query.search_query == 'site:jobs.lever.co "AI Engineer" "Amsterdam"'
        for query in queries
    )


def test_lever_client_gets_public_postings_endpoint() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "GET"
        assert str(request.url) == "https://api.lever.co/v0/postings/acme-ai?mode=json"
        assert "lever" in request.headers["User-Agent"]
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as http_client:
        client = LeverClient(http_client=http_client)
        result = client.fetch_board("https://jobs.lever.co/acme-ai")

    assert len(requests) == 1
    assert result.response == []
    assert result.endpoint == "https://api.lever.co/v0/postings/acme-ai?mode=json"
    assert result.api_region == "global"


def test_lever_client_falls_back_to_eu_endpoint_on_global_404() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if str(request.url).startswith(LEVER_PUBLIC_API_BASE_URL):
            return httpx.Response(404, json={"error": "not found"})
        assert str(request.url).startswith(LEVER_EU_PUBLIC_API_BASE_URL)
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as http_client:
        client = LeverClient(http_client=http_client)
        result = client.fetch_board("acme-ai")

    assert [str(request.url) for request in requests] == [
        "https://api.lever.co/v0/postings/acme-ai?mode=json",
        "https://api.eu.lever.co/v0/postings/acme-ai?mode=json",
    ]
    assert result.endpoint == "https://api.eu.lever.co/v0/postings/acme-ai?mode=json"
    assert result.api_region == "eu"


def test_collect_lever_boards_writes_raw_response_and_manifest(tmp_path) -> None:
    client = FakeLeverClient(_sample_lever_response())
    timestamps = iter(
        [
            "2026-06-16T10:00:00Z",
            "2026-06-16T10:00:01Z",
            "2026-06-16T10:00:02Z",
        ]
    )

    result = collect_lever_boards(
        ["https://jobs.lever.co/acme-ai/job-ai-engineer"],
        client=client,  # type: ignore[arg-type]
        data_dir=tmp_path,
        clock=lambda: next(timestamps),
    )

    assert result.successful_count == 1
    assert result.board_count == 1
    assert result.error_count == 0
    raw_record = read_json(Path(result.result_files[0]))
    assert raw_record["record_type"] == "raw_ats_response"
    assert raw_record["platform"] == "lever"
    assert raw_record["platform_company_slug"] == "acme-ai"
    assert raw_record["request_params"] == {"mode": "json"}
    assert raw_record["endpoint"] == "https://api.lever.co/v0/postings/acme-ai?mode=json"
    assert raw_record["api_region"] == "global"
    assert read_json(result.manifest_path)["result_files"] == result.result_files


def test_normalize_raw_lever_file_keeps_title_ai_signals_only(tmp_path) -> None:
    board = lever_board_from_slug("acme-ai")
    raw_record = build_raw_lever_response_record(
        board=board,
        response=_sample_lever_response(),
        collected_at="2026-06-16T10:00:01Z",
    )
    raw_path = write_raw_ats_response(
        raw_record,
        platform_company_slug="acme-ai",
        collection_date="2026-06-16",
        data_dir=tmp_path,
        platform="lever",
    )

    candidates = normalize_raw_ats_file(raw_path)

    assert [candidate["job_title_raw"] for candidate in candidates] == [
        "Senior AI Engineer",
        "AI Product Manager",
    ]
    assert candidates[0]["source"] == "lever"
    assert candidates[0]["source_mode"] == "public_job_board_endpoint"
    assert candidates[0]["source_url"] == "https://jobs.lever.co/acme-ai/job-ai-engineer"
    assert candidates[0]["board_url"] == "https://jobs.lever.co/acme-ai"
    assert candidates[0]["platform_company_slug"] == "acme-ai"
    assert candidates[0]["platform_job_id"] == "job-ai-engineer"
    assert candidates[0]["company_normalized"] == "Acme Ai"
    assert candidates[0]["job_title_normalized"] == "AI Engineer"
    assert candidates[0]["role_group"] == "AI Execution Role"
    assert candidates[0]["team"] == "Engineering"
    assert candidates[0]["location"] == "Amsterdam, Netherlands"
    assert candidates[0]["country"] == "Netherlands"
    assert candidates[0]["country_code"] == "nl"
    assert candidates[0]["job_countries"] == ["Netherlands"]
    assert candidates[0]["job_country_codes"] == ["nl"]
    assert candidates[0]["job_locations_raw"] == ["Amsterdam, Netherlands"]
    assert candidates[0]["employment_type"] == "Full-time"
    assert candidates[0]["description"] == "<p>Build AI systems.</p>"
    assert candidates[0]["description_plain"] == "Build AI systems."
    assert candidates[0]["source_created_at"] == "1780000000000"
    assert candidates[0]["evidence_quality"] == "title_only_ats_listing"
    assert candidates[1]["role_group"] == "AI Product Role"
    assert candidates[1]["department"] == "Product Management"
    assert candidates[1]["job_countries"] == ["Netherlands"]


def test_process_collection_includes_lever_raw_files(tmp_path) -> None:
    board = lever_board_from_slug("acme-ai")
    raw_record = build_raw_lever_response_record(
        board=board,
        response=_sample_lever_response(),
        collected_at="2026-06-16T10:00:01Z",
    )
    write_raw_ats_response(
        raw_record,
        platform_company_slug="acme-ai",
        collection_date="2026-06-16",
        data_dir=tmp_path,
        platform="lever",
    )

    result = process_collection("2026-06-16", data_dir=tmp_path)

    assert result.raw_file_count == 1
    assert result.candidate_count == 2
    assert result.deduped_candidate_count == 2
    assert result.company_count == 1

    candidates = read_jsonl(result.job_candidates_path)
    assert candidates[0]["source"] == "lever"
    assert candidates[0]["source_url"] == "https://jobs.lever.co/acme-ai/job-ai-engineer"

    companies = read_jsonl(result.companies_path)
    assert companies[0]["company"] == "Acme Ai"
    assert companies[0]["countries"] == ["Netherlands"]
    assert companies[0]["sources"] == ["lever"]
    assert companies[0]["matched_search_terms"] == [
        "AI Engineer",
        "AI Product Manager",
    ]


def test_build_lever_postings_endpoint_quotes_slug() -> None:
    assert build_lever_postings_endpoint("acme ai") == (
        "https://api.lever.co/v0/postings/acme%20ai?mode=json"
    )
