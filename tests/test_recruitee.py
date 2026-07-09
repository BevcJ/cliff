from pathlib import Path
from typing import Any

import httpx
import pytest

from ai_hiring_radar.config import load_countries_config
from ai_hiring_radar.normalize import normalize_raw_ats_file, process_collection
from ai_hiring_radar.query_builder import LocationDepth
from ai_hiring_radar.sources.ats_discovery import AtsDiscoveryDepth
from ai_hiring_radar.sources.recruitee import (
    RecruiteeClient,
    RecruiteeFetchResult,
    RecruiteeOfferDetailResult,
    build_raw_recruitee_response_record,
    build_recruitee_offer_detail_endpoint,
    build_recruitee_offers_endpoint,
    collect_recruitee_boards,
    discover_recruitee_boards,
    generate_recruitee_discovery_queries,
    parse_recruitee_board_url,
    recruitee_board_from_slug,
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


class FakeRecruiteeClient:
    def __init__(
        self,
        response: dict[str, Any],
        detail_responses: dict[str, dict[str, Any] | Exception],
    ) -> None:
        self.response = response
        self.detail_responses = detail_responses
        self.fetched_boards: list[str] = []
        self.fetched_details: list[tuple[str, str]] = []

    def fetch_board(self, board_url_or_slug: str) -> RecruiteeFetchResult:
        self.fetched_boards.append(board_url_or_slug)
        return RecruiteeFetchResult(
            response=self.response,
            endpoint="https://acme-ai.recruitee.com/api/offers/",
        )

    def fetch_offer_detail(
        self,
        *,
        board_url_or_slug: str,
        offer_identifier: str,
    ) -> RecruiteeOfferDetailResult:
        self.fetched_details.append((board_url_or_slug, offer_identifier))
        response = self.detail_responses[offer_identifier]
        if isinstance(response, Exception):
            raise response
        return RecruiteeOfferDetailResult(
            response=response,
            endpoint=f"https://acme-ai.recruitee.com/api/offers/{offer_identifier}",
            offer_identifier=offer_identifier,
        )


def _sample_recruitee_response() -> dict[str, Any]:
    return {
        "offers": [
            {
                "id": 123,
                "slug": "senior-ai-engineer",
                "title": "Senior AI Engineer",
                "careers_url": "https://acme-ai.recruitee.com/o/senior-ai-engineer",
                "location": "Amsterdam, Netherlands",
                "department": "Engineering",
            },
            {
                "id": 124,
                "slug": "backend-engineer",
                "title": "Backend Engineer",
                "careers_url": "https://acme-ai.recruitee.com/o/backend-engineer",
                "location": "Amsterdam, Netherlands",
                "department": "Engineering",
            },
            {
                "id": 125,
                "slug": "ai-product-manager",
                "title": "AI Product Manager",
                "careers_url": "https://acme-ai.recruitee.com/o/ai-product-manager",
                "location": "Remote - Netherlands",
                "department": "Product",
            },
        ]
    }


def _sample_recruitee_detail_responses() -> dict[str, dict[str, Any]]:
    return {
        "123": {
            "offer": {
                "id": 123,
                "slug": "senior-ai-engineer",
                "title": "Senior AI Engineer",
                "company": "Acme AI",
                "department": {"id": 1, "name": "Engineering"},
                "locations": [
                    {
                        "country_code": "NL",
                        "country": "Netherlands",
                        "city": "Amsterdam",
                        "full_address": "Netherlands, Noord-Holland, Amsterdam",
                    }
                ],
                "description": "Build AI systems.",
                "requirements": "Python and ML experience.",
                "remote": True,
                "hybrid": False,
                "on_site": False,
                "employment_type_code": "full-time",
                "salary": {"currency": "EUR", "min": 70000, "max": 90000},
                "careers_url": "https://acme-ai.recruitee.com/o/senior-ai-engineer",
                "careers_apply_url": (
                    "https://acme-ai.recruitee.com/o/senior-ai-engineer/apply"
                ),
                "published_at": "2026-06-16T00:00:00Z",
                "updated_at": "2026-06-17T00:00:00Z",
            }
        },
        "124": {
            "offer": {
                "id": 124,
                "slug": "backend-engineer",
                "title": "Backend Engineer",
                "company": "Acme AI",
                "department": {"id": 1, "name": "Engineering"},
                "locations": [
                    {
                        "country_code": "NL",
                        "country": "Netherlands",
                        "city": "Amsterdam",
                    }
                ],
                "description": "Build backend systems.",
            }
        },
        "125": {
            "offer": {
                "id": 125,
                "slug": "ai-product-manager",
                "title": "AI Product Manager",
                "company": "Acme AI",
                "department": {"id": 2, "name": "Product"},
                "locations": [
                    {
                        "country_code": "NL",
                        "country": "Netherlands",
                        "full_address": "Netherlands",
                    }
                ],
                "description": "Shape AI products.",
                "remote": False,
                "hybrid": True,
                "on_site": False,
                "employment_type_code": "full-time",
                "careers_url": "https://acme-ai.recruitee.com/o/ai-product-manager",
            }
        },
    }


def test_parse_recruitee_board_url_extracts_company_subdomain() -> None:
    board = parse_recruitee_board_url("https://acme-ai.recruitee.com/o/job-123")

    assert board is not None
    assert board.platform_company_slug == "acme-ai"
    assert board.board_url == "https://acme-ai.recruitee.com"
    assert parse_recruitee_board_url("acme-ai.recruitee.com/api/offers/") is not None
    assert parse_recruitee_board_url("https://acme_ai.recruitee.com") is None
    assert parse_recruitee_board_url("https://support.recruitee.com/docs") is None
    assert parse_recruitee_board_url("https://example.com/acme-ai") is None


def test_discover_recruitee_boards_writes_deduped_board_records(tmp_path) -> None:
    query = generate_recruitee_discovery_queries(
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
                        "link": "https://acme-ai.recruitee.com/o/senior-ai-engineer",
                        "snippet": "Acme AI is hiring in Amsterdam.",
                    },
                    {
                        "position": 2,
                        "title": "Acme AI careers",
                        "link": "https://acme-ai.recruitee.com",
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

    result = discover_recruitee_boards(
        [query],
        client=client,
        data_dir=tmp_path,
        clock=lambda: next(timestamps),
    )

    assert result.query_count == 1
    assert result.board_count == 1
    boards = read_jsonl(result.boards_path)
    assert boards[0]["record_type"] == "ats_company_board"
    assert boards[0]["platform"] == "recruitee"
    assert boards[0]["platform_company_slug"] == "acme-ai"
    assert boards[0]["board_url"] == "https://acme-ai.recruitee.com"

    manifest = read_json(result.manifest_path)
    assert manifest["platform"] == "recruitee"
    assert manifest["board_count"] == 1
    assert manifest["boards_file"] == result.boards_path.as_posix()


def test_generate_recruitee_discovery_queries_uses_shared_exhaustive_depth() -> None:
    queries = generate_recruitee_discovery_queries(
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
        query.search_query == 'site:*.recruitee.com "AI Engineer" "Amsterdam"'
        for query in queries
    )


def test_recruitee_client_fetches_listing_and_detail_endpoints() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "GET"
        assert "recruitee" in request.headers["User-Agent"]
        if str(request.url) == "https://acme-ai.recruitee.com/api/offers/":
            return httpx.Response(200, json={"offers": [{"id": 123}]})
        return httpx.Response(200, json={"offer": {"id": 123, "title": "AI Engineer"}})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as http_client:
        client = RecruiteeClient(http_client=http_client, request_delay_seconds=0)
        listing = client.fetch_board("https://acme-ai.recruitee.com")
        detail = client.fetch_offer_detail(
            board_url_or_slug="https://acme-ai.recruitee.com",
            offer_identifier="123",
        )

    assert [str(request.url) for request in requests] == [
        "https://acme-ai.recruitee.com/api/offers/",
        "https://acme-ai.recruitee.com/api/offers/123",
    ]
    assert listing.response == {"offers": [{"id": 123}]}
    assert detail.response == {"offer": {"id": 123, "title": "AI Engineer"}}


def test_collect_recruitee_boards_writes_raw_response_details_and_manifest(tmp_path) -> None:
    client = FakeRecruiteeClient(
        _sample_recruitee_response(),
        _sample_recruitee_detail_responses(),
    )
    timestamps = iter(
        [
            "2026-06-16T10:00:00Z",
            "2026-06-16T10:00:01Z",
            "2026-06-16T10:00:02Z",
        ]
    )

    result = collect_recruitee_boards(
        ["https://acme-ai.recruitee.com/o/senior-ai-engineer"],
        client=client,  # type: ignore[arg-type]
        data_dir=tmp_path,
        clock=lambda: next(timestamps),
    )

    assert result.successful_count == 1
    assert result.board_count == 1
    assert result.error_count == 0
    assert client.fetched_details == [
        ("https://acme-ai.recruitee.com", "123"),
        ("https://acme-ai.recruitee.com", "125"),
    ]

    raw_record = read_json(Path(result.result_files[0]))
    assert raw_record["record_type"] == "raw_ats_response"
    assert raw_record["platform"] == "recruitee"
    assert raw_record["platform_company_slug"] == "acme-ai"
    assert raw_record["request_params"] == {}
    assert raw_record["response_format"] == "json"
    assert raw_record["endpoint"] == "https://acme-ai.recruitee.com/api/offers/"
    assert sorted(raw_record["offer_detail_responses"]) == ["123", "125"]
    assert raw_record["offer_detail_errors"] == []
    assert read_json(result.manifest_path)["result_files"] == result.result_files


def test_collect_recruitee_boards_records_detail_errors_without_failing_board(
    tmp_path,
) -> None:
    detail_responses: dict[str, dict[str, Any] | Exception] = {
        **_sample_recruitee_detail_responses(),
        "125": ValueError("detail unavailable"),
    }
    client = FakeRecruiteeClient(_sample_recruitee_response(), detail_responses)
    timestamps = iter(
        [
            "2026-06-16T10:00:00Z",
            "2026-06-16T10:00:01Z",
            "2026-06-16T10:00:02Z",
        ]
    )

    result = collect_recruitee_boards(
        ["acme-ai"],
        client=client,  # type: ignore[arg-type]
        data_dir=tmp_path,
        clock=lambda: next(timestamps),
    )

    assert result.successful_count == 1
    assert result.error_count == 1
    assert result.errors[0]["error_scope"] == "offer_detail"
    assert result.errors[0]["platform_job_id"] == "125"
    raw_record = read_json(Path(result.result_files[0]))
    assert raw_record["offer_detail_errors"] == result.errors


def test_normalize_raw_recruitee_file_keeps_title_ai_signals_and_descriptions(
    tmp_path,
) -> None:
    board = recruitee_board_from_slug("acme-ai")
    raw_record = build_raw_recruitee_response_record(
        board=board,
        response=_sample_recruitee_response(),
        offer_detail_responses=_sample_recruitee_detail_responses(),
        collected_at="2026-06-16T10:00:01Z",
    )
    raw_path = write_raw_ats_response(
        raw_record,
        platform_company_slug="acme-ai",
        collection_date="2026-06-16",
        data_dir=tmp_path,
        platform="recruitee",
    )

    candidates = normalize_raw_ats_file(raw_path)

    assert [candidate["job_title_raw"] for candidate in candidates] == [
        "Senior AI Engineer",
        "AI Product Manager",
    ]
    assert candidates[0]["source"] == "recruitee"
    assert candidates[0]["source_mode"] == "public_job_board_endpoint"
    assert candidates[0]["source_url"] == (
        "https://acme-ai.recruitee.com/o/senior-ai-engineer"
    )
    assert candidates[0]["job_url"] == (
        "https://acme-ai.recruitee.com/o/senior-ai-engineer"
    )
    assert candidates[0]["apply_url"] == (
        "https://acme-ai.recruitee.com/o/senior-ai-engineer/apply"
    )
    assert candidates[0]["board_url"] == "https://acme-ai.recruitee.com"
    assert candidates[0]["platform_company_slug"] == "acme-ai"
    assert candidates[0]["platform_job_id"] == "123"
    assert candidates[0]["company_normalized"] == "Acme AI"
    assert candidates[0]["job_title_normalized"] == "AI Engineer"
    assert candidates[0]["role_group"] == "AI Execution Role"
    assert candidates[0]["team"] == "Engineering"
    assert candidates[0]["department"] == "Engineering"
    assert candidates[0]["location"] == "Amsterdam, Netherlands"
    assert candidates[0]["country"] == "Netherlands"
    assert candidates[0]["country_code"] == "nl"
    assert candidates[0]["job_countries"] == ["Netherlands"]
    assert candidates[0]["job_country_codes"] == ["nl"]
    assert candidates[0]["job_locations_raw"] == [
        "Netherlands, Noord-Holland, Amsterdam",
        "Amsterdam, Netherlands",
        "Amsterdam",
        "Netherlands",
        "NL",
    ]
    assert candidates[0]["workplace_type"] == "remote"
    assert candidates[0]["remote"] is True
    assert candidates[0]["hybrid"] is False
    assert candidates[0]["on_site"] is False
    assert candidates[0]["employment_type"] == "full-time"
    assert candidates[0]["compensation"] == {"currency": "EUR", "min": 70000, "max": 90000}
    assert candidates[0]["description"] == "Build AI systems.\n\nPython and ML experience."
    assert candidates[0]["requirements"] == "Python and ML experience."
    assert candidates[0]["source_published_at"] == "2026-06-16T00:00:00Z"
    assert candidates[0]["source_updated_at"] == "2026-06-17T00:00:00Z"
    assert candidates[0]["evidence_quality"] == "title_only_ats_listing"
    assert candidates[1]["role_group"] == "AI Product Role"
    assert candidates[1]["country"] == "Netherlands"
    assert candidates[1]["country_code"] == "nl"
    assert candidates[1]["workplace_type"] == "hybrid"
    assert candidates[1]["description"] == "Shape AI products."


def test_process_collection_includes_recruitee_raw_files(tmp_path) -> None:
    board = recruitee_board_from_slug("acme-ai")
    raw_record = build_raw_recruitee_response_record(
        board=board,
        response=_sample_recruitee_response(),
        offer_detail_responses=_sample_recruitee_detail_responses(),
        collected_at="2026-06-16T10:00:01Z",
    )
    write_raw_ats_response(
        raw_record,
        platform_company_slug="acme-ai",
        collection_date="2026-06-16",
        data_dir=tmp_path,
        platform="recruitee",
    )

    result = process_collection("2026-06-16", data_dir=tmp_path)

    assert result.raw_file_count == 1
    assert result.candidate_count == 2
    assert result.deduped_candidate_count == 2
    assert result.company_count == 1

    candidates = read_jsonl(result.job_candidates_path)
    assert candidates[0]["source"] == "recruitee"
    assert candidates[0]["description"] == "Build AI systems.\n\nPython and ML experience."

    companies = read_jsonl(result.companies_path)
    assert companies[0]["company"] == "Acme AI"
    assert companies[0]["countries"] == ["Netherlands"]
    assert companies[0]["sources"] == ["recruitee"]
    assert companies[0]["matched_search_terms"] == [
        "AI Engineer",
        "AI Product Manager",
    ]


def test_build_recruitee_endpoints_validate_slug_and_quote_offer_identifier() -> None:
    assert build_recruitee_offers_endpoint("Acme-AI") == (
        "https://acme-ai.recruitee.com/api/offers/"
    )
    assert build_recruitee_offer_detail_endpoint(
        platform_company_slug="Acme-AI",
        offer_identifier="senior ai engineer",
    ) == "https://acme-ai.recruitee.com/api/offers/senior%20ai%20engineer"

    with pytest.raises(ValueError):
        build_recruitee_offers_endpoint("Acme AI")
    with pytest.raises(ValueError):
        build_recruitee_offer_detail_endpoint(
            platform_company_slug="acme_ai",
            offer_identifier="senior-ai-engineer",
        )
    with pytest.raises(ValueError):
        recruitee_board_from_slug("support")
