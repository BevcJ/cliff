from pathlib import Path
from typing import Any

import httpx

from ai_hiring_radar.config import load_countries_config
from ai_hiring_radar.normalize import normalize_raw_ats_file, process_collection
from ai_hiring_radar.query_builder import LocationDepth
from ai_hiring_radar.sources.ats_discovery import AtsDiscoveryDepth
from ai_hiring_radar.sources.personio import (
    PersonioClient,
    PersonioFetchResult,
    build_personio_xml_endpoint,
    build_raw_personio_response_record,
    collect_personio_boards,
    discover_personio_boards,
    generate_personio_discovery_queries,
    parse_personio_board_url,
    personio_board_from_slug,
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


class FakePersonioClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.fetched_boards: list[str] = []

    def fetch_board(self, board_url_or_slug: str) -> PersonioFetchResult:
        self.fetched_boards.append(board_url_or_slug)
        return PersonioFetchResult(
            response=self.response,
            endpoint="https://acme-ai.jobs.personio.com/xml?language=en",
            language="en",
        )


def _sample_personio_response() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<workzag-jobs>
  <position>
    <id>job-ai-engineer</id>
    <name>Senior AI Engineer</name>
    <office>Amsterdam, Netherlands</office>
    <department>Engineering</department>
    <recruitingCategory>Engineering</recruitingCategory>
    <employmentType>permanent</employmentType>
    <schedule>full-time</schedule>
    <jobUrl>https://acme-ai.jobs.personio.com/job/job-ai-engineer</jobUrl>
    <jobDescriptions>
      <jobDescription>
        <name>Your mission</name>
        <value><![CDATA[Build AI systems.]]></value>
      </jobDescription>
      <jobDescription>
        <name>Your profile</name>
        <value><![CDATA[Python and ML experience.]]></value>
      </jobDescription>
    </jobDescriptions>
  </position>
  <position>
    <id>job-backend</id>
    <name>Backend Engineer</name>
    <office>Amsterdam, Netherlands</office>
    <department>Engineering</department>
    <employmentType>permanent</employmentType>
    <schedule>full-time</schedule>
  </position>
  <position>
    <id>job-ai-trainer</id>
    <name>Machine Learning Engineer - AI Trainer - Freelance</name>
    <office>Amsterdam, Netherlands</office>
    <department>Engineering</department>
    <employmentType>contract</employmentType>
    <schedule>freelance</schedule>
  </position>
  <position>
    <id>job-ai-product</id>
    <name>AI Product Manager</name>
    <office>Remote - Netherlands</office>
    <department>Product</department>
    <recruitingCategory>Product</recruitingCategory>
    <employmentType>permanent</employmentType>
    <schedule>full-time</schedule>
    <jobUrl>https://acme-ai.jobs.personio.com/job/job-ai-product</jobUrl>
    <jobDescriptions>
      <jobDescription>
        <name>Your mission</name>
        <value><![CDATA[Shape AI products.]]></value>
      </jobDescription>
    </jobDescriptions>
  </position>
</workzag-jobs>"""


def test_parse_personio_board_url_extracts_company_subdomain() -> None:
    board = parse_personio_board_url("https://acme.jobs.personio.com/job/123")

    assert board is not None
    assert board.platform_company_slug == "acme"
    assert board.board_url == "https://acme.jobs.personio.com"
    assert parse_personio_board_url("acme.jobs.personio.com/jobs") is not None
    assert parse_personio_board_url("https://jobs.personio.com/acme") is None
    assert parse_personio_board_url("https://example.com/acme") is None


def test_discover_personio_boards_writes_deduped_board_records(tmp_path) -> None:
    query = generate_personio_discovery_queries(
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
                        "link": "https://acme-ai.jobs.personio.com/job/job-ai-engineer",
                        "snippet": "Acme AI is hiring in Amsterdam.",
                    },
                    {
                        "position": 2,
                        "title": "Acme AI careers",
                        "link": "https://acme-ai.jobs.personio.com",
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

    result = discover_personio_boards(
        [query],
        client=client,
        data_dir=tmp_path,
        clock=lambda: next(timestamps),
    )

    assert result.query_count == 1
    assert result.board_count == 1
    boards = read_jsonl(result.boards_path)
    assert boards[0]["record_type"] == "ats_company_board"
    assert boards[0]["platform"] == "personio"
    assert boards[0]["platform_company_slug"] == "acme-ai"
    assert boards[0]["board_url"] == "https://acme-ai.jobs.personio.com"

    manifest = read_json(result.manifest_path)
    assert manifest["platform"] == "personio"
    assert manifest["board_count"] == 1
    assert manifest["boards_file"] == result.boards_path.as_posix()


def test_generate_personio_discovery_queries_uses_shared_exhaustive_depth() -> None:
    queries = generate_personio_discovery_queries(
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
        query.search_query == 'site:*.jobs.personio.com "AI Engineer" "Amsterdam"'
        for query in queries
    )


def test_personio_client_gets_public_xml_endpoint() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "GET"
        assert str(request.url) == "https://acme-ai.jobs.personio.com/xml?language=en"
        assert "personio" in request.headers["User-Agent"]
        return httpx.Response(200, text="<workzag-jobs />")

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as http_client:
        client = PersonioClient(http_client=http_client)
        result = client.fetch_board("https://acme-ai.jobs.personio.com")

    assert len(requests) == 1
    assert result.response == "<workzag-jobs />"
    assert result.endpoint == "https://acme-ai.jobs.personio.com/xml?language=en"
    assert result.language == "en"


def test_collect_personio_boards_writes_raw_response_and_manifest(tmp_path) -> None:
    client = FakePersonioClient(_sample_personio_response())
    timestamps = iter(
        [
            "2026-06-16T10:00:00Z",
            "2026-06-16T10:00:01Z",
            "2026-06-16T10:00:02Z",
        ]
    )

    result = collect_personio_boards(
        ["https://acme-ai.jobs.personio.com/job/job-ai-engineer"],
        client=client,  # type: ignore[arg-type]
        data_dir=tmp_path,
        clock=lambda: next(timestamps),
    )

    assert result.successful_count == 1
    assert result.board_count == 1
    assert result.error_count == 0
    raw_record = read_json(Path(result.result_files[0]))
    assert raw_record["record_type"] == "raw_ats_response"
    assert raw_record["platform"] == "personio"
    assert raw_record["platform_company_slug"] == "acme-ai"
    assert raw_record["request_params"] == {"language": "en"}
    assert raw_record["response_format"] == "xml"
    assert raw_record["endpoint"] == "https://acme-ai.jobs.personio.com/xml?language=en"
    assert raw_record["title_prefilter"] == {
        "mode": "strict_title",
        "source": "listing_title",
        "source_field": "name",
        "listed_count": 4,
        "matched_count": 2,
        "skipped_count": 2,
    }
    assert read_json(result.manifest_path)["result_files"] == result.result_files


def test_normalize_raw_personio_file_keeps_title_ai_signals_only(tmp_path) -> None:
    board = personio_board_from_slug("acme-ai")
    raw_record = build_raw_personio_response_record(
        board=board,
        response=_sample_personio_response(),
        collected_at="2026-06-16T10:00:01Z",
    )
    raw_path = write_raw_ats_response(
        raw_record,
        platform_company_slug="acme-ai",
        collection_date="2026-06-16",
        data_dir=tmp_path,
        platform="personio",
    )

    candidates = normalize_raw_ats_file(raw_path)

    assert [candidate["job_title_raw"] for candidate in candidates] == [
        "Senior AI Engineer",
        "AI Product Manager",
    ]
    assert candidates[0]["source"] == "personio"
    assert candidates[0]["source_mode"] == "public_job_board_endpoint"
    assert candidates[0]["source_url"] == (
        "https://acme-ai.jobs.personio.com/job/job-ai-engineer"
    )
    assert candidates[0]["job_url"] == (
        "https://acme-ai.jobs.personio.com/job/job-ai-engineer"
    )
    assert candidates[0]["board_url"] == "https://acme-ai.jobs.personio.com"
    assert candidates[0]["platform_company_slug"] == "acme-ai"
    assert candidates[0]["platform_job_id"] == "job-ai-engineer"
    assert candidates[0]["company_normalized"] == "Acme Ai"
    assert candidates[0]["job_title_normalized"] == "AI Engineer"
    assert candidates[0]["role_group"] == "AI Execution Role"
    assert candidates[0]["team"] == "Engineering"
    assert candidates[0]["department"] == "Engineering"
    assert candidates[0]["location"] == "Amsterdam, Netherlands"
    assert candidates[0]["country"] == "Netherlands"
    assert candidates[0]["country_code"] == "nl"
    assert candidates[0]["job_countries"] == ["Netherlands"]
    assert candidates[0]["job_country_codes"] == ["nl"]
    assert candidates[0]["job_locations_raw"] == ["Amsterdam, Netherlands"]
    assert candidates[0]["employment_type"] == "permanent"
    assert candidates[0]["schedule"] == "full-time"
    assert candidates[0]["recruiting_category"] == "Engineering"
    assert candidates[0]["description"] == "Build AI systems.\n\nPython and ML experience."
    assert candidates[0]["job_description_sections"] == [
        {"name": "Your mission", "value": "Build AI systems."},
        {"name": "Your profile", "value": "Python and ML experience."},
    ]
    assert candidates[0]["evidence_quality"] == "title_only_ats_listing"
    assert candidates[1]["role_group"] == "AI Product Role"
    assert candidates[1]["source_url"] == (
        "https://acme-ai.jobs.personio.com/job/job-ai-product"
    )
    assert candidates[1]["job_url"] == (
        "https://acme-ai.jobs.personio.com/job/job-ai-product"
    )
    assert candidates[1]["board_url"] == "https://acme-ai.jobs.personio.com"
    assert candidates[1]["job_countries"] == ["Netherlands"]


def test_process_collection_includes_personio_raw_files(tmp_path) -> None:
    board = personio_board_from_slug("acme-ai")
    raw_record = build_raw_personio_response_record(
        board=board,
        response=_sample_personio_response(),
        collected_at="2026-06-16T10:00:01Z",
    )
    write_raw_ats_response(
        raw_record,
        platform_company_slug="acme-ai",
        collection_date="2026-06-16",
        data_dir=tmp_path,
        platform="personio",
    )

    result = process_collection("2026-06-16", data_dir=tmp_path)

    assert result.raw_file_count == 1
    assert result.candidate_count == 2
    assert result.deduped_candidate_count == 2
    assert result.company_count == 1

    candidates = read_jsonl(result.job_candidates_path)
    assert candidates[0]["source"] == "personio"
    assert candidates[0]["source_url"] == (
        "https://acme-ai.jobs.personio.com/job/job-ai-engineer"
    )

    companies = read_jsonl(result.companies_path)
    assert companies[0]["company"] == "Acme Ai"
    assert companies[0]["countries"] == ["Netherlands"]
    assert companies[0]["sources"] == ["personio"]
    assert companies[0]["matched_search_terms"] == [
        "AI Engineer",
        "AI Product Manager",
    ]


def test_build_personio_xml_endpoint_quotes_language() -> None:
    assert build_personio_xml_endpoint("acme-ai", language="en-US") == (
        "https://acme-ai.jobs.personio.com/xml?language=en-US"
    )
