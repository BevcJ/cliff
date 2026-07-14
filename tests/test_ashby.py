import json
from pathlib import Path
from typing import Any

import httpx

from ai_hiring_radar.config import load_countries_config
from ai_hiring_radar.normalizers.ats.registry import normalize_raw_ats_file
from ai_hiring_radar.processing import process_collection
from ai_hiring_radar.search_locations import LocationDepth
from ai_hiring_radar.sources.ashby import (
    ASHBY_JOB_POSTING_GRAPHQL_URL,
    ASHBY_PUBLIC_GRAPHQL_URL,
    AshbyClient,
    AshbyDiscoveryDepth,
    ashby_board_from_slug,
    build_ashby_discovery_search_query,
    build_raw_ashby_response_record,
    collect_ashby_boards,
    discover_ashby_boards,
    generate_ashby_discovery_queries,
    parse_ashby_board_url,
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


class FakeAshbyClient:
    def __init__(
        self,
        response: dict[str, Any],
        detail_responses: dict[str, dict[str, Any] | Exception] | None = None,
    ) -> None:
        self.response = response
        self.detail_responses = detail_responses or {}
        self.fetched_boards: list[str] = []
        self.fetched_job_details: list[tuple[str, str]] = []

    def fetch_board(self, board_url_or_slug: str) -> dict[str, Any]:
        self.fetched_boards.append(board_url_or_slug)
        return self.response

    def fetch_job_detail(
        self,
        *,
        board_url_or_slug: str,
        job_posting_id: str,
    ) -> dict[str, Any]:
        self.fetched_job_details.append((board_url_or_slug, job_posting_id))
        response = self.detail_responses.get(
            job_posting_id,
            {"data": {"jobPosting": {"id": job_posting_id}}},
        )
        if isinstance(response, Exception):
            raise response
        return response


def _sample_ashby_response() -> dict[str, Any]:
    return {
        "data": {
            "jobBoard": {
                "teams": [
                    {
                        "id": "team-rd",
                        "name": "R&D",
                        "externalName": None,
                        "parentTeamId": None,
                    },
                    {
                        "id": "team-ai",
                        "name": "AI",
                        "externalName": None,
                        "parentTeamId": "team-rd",
                    },
                ],
                "jobPostings": [
                    {
                        "id": "job-ai-engineer",
                        "title": "Senior AI Engineer",
                        "teamId": "team-ai",
                        "locationId": "loc-nl",
                        "locationName": "Netherlands",
                        "workplaceType": "Remote",
                        "employmentType": "FullTime",
                        "secondaryLocations": [],
                        "compensationTierSummary": "EUR 80K - 100K",
                    },
                    {
                        "id": "job-backend",
                        "title": "Backend Engineer",
                        "teamId": "team-rd",
                        "locationId": "loc-nl",
                        "locationName": "Netherlands",
                        "workplaceType": "Hybrid",
                        "employmentType": "FullTime",
                        "secondaryLocations": [],
                        "compensationTierSummary": None,
                    },
                    {
                        "id": "job-ai-trainer",
                        "title": "Machine Learning Engineer - AI Trainer - Freelance",
                        "teamId": "team-ai",
                        "locationId": "loc-nl",
                        "locationName": "Netherlands",
                        "workplaceType": "Remote",
                        "employmentType": "Contract",
                        "secondaryLocations": [],
                        "compensationTierSummary": None,
                    },
                    {
                        "id": "job-ai-head",
                        "title": "Head of Artificial Intelligence",
                        "teamId": "team-ai",
                        "locationId": "loc-de",
                        "locationName": "Germany",
                        "workplaceType": "Onsite",
                        "employmentType": "FullTime",
                        "secondaryLocations": [
                            {"locationId": "loc-nl", "locationName": "Netherlands"}
                        ],
                        "compensationTierSummary": None,
                    },
                ],
            }
        }
    }


def test_parse_ashby_board_url_extracts_first_path_segment() -> None:
    board = parse_ashby_board_url("https://jobs.ashbyhq.com/pleo/jobs/123")

    assert board is not None
    assert board.platform_company_slug == "pleo"
    assert board.board_url == "https://jobs.ashbyhq.com/pleo"
    assert parse_ashby_board_url("https://jobs.ashbyhq.com/api/non-user-graphql") is None
    assert parse_ashby_board_url("https://example.com/pleo") is None


def test_build_ashby_discovery_search_query_supports_site_only_and_terms() -> None:
    assert build_ashby_discovery_search_query() == "site:jobs.ashbyhq.com"
    assert (
        build_ashby_discovery_search_query(terms=["AI Engineer", "Netherlands"])
        == 'site:jobs.ashbyhq.com "AI Engineer" "Netherlands"'
    )


def test_generate_ashby_discovery_queries_is_exhaustive_by_default() -> None:
    queries = generate_ashby_discovery_queries(
        countries_config=load_countries_config(),
        country_codes=["nl"],
        role_terms=["AI Engineer"],
        signal_terms=["LLM"],
    )

    query_types = {query.discovery_query_type for query in queries}
    assert query_types == {
        "site_only",
        "location",
        "role",
        "ai_signal",
        "role_country",
        "ai_signal_country",
        "role_location",
        "ai_signal_location",
    }
    assert {query.page for query in queries} == {1, 2}
    assert {query.request_params["num"] for query in queries} == {10}
    assert any(query.search_query == "site:jobs.ashbyhq.com" for query in queries)
    assert any(
        query.search_query == 'site:jobs.ashbyhq.com "AI Engineer" "Netherlands"'
        for query in queries
    )
    assert any(
        query.search_query == 'site:jobs.ashbyhq.com "AI Engineer" "Amsterdam"'
        for query in queries
    )
    assert any(query.request_params.get("page") == 2 for query in queries)
    assert any(query.search_location_label == "Amsterdam" for query in queries)


def test_generate_ashby_discovery_queries_exhaustive_adds_term_location_pairs() -> None:
    queries = generate_ashby_discovery_queries(
        countries_config=load_countries_config(),
        country_codes=["nl"],
        role_terms=["AI Engineer"],
        signal_terms=["LLM"],
        pages=1,
        num=5,
        location_depth=LocationDepth.CITIES,
        discovery_depth=AshbyDiscoveryDepth.EXHAUSTIVE,
    )

    query_types = {query.discovery_query_type for query in queries}
    assert "role_location" in query_types
    assert "ai_signal_location" in query_types
    assert any(
        query.search_query == 'site:jobs.ashbyhq.com "AI Engineer" "Amsterdam"'
        for query in queries
    )
    assert {query.request_params["num"] for query in queries} == {5}


def test_discover_ashby_boards_writes_deduped_board_records(tmp_path) -> None:
    query = generate_ashby_discovery_queries(
        countries_config=load_countries_config(),
        country_codes=["nl"],
    )[0]
    client = FakeSearchClient(
        [
            {
                "organic_results": [
                    {
                        "position": 1,
                        "title": "Pleo jobs",
                        "link": "https://jobs.ashbyhq.com/pleo/123",
                        "snippet": "Pleo is hiring in Amsterdam.",
                    },
                    {
                        "position": 2,
                        "title": "Pleo careers",
                        "link": "https://jobs.ashbyhq.com/pleo",
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

    result = discover_ashby_boards(
        [query],
        client=client,
        data_dir=tmp_path,
        clock=lambda: next(timestamps),
    )

    assert result.query_count == 1
    assert result.board_count == 1
    boards = read_jsonl(result.boards_path)
    assert boards[0]["record_type"] == "ats_company_board"
    assert boards[0]["platform"] == "ashby"
    assert boards[0]["platform_company_slug"] == "pleo"
    assert boards[0]["board_url"] == "https://jobs.ashbyhq.com/pleo"
    assert boards[0]["discovery_query_type"] == "site_only"
    assert boards[0]["discovery_terms"] == []
    assert boards[0]["search_page"] == 1

    manifest = read_json(result.manifest_path)
    assert manifest["board_count"] == 1
    assert manifest["boards_file"] == result.boards_path.as_posix()
    assert manifest["query_types"] == ["site_only"]
    assert manifest["pages"] == [1]
    assert manifest["results_per_query"] == [10]


def test_ashby_client_posts_public_graphql_body() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = json.loads(request.content)
        assert request.method == "POST"
        assert str(request.url) == ASHBY_PUBLIC_GRAPHQL_URL
        assert request.headers["Content-Type"] == "application/json"
        assert body["operationName"] == "ApiJobBoardWithTeams"
        assert body["variables"] == {"organizationHostedJobsPageName": "everai"}
        assert "jobBoardWithTeams" in body["query"]
        return httpx.Response(200, json={"data": {"jobBoard": {}}})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as http_client:
        client = AshbyClient(
            http_client=http_client,
            request_delay_seconds=0,
            max_retries=0,
        )
        payload = client.fetch_board("https://jobs.ashbyhq.com/everai")

    assert len(requests) == 1
    assert payload == {"data": {"jobBoard": {}}}


def test_ashby_client_posts_job_detail_graphql_body() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = json.loads(request.content)
        assert request.method == "POST"
        assert str(request.url) == ASHBY_JOB_POSTING_GRAPHQL_URL
        assert request.headers["Content-Type"] == "application/json"
        assert body["operationName"] == "ApiJobPosting"
        assert body["variables"] == {
            "organizationHostedJobsPageName": "everai",
            "jobPostingId": "job-ai-engineer",
        }
        assert "descriptionHtml" in body["query"]
        return httpx.Response(
            200,
            json={"data": {"jobPosting": {"id": "job-ai-engineer"}}},
        )

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as http_client:
        client = AshbyClient(
            http_client=http_client,
            request_delay_seconds=0,
            max_retries=0,
        )
        payload = client.fetch_job_detail(
            board_url_or_slug="https://jobs.ashbyhq.com/everai",
            job_posting_id="job-ai-engineer",
        )

    assert len(requests) == 1
    assert payload == {"data": {"jobPosting": {"id": "job-ai-engineer"}}}


def test_ashby_client_sleeps_between_api_calls() -> None:
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "ApiJobPosting" in str(request.url):
            return httpx.Response(200, json={"data": {"jobPosting": {}}})
        return httpx.Response(200, json={"data": {"jobBoard": {}}})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as http_client:
        client = AshbyClient(
            http_client=http_client,
            request_delay_seconds=0.2,
            max_retries=0,
            sleeper=sleeps.append,
        )
        client.fetch_board("https://jobs.ashbyhq.com/everai")
        client.fetch_job_detail(
            board_url_or_slug="https://jobs.ashbyhq.com/everai",
            job_posting_id="job-ai-engineer",
        )

    assert sleeps == [0.2]


def test_collect_ashby_boards_writes_raw_response_and_manifest(tmp_path) -> None:
    client = FakeAshbyClient(_sample_ashby_response())
    timestamps = iter(
        [
            "2026-06-16T10:00:00Z",
            "2026-06-16T10:00:01Z",
            "2026-06-16T10:00:02Z",
        ]
    )

    result = collect_ashby_boards(
        ["https://jobs.ashbyhq.com/everai"],
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
    assert raw_record["platform_company_slug"] == "everai"
    assert raw_record["request_body"]["variables"] == {
        "organizationHostedJobsPageName": "everai"
    }
    assert raw_record["title_prefilter"] == {
        "mode": "strict_title",
        "source": "listing_title",
        "source_field": "title",
        "listed_count": 4,
        "matched_count": 2,
        "skipped_count": 2,
    }
    assert sorted(raw_record["job_detail_responses"]) == [
        "job-ai-engineer",
        "job-ai-head",
    ]
    assert client.fetched_job_details == [
        ("https://jobs.ashbyhq.com/everai", "job-ai-engineer"),
        ("https://jobs.ashbyhq.com/everai", "job-ai-head"),
    ]
    assert raw_record["job_detail_errors"] == []
    manifest = read_json(result.manifest_path)
    assert manifest["result_files"] == result.result_files
    assert manifest["written_files"] == result.written_files
    assert manifest["resumed_files"] == result.resumed_files


def test_collect_ashby_boards_resumes_valid_raw_file(tmp_path) -> None:
    board = ashby_board_from_slug("everai")
    raw_path = write_raw_ats_response(
        build_raw_ashby_response_record(
            board=board,
            response=_sample_ashby_response(),
            collected_at="2026-06-16T09:00:00Z",
        ),
        platform_company_slug=board.platform_company_slug,
        collection_date="2026-06-16",
        data_dir=tmp_path,
        platform="ashby",
    )
    client = FakeAshbyClient(_sample_ashby_response())
    timestamps = iter(["2026-06-16T10:00:00Z", "2026-06-16T10:00:01Z"])

    result = collect_ashby_boards(
        [board.board_url],
        client=client,  # type: ignore[arg-type]
        data_dir=tmp_path,
        clock=lambda: next(timestamps),
    )

    assert client.fetched_boards == []
    assert client.fetched_job_details == []
    assert result.result_files == [raw_path.as_posix()]
    assert result.written_files == []
    assert result.resumed_files == [raw_path.as_posix()]
    assert result.successful_count == 1
    assert result.written_count == 0
    assert result.resumed_count == 1
    manifest = read_json(result.manifest_path)
    assert manifest["result_files"] == [raw_path.as_posix()]
    assert manifest["written_files"] == []
    assert manifest["resumed_files"] == [raw_path.as_posix()]


def test_collect_ashby_boards_keeps_board_when_job_detail_fails(tmp_path) -> None:
    client = FakeAshbyClient(
        _sample_ashby_response(),
        detail_responses={"job-ai-head": RuntimeError("detail failed")},
    )
    timestamps = iter(
        [
            "2026-06-16T10:00:00Z",
            "2026-06-16T10:00:01Z",
            "2026-06-16T10:00:02Z",
        ]
    )

    result = collect_ashby_boards(
        ["https://jobs.ashbyhq.com/everai"],
        client=client,  # type: ignore[arg-type]
        data_dir=tmp_path,
        clock=lambda: next(timestamps),
    )

    assert result.successful_count == 1
    assert result.board_count == 1
    assert result.error_count == 1
    raw_record = read_json(Path(result.result_files[0]))
    assert sorted(raw_record["job_detail_responses"]) == [
        "job-ai-engineer",
    ]
    assert raw_record["job_detail_errors"] == [
        {
            "platform": "ashby",
            "platform_company_slug": "everai",
            "board_url": "https://jobs.ashbyhq.com/everai",
            "platform_job_id": "job-ai-head",
            "error_scope": "job_detail",
            "error": "detail failed",
            "error_type": "RuntimeError",
        }
    ]
    manifest = read_json(result.manifest_path)
    assert manifest["errors"] == raw_record["job_detail_errors"]


def test_normalize_raw_ashby_file_keeps_title_ai_signals_only(tmp_path) -> None:
    board = ashby_board_from_slug("everai")
    raw_record = build_raw_ashby_response_record(
        board=board,
        response=_sample_ashby_response(),
        collected_at="2026-06-16T10:00:01Z",
    )
    raw_path = write_raw_ats_response(
        raw_record,
        platform_company_slug="everai",
        collection_date="2026-06-16",
        data_dir=tmp_path,
    )

    candidates = normalize_raw_ats_file(raw_path)

    assert [candidate["job_title_raw"] for candidate in candidates] == [
        "Senior AI Engineer",
        "Head of Artificial Intelligence",
    ]
    assert candidates[0]["source"] == "ashby"
    assert candidates[0]["source_mode"] == "public_job_board_endpoint"
    assert candidates[0]["platform_company_slug"] == "everai"
    assert candidates[0]["platform_job_id"] == "job-ai-engineer"
    assert candidates[0]["company_normalized"] == "Everai"
    assert candidates[0]["job_title_normalized"] == "AI Engineer"
    assert candidates[0]["role_group"] == "AI Execution Role"
    assert candidates[0]["team"] == "AI"
    assert candidates[0]["parent_team"] == "R&D"
    assert candidates[0]["location"] == "Netherlands"
    assert candidates[0]["country"] == "Netherlands"
    assert candidates[0]["country_code"] == "nl"
    assert candidates[0]["job_countries"] == ["Netherlands"]
    assert candidates[0]["job_country_codes"] == ["nl"]
    assert candidates[0]["job_locations_raw"] == ["Netherlands"]
    assert candidates[0]["evidence_quality"] == "title_only_ats_listing"
    assert candidates[1]["role_group"] == "Unclear AI Role"
    assert candidates[1]["job_countries"] == ["Germany", "Netherlands"]
    assert candidates[1]["job_country_codes"] == ["de", "nl"]


def test_normalize_raw_ashby_file_uses_job_detail_description(tmp_path) -> None:
    board = ashby_board_from_slug("everai")
    raw_record = build_raw_ashby_response_record(
        board=board,
        response=_sample_ashby_response(),
        collected_at="2026-06-16T10:00:01Z",
        job_detail_responses={
            "job-ai-engineer": {
                "data": {
                    "jobPosting": {
                        "id": "job-ai-engineer",
                        "descriptionHtml": "<p>Build AI systems.</p>",
                        "departmentName": "Engineering",
                        "teamNames": ["AI"],
                        "locationName": "Amsterdam, Netherlands",
                        "workplaceType": "Hybrid",
                        "employmentType": "FullTime",
                        "compensationTierSummary": "EUR 80K - 100K",
                    }
                }
            }
        },
    )
    raw_path = write_raw_ats_response(
        raw_record,
        platform_company_slug="everai",
        collection_date="2026-06-16",
        data_dir=tmp_path,
    )

    candidates = normalize_raw_ats_file(raw_path)

    assert candidates[0]["platform_job_id"] == "job-ai-engineer"
    assert candidates[0]["job_url"] == "https://jobs.ashbyhq.com/everai/job-ai-engineer"
    assert candidates[0]["description"] == "<p>Build AI systems.</p>"
    assert candidates[0]["department"] == "Engineering"
    assert candidates[0]["teams"] == ["AI"]
    assert candidates[0]["workplace_type"] == "Remote"
    assert candidates[0]["employment_type"] == "FullTime"
    assert candidates[0]["compensation"] == "EUR 80K - 100K"


def test_process_collection_includes_ashby_raw_files(tmp_path) -> None:
    board = ashby_board_from_slug("everai")
    raw_record = build_raw_ashby_response_record(
        board=board,
        response=_sample_ashby_response(),
        collected_at="2026-06-16T10:00:01Z",
    )
    write_raw_ats_response(
        raw_record,
        platform_company_slug="everai",
        collection_date="2026-06-16",
        data_dir=tmp_path,
    )

    result = process_collection("2026-06-16", data_dir=tmp_path)

    assert result.raw_file_count == 1
    assert result.candidate_count == 2
    assert result.deduped_candidate_count == 2
    assert result.company_count == 1

    candidates = read_jsonl(result.job_candidates_path)
    assert candidates[0]["source"] == "ashby"
    assert candidates[0]["source_url"] == "https://jobs.ashbyhq.com/everai"

    companies = read_jsonl(result.companies_path)
    assert companies[0]["company"] == "Everai"
    assert companies[0]["countries"] == ["Netherlands", "Germany"]
    assert companies[0]["sources"] == ["ashby"]
    assert companies[0]["matched_search_terms"] == [
        "AI Engineer",
        "title contains AI",
    ]
