from pathlib import Path
from typing import Any

import httpx

from ai_hiring_radar.config import load_countries_config
from ai_hiring_radar.normalize import normalize_raw_ats_file, process_collection
from ai_hiring_radar.query_builder import LocationDepth
from ai_hiring_radar.sources.ats_discovery import AtsDiscoveryDepth
from ai_hiring_radar.sources.workable import (
    WorkableClient,
    WorkableFetchResult,
    build_raw_workable_response_record,
    build_workable_account_endpoint,
    build_workable_job_detail_endpoint,
    build_workable_jobs_endpoint,
    collect_workable_boards,
    discover_workable_boards,
    generate_workable_discovery_queries,
    parse_workable_board_url,
    workable_board_from_slug,
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


class FakeWorkableClient:
    def __init__(
        self,
        response: dict[str, Any],
        *,
        job_detail_errors: list[dict[str, Any]] | None = None,
    ) -> None:
        self.response = response
        self.job_detail_errors = job_detail_errors or []
        self.fetched_boards: list[str] = []

    def fetch_board(self, board_url_or_slug: str) -> WorkableFetchResult:
        self.fetched_boards.append(board_url_or_slug)
        return WorkableFetchResult(
            response=self.response,
            endpoint="https://apply.workable.com/api/v3/accounts/acme-ai/jobs",
            request_body={},
            account_response={"name": "Acme AI"},
            account_endpoint="https://apply.workable.com/api/v1/accounts/acme-ai?full=true",
            job_detail_responses={
                "AIENG": {
                    "shortcode": "AIENG",
                    "description": "<p>Build AI systems.</p>",
                    "requirements": "Python and ML experience.",
                    "benefits": "Remote setup budget.",
                },
                "AIPM": {
                    "shortcode": "AIPM",
                    "description": "<p>Shape AI products.</p>",
                },
            },
            job_detail_endpoints=[
                "https://apply.workable.com/api/v2/accounts/acme-ai/jobs/AIENG",
                "https://apply.workable.com/api/v2/accounts/acme-ai/jobs/AIPM",
            ],
            job_detail_errors=self.job_detail_errors,
        )


def _sample_workable_response() -> dict[str, Any]:
    return {
        "total": 3,
        "results": [
            {
                "id": 1001,
                "shortcode": "AIENG",
                "title": "Senior AI Engineer",
                "remote": False,
                "location": {
                    "country": "Netherlands",
                    "countryCode": "NL",
                    "city": "Amsterdam",
                    "region": "North Holland",
                },
                "locations": [
                    {
                        "country": "Netherlands",
                        "countryCode": "NL",
                        "city": "Amsterdam",
                        "region": "North Holland",
                        "hidden": False,
                    }
                ],
                "state": "published",
                "published": "2026-07-07T00:00:00.000Z",
                "language": "en",
                "department": ["Engineering"],
                "approvalStatus": "approved",
                "workplace": "hybrid",
            },
            {
                "id": 1002,
                "shortcode": "BACKEND",
                "title": "Backend Engineer",
                "remote": False,
                "location": {
                    "country": "Netherlands",
                    "countryCode": "NL",
                    "city": "Amsterdam",
                    "region": "North Holland",
                },
                "department": ["Engineering"],
                "published": "2026-07-08T00:00:00.000Z",
            },
            {
                "id": 1003,
                "shortcode": "AIPM",
                "title": "AI Product Manager",
                "remote": True,
                "location": {
                    "country": "Netherlands",
                    "countryCode": "NL",
                    "city": "Amsterdam",
                    "region": "North Holland",
                },
                "locations": [
                    {
                        "country": "Netherlands",
                        "countryCode": "NL",
                        "city": "Amsterdam",
                        "region": "North Holland",
                        "hidden": False,
                    },
                    {
                        "country": "Poland",
                        "countryCode": "PL",
                        "city": "Krakow",
                        "region": None,
                        "hidden": False,
                    },
                ],
                "state": "published",
                "published": "2026-07-09T00:00:00.000Z",
                "language": "en",
                "department": ["Product"],
                "workplace": "remote",
            },
        ],
    }


def test_parse_workable_board_url_extracts_account_slug() -> None:
    board = parse_workable_board_url("https://apply.workable.com/acme-ai/j/AIENG")

    assert board is not None
    assert board.platform_company_slug == "acme-ai"
    assert board.board_url == "https://apply.workable.com/acme-ai"
    assert parse_workable_board_url("apply.workable.com/acme-ai") is not None
    assert parse_workable_board_url("https://acme-ai.workable.com/jobs/123") is not None
    assert parse_workable_board_url("https://apply.workable.com/api/v1/accounts/acme") is None
    assert parse_workable_board_url("https://example.com/acme") is None


def test_discover_workable_boards_writes_deduped_board_records(tmp_path) -> None:
    query = generate_workable_discovery_queries(
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
                        "link": "https://apply.workable.com/acme-ai/j/AIENG",
                        "snippet": "Acme AI is hiring in Amsterdam.",
                    },
                    {
                        "position": 2,
                        "title": "Acme AI careers",
                        "link": "https://apply.workable.com/acme-ai",
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

    result = discover_workable_boards(
        [query],
        client=client,
        data_dir=tmp_path,
        clock=lambda: next(timestamps),
    )

    assert result.query_count == 1
    assert result.board_count == 1
    boards = read_jsonl(result.boards_path)
    assert boards[0]["record_type"] == "ats_company_board"
    assert boards[0]["platform"] == "workable"
    assert boards[0]["platform_company_slug"] == "acme-ai"
    assert boards[0]["board_url"] == "https://apply.workable.com/acme-ai"

    manifest = read_json(result.manifest_path)
    assert manifest["platform"] == "workable"
    assert manifest["board_count"] == 1
    assert manifest["boards_file"] == result.boards_path.as_posix()


def test_generate_workable_discovery_queries_uses_shared_exhaustive_depth() -> None:
    queries = generate_workable_discovery_queries(
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
        query.search_query == 'site:apply.workable.com "AI Engineer" "Amsterdam"'
        for query in queries
    )


def test_workable_client_fetches_public_listing_and_detail_endpoints() -> None:
    requests: list[httpx.Request] = []
    workable_response = _sample_workable_response()
    workable_response["total"] = 4
    workable_response["results"].append(
        {
            "id": 1004,
            "shortcode": "DRAFTAI",
            "title": "AI Engineer",
            "state": "draft",
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert "workable" in request.headers["User-Agent"]
        if str(request.url) == "https://apply.workable.com/api/v1/accounts/acme-ai?full=true":
            assert request.method == "GET"
            return httpx.Response(200, json={"name": "Acme AI"})
        if str(request.url) == "https://apply.workable.com/api/v3/accounts/acme-ai/jobs":
            assert request.method == "POST"
            assert request.content == b"{}"
            return httpx.Response(200, json=workable_response)
        assert request.method == "GET"
        return httpx.Response(200, json={"shortcode": request.url.path.rsplit("/", 1)[-1]})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as http_client:
        client = WorkableClient(http_client=http_client)
        result = client.fetch_board("https://apply.workable.com/acme-ai")

    assert [request.method for request in requests] == ["GET", "POST", "GET", "GET"]
    assert [str(request.url) for request in requests[2:]] == [
        build_workable_job_detail_endpoint("acme-ai", "AIENG"),
        build_workable_job_detail_endpoint("acme-ai", "AIPM"),
    ]
    assert result.account_response == {"name": "Acme AI"}
    assert result.response["total"] == 4
    assert sorted(result.job_detail_responses) == ["AIENG", "AIPM"]
    assert result.job_detail_errors == []


def test_workable_client_continues_when_detail_fetch_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://apply.workable.com/api/v1/accounts/acme-ai?full=true":
            return httpx.Response(200, json={"name": "Acme AI"})
        if str(request.url) == "https://apply.workable.com/api/v3/accounts/acme-ai/jobs":
            return httpx.Response(200, json=_sample_workable_response())
        if str(request.url).endswith("/AIENG"):
            return httpx.Response(500, json={"error": "temporary"})
        return httpx.Response(200, json={"shortcode": request.url.path.rsplit("/", 1)[-1]})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as http_client:
        client = WorkableClient(http_client=http_client)
        result = client.fetch_board("acme-ai")

    assert "AIENG" not in result.job_detail_responses
    assert sorted(result.job_detail_responses) == ["AIPM"]
    assert result.job_detail_errors[0]["shortcode"] == "AIENG"
    assert result.job_detail_errors[0]["endpoint"] == build_workable_job_detail_endpoint(
        "acme-ai",
        "AIENG",
    )
    assert result.job_detail_errors[0]["error_scope"] == "job_detail"
    assert result.job_detail_errors[0]["error_type"] == "HTTPStatusError"


def test_collect_workable_boards_writes_raw_response_and_manifest(tmp_path) -> None:
    client = FakeWorkableClient(_sample_workable_response())
    timestamps = iter(
        [
            "2026-06-16T10:00:00Z",
            "2026-06-16T10:00:01Z",
            "2026-06-16T10:00:02Z",
        ]
    )

    result = collect_workable_boards(
        ["https://apply.workable.com/acme-ai/j/AIENG"],
        client=client,  # type: ignore[arg-type]
        data_dir=tmp_path,
        clock=lambda: next(timestamps),
    )

    assert result.successful_count == 1
    assert result.board_count == 1
    assert result.error_count == 0
    raw_record = read_json(Path(result.result_files[0]))
    assert raw_record["record_type"] == "raw_ats_response"
    assert raw_record["platform"] == "workable"
    assert raw_record["platform_company_slug"] == "acme-ai"
    assert raw_record["request_method"] == "POST"
    assert raw_record["request_body"] == {}
    assert raw_record["response_format"] == "json"
    assert raw_record["endpoint"] == "https://apply.workable.com/api/v3/accounts/acme-ai/jobs"
    assert raw_record["account_response"] == {"name": "Acme AI"}
    assert raw_record["title_prefilter"] == {
        "mode": "strict_title",
        "source": "listing_title",
        "source_field": "title/name",
        "listed_count": 3,
        "matched_count": 2,
        "skipped_count": 1,
        "eligible_count": 3,
    }
    assert raw_record["job_detail_responses"]["AIENG"]["description"] == (
        "<p>Build AI systems.</p>"
    )
    assert read_json(result.manifest_path)["result_files"] == result.result_files


def test_collect_workable_boards_preserves_detail_error_metadata(tmp_path) -> None:
    detail_endpoint = build_workable_job_detail_endpoint("acme-ai", "AIENG")
    client = FakeWorkableClient(
        _sample_workable_response(),
        job_detail_errors=[
            {
                "shortcode": "AIENG",
                "endpoint": detail_endpoint,
                "error_scope": "job_detail",
                "error": "temporary failure",
                "error_type": "HTTPStatusError",
            }
        ],
    )
    timestamps = iter(
        [
            "2026-06-16T10:00:00Z",
            "2026-06-16T10:00:01Z",
            "2026-06-16T10:00:02Z",
        ]
    )

    result = collect_workable_boards(
        ["https://apply.workable.com/acme-ai"],
        client=client,  # type: ignore[arg-type]
        data_dir=tmp_path,
        clock=lambda: next(timestamps),
    )

    assert result.error_count == 1
    manifest_error = read_json(result.manifest_path)["errors"][0]
    assert manifest_error["shortcode"] == "AIENG"
    assert manifest_error["endpoint"] == detail_endpoint
    assert manifest_error["error_scope"] == "job_detail"
    assert manifest_error["error_type"] == "HTTPStatusError"
    assert manifest_error["output_file"] == result.result_files[0]


def test_normalize_raw_workable_file_keeps_title_ai_signals_only(tmp_path) -> None:
    board = workable_board_from_slug("acme-ai")
    raw_record = build_raw_workable_response_record(
        board=board,
        response=_sample_workable_response(),
        account_response={"name": "Acme AI"},
        job_detail_responses={
            "AIENG": {
                "shortcode": "AIENG",
                "description": "<p>Build AI systems.</p>",
                "requirements": "Python and ML experience.",
                "benefits": "Remote setup budget.",
            },
            "AIPM": {
                "shortcode": "AIPM",
                "description": "<p>Shape AI products.</p>",
            },
        },
        collected_at="2026-06-16T10:00:01Z",
    )
    raw_path = write_raw_ats_response(
        raw_record,
        platform_company_slug="acme-ai",
        collection_date="2026-06-16",
        data_dir=tmp_path,
        platform="workable",
    )

    candidates = normalize_raw_ats_file(raw_path)

    assert [candidate["job_title_raw"] for candidate in candidates] == [
        "Senior AI Engineer",
        "AI Product Manager",
    ]
    assert candidates[0]["source"] == "workable"
    assert candidates[0]["source_mode"] == "public_job_board_endpoint"
    assert candidates[0]["source_url"] == "https://apply.workable.com/acme-ai/j/AIENG"
    assert candidates[0]["job_url"] == "https://apply.workable.com/acme-ai/j/AIENG"
    assert candidates[0]["board_url"] == "https://apply.workable.com/acme-ai"
    assert candidates[0]["platform_company_slug"] == "acme-ai"
    assert candidates[0]["platform_job_id"] == "AIENG"
    assert candidates[0]["company_normalized"] == "Acme AI"
    assert candidates[0]["job_title_normalized"] == "AI Engineer"
    assert candidates[0]["role_group"] == "AI Execution Role"
    assert candidates[0]["team"] == "Engineering"
    assert candidates[0]["department"] == "Engineering"
    assert candidates[0]["location"] == "Amsterdam, North Holland, Netherlands"
    assert candidates[0]["country"] == "Netherlands"
    assert candidates[0]["country_code"] == "nl"
    assert candidates[0]["job_countries"] == ["Netherlands"]
    assert candidates[0]["job_country_codes"] == ["nl"]
    assert candidates[0]["job_locations_raw"] == [
        "Amsterdam, North Holland, Netherlands"
    ]
    assert candidates[0]["workplace_type"] == "hybrid"
    assert candidates[0]["remote"] is False
    assert candidates[0]["description"] == "<p>Build AI systems.</p>"
    assert candidates[0]["requirements"] == "Python and ML experience."
    assert candidates[0]["benefits"] == "Remote setup budget."
    assert candidates[0]["source_published_at"] == "2026-07-07T00:00:00.000Z"
    assert candidates[0]["evidence_quality"] == "title_only_ats_listing"
    assert candidates[1]["role_group"] == "AI Product Role"
    assert candidates[1]["country"] == "Netherlands"
    assert candidates[1]["country_code"] == "nl"
    assert candidates[1]["job_countries"] == ["Netherlands", "Poland"]
    assert candidates[1]["job_country_codes"] == ["nl", "pl"]
    assert candidates[1]["workplace_type"] == "remote"


def test_normalize_raw_workable_file_skips_non_public_jobs_and_hidden_locations(
    tmp_path,
) -> None:
    board = workable_board_from_slug("acme-ai")
    raw_record = build_raw_workable_response_record(
        board=board,
        response={
            "results": [
                {
                    "shortcode": "VISIBLEAI",
                    "title": "AI Engineer",
                    "locations": [
                        {
                            "country": "Poland",
                            "countryCode": "PL",
                            "city": "Krakow",
                            "hidden": True,
                        },
                        {
                            "country": "Germany",
                            "countryCode": "DE",
                            "city": "Berlin",
                            "hidden": False,
                        },
                    ],
                    "state": "published",
                },
                {
                    "shortcode": "DRAFTAI",
                    "title": "AI Engineer",
                    "state": "draft",
                    "location": {"country": "Netherlands", "countryCode": "NL"},
                },
                {
                    "shortcode": "INTERNALAI",
                    "title": "AI Engineer",
                    "isInternal": True,
                    "location": {"country": "Netherlands", "countryCode": "NL"},
                },
                {
                    "shortcode": "HIDDENAI",
                    "title": "AI Engineer",
                    "hidden": True,
                    "location": {"country": "Netherlands", "countryCode": "NL"},
                },
            ]
        },
        account_response={"name": "Acme AI"},
        collected_at="2026-06-16T10:00:01Z",
    )
    raw_path = write_raw_ats_response(
        raw_record,
        platform_company_slug="acme-ai",
        collection_date="2026-06-16",
        data_dir=tmp_path,
        platform="workable",
    )

    candidates = normalize_raw_ats_file(raw_path)

    assert [candidate["platform_job_id"] for candidate in candidates] == ["VISIBLEAI"]
    assert candidates[0]["country"] == "Germany"
    assert candidates[0]["country_code"] == "de"
    assert candidates[0]["job_countries"] == ["Germany"]
    assert candidates[0]["job_country_codes"] == ["de"]
    assert candidates[0]["job_locations_raw"] == ["Berlin, Germany"]
    assert candidates[0]["locations"] == [
        {
            "country": "Germany",
            "countryCode": "DE",
            "city": "Berlin",
            "hidden": False,
        }
    ]


def test_process_collection_includes_workable_raw_files(tmp_path) -> None:
    board = workable_board_from_slug("acme-ai")
    raw_record = build_raw_workable_response_record(
        board=board,
        response=_sample_workable_response(),
        account_response={"name": "Acme AI"},
        job_detail_responses={
            "AIENG": {"description": "<p>Build AI systems.</p>"},
            "AIPM": {"description": "<p>Shape AI products.</p>"},
        },
        collected_at="2026-06-16T10:00:01Z",
    )
    write_raw_ats_response(
        raw_record,
        platform_company_slug="acme-ai",
        collection_date="2026-06-16",
        data_dir=tmp_path,
        platform="workable",
    )

    result = process_collection("2026-06-16", data_dir=tmp_path)

    assert result.raw_file_count == 1
    assert result.candidate_count == 2
    assert result.deduped_candidate_count == 2
    assert result.company_count == 1

    candidates = read_jsonl(result.job_candidates_path)
    assert candidates[0]["source"] == "workable"
    assert candidates[0]["source_url"] == "https://apply.workable.com/acme-ai/j/AIENG"

    companies = read_jsonl(result.companies_path)
    assert companies[0]["company"] == "Acme AI"
    assert companies[0]["countries"] == ["Netherlands", "Poland"]
    assert companies[0]["sources"] == ["workable"]
    assert companies[0]["matched_search_terms"] == [
        "AI Engineer",
        "AI Product Manager",
    ]


def test_build_workable_endpoints_quote_slug_and_shortcode() -> None:
    assert build_workable_account_endpoint("Acme AI") == (
        "https://apply.workable.com/api/v1/accounts/acme%20ai?full=true"
    )
    assert build_workable_jobs_endpoint("Acme AI") == (
        "https://apply.workable.com/api/v3/accounts/acme%20ai/jobs"
    )
    assert build_workable_job_detail_endpoint("Acme AI", "A/B") == (
        "https://apply.workable.com/api/v2/accounts/acme%20ai/jobs/A%2FB"
    )
