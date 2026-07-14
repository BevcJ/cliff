from pathlib import Path
from typing import Any

import httpx
import pytest

from ai_hiring_radar.config import load_countries_config
from ai_hiring_radar.normalizers.ats.registry import normalize_raw_ats_file
from ai_hiring_radar.processing import process_collection
from ai_hiring_radar.search_locations import LocationDepth
from ai_hiring_radar.sources.ats_discovery import AtsDiscoveryDepth
from ai_hiring_radar.sources.smartrecruiters import (
    SmartRecruitersClient,
    SmartRecruitersFetchResult,
    build_raw_smartrecruiters_response_record,
    build_smartrecruiters_postings_endpoint,
    collect_smartrecruiters_boards,
    discover_smartrecruiters_boards,
    generate_smartrecruiters_discovery_queries,
    parse_smartrecruiters_board_url,
    smartrecruiters_board_from_slug,
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


class FakeSmartRecruitersClient:
    def __init__(self, response: list[dict[str, Any]]) -> None:
        self.response = response
        self.fetched_boards: list[str] = []

    def fetch_board(self, board_url_or_slug: str) -> SmartRecruitersFetchResult:
        self.fetched_boards.append(board_url_or_slug)
        endpoint = (
            "https://api.smartrecruiters.com/v1/companies/acme-ai/postings"
            "?limit=100&offset=0"
        )
        return SmartRecruitersFetchResult(
            response=self.response,
            endpoint=endpoint,
            page_endpoints=[endpoint],
            request_params={"limit": 100, "offset": 0},
        )


def _sample_smartrecruiters_response() -> list[dict[str, Any]]:
    return [
        {
            "content": [
                {
                    "id": "job-ai-engineer",
                    "name": "Senior AI Engineer",
                    "ref": (
                        "https://api.smartrecruiters.com/v1/companies/acme-ai/"
                        "postings/job-ai-engineer"
                    ),
                    "location": {
                        "city": "Amsterdam",
                        "country": "nl",
                        "remote": True,
                        "hybrid": False,
                        "fullLocation": "Amsterdam, Netherlands",
                    },
                    "releasedDate": "2026-06-16T00:00:00Z",
                },
                {
                    "id": "job-backend",
                    "name": "Backend Engineer",
                    "ref": (
                        "https://api.smartrecruiters.com/v1/companies/acme-ai/"
                        "postings/job-backend"
                    ),
                    "location": {
                        "city": "Amsterdam",
                        "country": "nl",
                        "remote": False,
                        "hybrid": False,
                        "fullLocation": "Amsterdam, Netherlands",
                    },
                },
                {
                    "id": "job-ai-product",
                    "name": "AI Product Manager",
                    "ref": (
                        "https://api.smartrecruiters.com/v1/companies/acme-ai/"
                        "postings/job-ai-product"
                    ),
                    "location": {
                        "city": "Krakow",
                        "country": "pl",
                        "remote": False,
                        "hybrid": True,
                        "fullLocation": "Krakow, Poland",
                    },
                    "releasedDate": "2026-06-17T00:00:00Z",
                },
            ],
            "limit": 100,
            "offset": 0,
            "totalFound": 3,
        }
    ]


def test_parse_smartrecruiters_board_url_extracts_company_identifier() -> None:
    board = parse_smartrecruiters_board_url(
        "https://careers.smartrecruiters.com/acme-ai/jobs/123"
    )

    assert board is not None
    assert board.platform_company_slug == "acme-ai"
    assert board.board_url == "https://careers.smartrecruiters.com/acme-ai"
    assert parse_smartrecruiters_board_url(
        "careers.smartrecruiters.com/acme-ai/jobs"
    ) is not None
    assert parse_smartrecruiters_board_url(
        "https://jobs.smartrecruiters.com/acme-ai/123-ai-engineer"
    ) is not None
    assert parse_smartrecruiters_board_url(
        "https://api.smartrecruiters.com/v1/companies/acme-ai/postings/123"
    ) is not None
    assert parse_smartrecruiters_board_url("https://example.com/acme-ai") is None


def test_discover_smartrecruiters_boards_writes_deduped_board_records(tmp_path) -> None:
    query = generate_smartrecruiters_discovery_queries(
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
                        "link": (
                            "https://careers.smartrecruiters.com/acme-ai/"
                            "jobs/123-ai-engineer"
                        ),
                        "snippet": "Acme AI is hiring in Amsterdam.",
                    },
                    {
                        "position": 2,
                        "title": "Acme AI careers",
                        "link": "https://careers.smartrecruiters.com/acme-ai",
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

    result = discover_smartrecruiters_boards(
        [query],
        client=client,
        data_dir=tmp_path,
        clock=lambda: next(timestamps),
    )

    assert result.query_count == 1
    assert result.board_count == 1
    boards = read_jsonl(result.boards_path)
    assert boards[0]["record_type"] == "ats_company_board"
    assert boards[0]["platform"] == "smartrecruiters"
    assert boards[0]["platform_company_slug"] == "acme-ai"
    assert boards[0]["board_url"] == "https://careers.smartrecruiters.com/acme-ai"

    manifest = read_json(result.manifest_path)
    assert manifest["platform"] == "smartrecruiters"
    assert manifest["board_count"] == 1
    assert manifest["boards_file"] == result.boards_path.as_posix()


def test_generate_smartrecruiters_discovery_queries_uses_shared_exhaustive_depth() -> None:
    queries = generate_smartrecruiters_discovery_queries(
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
        query.search_query
        == 'site:careers.smartrecruiters.com "AI Engineer" "Amsterdam"'
        for query in queries
    )


def test_smartrecruiters_client_fetches_paginated_public_postings_endpoint() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "GET"
        assert "smartrecruiters" in request.headers["User-Agent"]
        if str(request.url).endswith("offset=0"):
            return httpx.Response(
                200,
                json={
                    "content": [{"id": "job-1", "name": "AI Engineer"}],
                    "limit": 1,
                    "offset": 0,
                    "totalFound": 2,
                },
            )
        return httpx.Response(
            200,
            json={
                "content": [{"id": "job-2", "name": "AI Product Manager"}],
                "limit": 1,
                "offset": 1,
                "totalFound": 2,
            },
        )

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as http_client:
        client = SmartRecruitersClient(
            http_client=http_client,
            page_limit=1,
            request_delay_seconds=0,
            max_retries=0,
        )
        result = client.fetch_board("https://careers.smartrecruiters.com/acme-ai")

    assert [str(request.url) for request in requests] == [
        "https://api.smartrecruiters.com/v1/companies/acme-ai/postings?limit=1&offset=0",
        "https://api.smartrecruiters.com/v1/companies/acme-ai/postings?limit=1&offset=1",
    ]
    assert [page["offset"] for page in result.response] == [0, 1]
    assert result.request_params == {"limit": 1, "offset": 0}


def test_collect_smartrecruiters_boards_writes_raw_response_and_manifest(tmp_path) -> None:
    client = FakeSmartRecruitersClient(_sample_smartrecruiters_response())
    timestamps = iter(
        [
            "2026-06-16T10:00:00Z",
            "2026-06-16T10:00:01Z",
            "2026-06-16T10:00:02Z",
        ]
    )

    result = collect_smartrecruiters_boards(
        ["https://careers.smartrecruiters.com/acme-ai/jobs/123-ai-engineer"],
        client=client,  # type: ignore[arg-type]
        data_dir=tmp_path,
        clock=lambda: next(timestamps),
    )

    assert result.successful_count == 1
    assert result.written_count == 1
    assert result.resumed_count == 0
    assert result.written_files == result.result_files
    assert result.resumed_files == []
    assert result.board_count == 1
    assert result.error_count == 0
    raw_record = read_json(Path(result.result_files[0]))
    assert raw_record["record_type"] == "raw_ats_response"
    assert raw_record["platform"] == "smartrecruiters"
    assert raw_record["platform_company_slug"] == "acme-ai"
    assert raw_record["request_params"] == {"limit": 100, "offset": 0}
    assert raw_record["response_format"] == "json"
    assert raw_record["endpoint"] == (
        "https://api.smartrecruiters.com/v1/companies/acme-ai/postings"
        "?limit=100&offset=0"
    )
    assert raw_record["title_prefilter"] == {
        "mode": "strict_title",
        "source": "listing_title",
        "source_field": "name/title",
        "listed_count": 3,
        "matched_count": 2,
        "skipped_count": 1,
    }
    assert raw_record["response"] == _sample_smartrecruiters_response()
    manifest = read_json(result.manifest_path)
    assert manifest["result_files"] == result.result_files
    assert manifest["written_files"] == result.written_files
    assert manifest["resumed_files"] == result.resumed_files


def test_collect_smartrecruiters_boards_validates_explicit_collection_date(
    tmp_path,
) -> None:
    client = FakeSmartRecruitersClient(_sample_smartrecruiters_response())

    with pytest.raises(ValueError):
        collect_smartrecruiters_boards(
            ["acme-ai"],
            client=client,  # type: ignore[arg-type]
            collection_date="",
            data_dir=tmp_path,
            clock=lambda: "2026-06-20T10:00:00Z",
        )

    assert client.fetched_boards == []


def test_normalize_raw_smartrecruiters_file_keeps_title_ai_signals_only(tmp_path) -> None:
    board = smartrecruiters_board_from_slug("acme-ai")
    raw_record = build_raw_smartrecruiters_response_record(
        board=board,
        response=_sample_smartrecruiters_response(),
        collected_at="2026-06-16T10:00:01Z",
    )
    raw_path = write_raw_ats_response(
        raw_record,
        platform_company_slug="acme-ai",
        collection_date="2026-06-16",
        data_dir=tmp_path,
        platform="smartrecruiters",
    )

    candidates = normalize_raw_ats_file(raw_path)

    assert [candidate["job_title_raw"] for candidate in candidates] == [
        "Senior AI Engineer",
        "AI Product Manager",
    ]
    assert candidates[0]["source"] == "smartrecruiters"
    assert candidates[0]["source_mode"] == "public_job_board_endpoint"
    assert candidates[0]["source_url"] == (
        "https://api.smartrecruiters.com/v1/companies/acme-ai/postings/job-ai-engineer"
    )
    assert candidates[0]["job_url"] == (
        "https://api.smartrecruiters.com/v1/companies/acme-ai/postings/job-ai-engineer"
    )
    assert candidates[0]["board_url"] == "https://careers.smartrecruiters.com/acme-ai"
    assert candidates[0]["platform_company_slug"] == "acme-ai"
    assert candidates[0]["platform_job_id"] == "job-ai-engineer"
    assert candidates[0]["company_normalized"] == "Acme Ai"
    assert candidates[0]["job_title_normalized"] == "AI Engineer"
    assert candidates[0]["role_group"] == "AI Execution Role"
    assert candidates[0]["location"] == "Amsterdam, Netherlands"
    assert candidates[0]["country"] == "Netherlands"
    assert candidates[0]["country_code"] == "nl"
    assert candidates[0]["job_countries"] == ["Netherlands"]
    assert candidates[0]["job_country_codes"] == ["nl"]
    assert candidates[0]["job_locations_raw"] == ["Amsterdam, Netherlands", "Amsterdam"]
    assert candidates[0]["location_country_raw"] == "nl"
    assert candidates[0]["workplace_type"] == "remote"
    assert candidates[0]["remote"] is True
    assert candidates[0]["hybrid"] is False
    assert candidates[0]["api_ref"] == (
        "https://api.smartrecruiters.com/v1/companies/acme-ai/postings/job-ai-engineer"
    )
    assert candidates[0]["source_created_at"] == "2026-06-16T00:00:00Z"
    assert candidates[0]["evidence_quality"] == "title_only_ats_listing"
    assert candidates[1]["role_group"] == "AI Product Role"
    assert candidates[1]["country"] == "Poland"
    assert candidates[1]["country_code"] == "pl"
    assert candidates[1]["workplace_type"] == "hybrid"


def test_process_collection_includes_smartrecruiters_raw_files(tmp_path) -> None:
    board = smartrecruiters_board_from_slug("acme-ai")
    raw_record = build_raw_smartrecruiters_response_record(
        board=board,
        response=_sample_smartrecruiters_response(),
        collected_at="2026-06-16T10:00:01Z",
    )
    write_raw_ats_response(
        raw_record,
        platform_company_slug="acme-ai",
        collection_date="2026-06-16",
        data_dir=tmp_path,
        platform="smartrecruiters",
    )

    result = process_collection("2026-06-16", data_dir=tmp_path)

    assert result.raw_file_count == 1
    assert result.candidate_count == 2
    assert result.deduped_candidate_count == 2
    assert result.company_count == 1

    candidates = read_jsonl(result.job_candidates_path)
    assert candidates[0]["source"] == "smartrecruiters"
    assert candidates[0]["source_url"] == (
        "https://api.smartrecruiters.com/v1/companies/acme-ai/postings/job-ai-engineer"
    )

    companies = read_jsonl(result.companies_path)
    assert companies[0]["company"] == "Acme Ai"
    assert companies[0]["countries"] == ["Netherlands", "Poland"]
    assert companies[0]["sources"] == ["smartrecruiters"]
    assert companies[0]["matched_search_terms"] == [
        "AI Engineer",
        "AI Product Manager",
    ]


def test_build_smartrecruiters_postings_endpoint_quotes_slug_and_query() -> None:
    assert build_smartrecruiters_postings_endpoint(
        "Acme AI",
        limit=50,
        offset=100,
        search_text="AI Engineer",
    ) == (
        "https://api.smartrecruiters.com/v1/companies/Acme%20AI/postings"
        "?limit=50&offset=100&q=AI+Engineer"
    )
