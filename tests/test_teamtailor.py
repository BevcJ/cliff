from pathlib import Path
from typing import Any

import httpx
import pytest

from ai_hiring_radar.config import load_countries_config
from ai_hiring_radar.normalize import normalize_raw_ats_file, process_collection
from ai_hiring_radar.query_builder import LocationDepth
from ai_hiring_radar.sources.ats_discovery import AtsDiscoveryDepth
from ai_hiring_radar.sources.teamtailor import (
    TeamtailorClient,
    TeamtailorFetchResult,
    build_raw_teamtailor_response_record,
    build_teamtailor_rss_endpoint,
    collect_teamtailor_boards,
    discover_teamtailor_boards,
    generate_teamtailor_discovery_queries,
    parse_teamtailor_board_url,
    teamtailor_board_from_slug,
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


class FakeTeamtailorClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.fetched_boards: list[str] = []

    def fetch_board(self, board_url_or_slug: str) -> TeamtailorFetchResult:
        self.fetched_boards.append(board_url_or_slug)
        return TeamtailorFetchResult(
            response=self.response,
            endpoint="https://acme-ai.teamtailor.com/jobs.rss",
        )


def _sample_teamtailor_response() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:tt="https://teamtailor.com/locations">
  <channel>
    <title>Acme AI</title>
    <description>Current job openings</description>
    <link>https://acme-ai.teamtailor.com/jobs</link>
    <item>
      <title>Senior AI Engineer</title>
      <description><![CDATA[<p>Build AI systems.</p><p>Python and ML experience.</p>]]></description>
      <pubDate>Tue, 16 Jun 2026 10:00:00 +0200</pubDate>
      <link>https://acme-ai.teamtailor.com/jobs/123-senior-ai-engineer</link>
      <remoteStatus>hybrid</remoteStatus>
      <guid>job-ai-engineer</guid>
      <tt:locations>
        <tt:location>
          <tt:name>Amsterdam</tt:name>
          <tt:city>Amsterdam</tt:city>
          <tt:country>Netherlands</tt:country>
        </tt:location>
      </tt:locations>
      <tt:department>Engineering</tt:department>
      <tt:role>Engineering</tt:role>
      <tt:division>Product</tt:division>
    </item>
    <item>
      <title>Backend Engineer</title>
      <description><![CDATA[<p>Build APIs.</p>]]></description>
      <pubDate>Tue, 16 Jun 2026 11:00:00 +0200</pubDate>
      <link>https://acme-ai.teamtailor.com/jobs/124-backend-engineer</link>
      <remoteStatus>none</remoteStatus>
      <guid>job-backend</guid>
      <tt:locations>
        <tt:location>
          <tt:name>Amsterdam</tt:name>
          <tt:city>Amsterdam</tt:city>
          <tt:country>Netherlands</tt:country>
        </tt:location>
      </tt:locations>
      <tt:department>Engineering</tt:department>
    </item>
    <item>
      <title>AI Product Manager</title>
      <description><![CDATA[<p>Shape AI products.</p>]]></description>
      <pubDate>Wed, 17 Jun 2026 10:00:00 +0200</pubDate>
      <link>https://acme-ai.teamtailor.com/jobs/125-ai-product-manager</link>
      <remoteStatus>remote</remoteStatus>
      <guid>job-ai-product</guid>
      <tt:locations>
        <tt:location>
          <tt:name>Remote Netherlands</tt:name>
          <tt:city>Amsterdam</tt:city>
          <tt:country>Netherlands</tt:country>
        </tt:location>
        <tt:location>
          <tt:name>London</tt:name>
          <tt:city>London</tt:city>
          <tt:country>United Kingdom</tt:country>
        </tt:location>
      </tt:locations>
      <tt:department>Product</tt:department>
      <tt:role>Product Manager</tt:role>
      <tt:division>Product</tt:division>
    </item>
  </channel>
</rss>"""


def test_parse_teamtailor_board_url_extracts_company_subdomain() -> None:
    board = parse_teamtailor_board_url("https://acme.teamtailor.com/jobs/123")

    assert board is not None
    assert board.platform_company_slug == "acme"
    assert board.board_url == "https://acme.teamtailor.com"
    assert parse_teamtailor_board_url("acme.teamtailor.com/jobs") is not None
    assert parse_teamtailor_board_url("https://teamtailor.com/acme") is None
    assert parse_teamtailor_board_url("https://example.com/acme") is None


def test_discover_teamtailor_boards_writes_deduped_board_records(tmp_path) -> None:
    query = generate_teamtailor_discovery_queries(
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
                        "link": "https://acme-ai.teamtailor.com/jobs/123-ai-engineer",
                        "snippet": "Acme AI is hiring in Amsterdam.",
                    },
                    {
                        "position": 2,
                        "title": "Acme AI careers",
                        "link": "https://acme-ai.teamtailor.com",
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

    result = discover_teamtailor_boards(
        [query],
        client=client,
        data_dir=tmp_path,
        clock=lambda: next(timestamps),
    )

    assert result.query_count == 1
    assert result.board_count == 1
    boards = read_jsonl(result.boards_path)
    assert boards[0]["record_type"] == "ats_company_board"
    assert boards[0]["platform"] == "teamtailor"
    assert boards[0]["platform_company_slug"] == "acme-ai"
    assert boards[0]["board_url"] == "https://acme-ai.teamtailor.com"

    manifest = read_json(result.manifest_path)
    assert manifest["platform"] == "teamtailor"
    assert manifest["board_count"] == 1
    assert manifest["boards_file"] == result.boards_path.as_posix()


def test_generate_teamtailor_discovery_queries_uses_shared_exhaustive_depth() -> None:
    queries = generate_teamtailor_discovery_queries(
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
        query.search_query == 'site:*.teamtailor.com "AI Engineer" "Amsterdam"'
        for query in queries
    )


def test_teamtailor_client_gets_public_rss_endpoint() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "GET"
        assert str(request.url) == "https://acme-ai.teamtailor.com/jobs.rss"
        assert "teamtailor" in request.headers["User-Agent"]
        return httpx.Response(200, text="<rss><channel /></rss>")

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as http_client:
        client = TeamtailorClient(
            http_client=http_client,
            request_delay_seconds=0,
            max_retries=0,
        )
        result = client.fetch_board("https://acme-ai.teamtailor.com")

    assert len(requests) == 1
    assert result.response == "<rss><channel /></rss>"
    assert result.endpoint == "https://acme-ai.teamtailor.com/jobs.rss"


def test_collect_teamtailor_boards_writes_raw_response_and_manifest(tmp_path) -> None:
    client = FakeTeamtailorClient(_sample_teamtailor_response())
    timestamps = iter(
        [
            "2026-06-16T10:00:00Z",
            "2026-06-16T10:00:01Z",
            "2026-06-16T10:00:02Z",
        ]
    )

    result = collect_teamtailor_boards(
        ["https://acme-ai.teamtailor.com/jobs/123-ai-engineer"],
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
    assert raw_record["platform"] == "teamtailor"
    assert raw_record["platform_company_slug"] == "acme-ai"
    assert raw_record["response_format"] == "rss_xml"
    assert raw_record["endpoint"] == "https://acme-ai.teamtailor.com/jobs.rss"
    assert raw_record["title_prefilter"] == {
        "mode": "strict_title",
        "source": "listing_title",
        "source_field": "title",
        "listed_count": 3,
        "matched_count": 2,
        "skipped_count": 1,
    }
    assert raw_record["response"] == _sample_teamtailor_response()
    manifest = read_json(result.manifest_path)
    assert manifest["result_files"] == result.result_files
    assert manifest["written_files"] == result.written_files
    assert manifest["resumed_files"] == result.resumed_files


@pytest.mark.parametrize("invalid_file", ["invalid", "corrupt", "mismatched"])
def test_collect_teamtailor_boards_refetches_invalid_resume_files(
    tmp_path,
    invalid_file: str,
) -> None:
    collection_date = "2026-06-20"
    raw_record = build_raw_teamtailor_response_record(
        board=teamtailor_board_from_slug("acme-ai"),
        response=_sample_teamtailor_response(),
        collected_at="2026-06-19T10:00:00Z",
    )
    if invalid_file == "invalid":
        raw_record.pop("record_type")
    elif invalid_file == "mismatched":
        raw_record["platform_company_slug"] = "other-company"
    raw_path = write_raw_ats_response(
        raw_record,
        platform_company_slug="acme-ai",
        collection_date=collection_date,
        data_dir=tmp_path,
        platform="teamtailor",
    )
    if invalid_file == "corrupt":
        raw_path.write_text("{not-json", encoding="utf-8")

    client = FakeTeamtailorClient(_sample_teamtailor_response())
    timestamps = iter(
        [
            "2026-06-21T10:00:00Z",
            "2026-06-21T10:00:01Z",
            "2026-06-21T10:00:02Z",
        ]
    )
    result = collect_teamtailor_boards(
        ["acme-ai"],
        client=client,  # type: ignore[arg-type]
        collection_date=collection_date,
        data_dir=tmp_path,
        clock=lambda: next(timestamps),
    )

    assert client.fetched_boards == ["https://acme-ai.teamtailor.com"]
    assert result.result_files == [raw_path.as_posix()]
    assert result.written_files == [raw_path.as_posix()]
    assert result.resumed_files == []
    assert read_json(raw_path)["platform_company_slug"] == "acme-ai"


def test_normalize_raw_teamtailor_file_keeps_title_ai_signals_with_description(
    tmp_path,
) -> None:
    board = teamtailor_board_from_slug("acme-ai")
    raw_record = build_raw_teamtailor_response_record(
        board=board,
        response=_sample_teamtailor_response(),
        collected_at="2026-06-16T10:00:01Z",
    )
    raw_path = write_raw_ats_response(
        raw_record,
        platform_company_slug="acme-ai",
        collection_date="2026-06-16",
        data_dir=tmp_path,
        platform="teamtailor",
    )

    candidates = normalize_raw_ats_file(raw_path)

    assert [candidate["job_title_raw"] for candidate in candidates] == [
        "Senior AI Engineer",
        "AI Product Manager",
    ]
    assert candidates[0]["source"] == "teamtailor"
    assert candidates[0]["source_mode"] == "public_job_board_endpoint"
    assert candidates[0]["source_url"] == (
        "https://acme-ai.teamtailor.com/jobs/123-senior-ai-engineer"
    )
    assert candidates[0]["job_url"] == (
        "https://acme-ai.teamtailor.com/jobs/123-senior-ai-engineer"
    )
    assert candidates[0]["board_url"] == "https://acme-ai.teamtailor.com"
    assert candidates[0]["platform_company_slug"] == "acme-ai"
    assert candidates[0]["platform_job_id"] == "job-ai-engineer"
    assert candidates[0]["company_normalized"] == "Acme Ai"
    assert candidates[0]["job_title_normalized"] == "AI Engineer"
    assert candidates[0]["role_group"] == "AI Execution Role"
    assert candidates[0]["team"] == "Engineering"
    assert candidates[0]["department"] == "Engineering"
    assert candidates[0]["teamtailor_role"] == "Engineering"
    assert candidates[0]["division"] == "Product"
    assert candidates[0]["location"] == "Amsterdam, Netherlands"
    assert candidates[0]["country"] == "Netherlands"
    assert candidates[0]["country_code"] == "nl"
    assert candidates[0]["job_countries"] == ["Netherlands"]
    assert candidates[0]["job_country_codes"] == ["nl"]
    assert candidates[0]["job_locations_raw"] == ["Amsterdam, Netherlands"]
    assert candidates[0]["workplace_type"] == "hybrid"
    assert candidates[0]["remote_status"] == "hybrid"
    assert candidates[0]["description"] == "Build AI systems. Python and ML experience."
    assert "<p>Build AI systems.</p>" in candidates[0]["description_html"]
    assert candidates[0]["source_created_at"] == "2026-06-16T10:00:00+02:00"
    assert candidates[0]["evidence_quality"] == "title_only_ats_listing"
    assert candidates[1]["role_group"] == "AI Product Role"
    assert candidates[1]["job_countries"] == ["Netherlands", "United Kingdom"]
    assert candidates[1]["job_country_codes"] == ["nl", "uk"]
    assert candidates[1]["workplace_type"] == "remote"


def test_process_collection_includes_teamtailor_raw_files(tmp_path) -> None:
    board = teamtailor_board_from_slug("acme-ai")
    raw_record = build_raw_teamtailor_response_record(
        board=board,
        response=_sample_teamtailor_response(),
        collected_at="2026-06-16T10:00:01Z",
    )
    write_raw_ats_response(
        raw_record,
        platform_company_slug="acme-ai",
        collection_date="2026-06-16",
        data_dir=tmp_path,
        platform="teamtailor",
    )

    result = process_collection("2026-06-16", data_dir=tmp_path)

    assert result.raw_file_count == 1
    assert result.candidate_count == 2
    assert result.deduped_candidate_count == 2
    assert result.company_count == 1

    candidates = read_jsonl(result.job_candidates_path)
    assert candidates[0]["source"] == "teamtailor"
    assert candidates[0]["description"] == "Build AI systems. Python and ML experience."

    companies = read_jsonl(result.companies_path)
    assert companies[0]["company"] == "Acme Ai"
    assert companies[0]["countries"] == ["Netherlands", "United Kingdom"]
    assert companies[0]["sources"] == ["teamtailor"]
    assert companies[0]["matched_search_terms"] == [
        "AI Engineer",
        "AI Product Manager",
    ]


def test_build_teamtailor_rss_endpoint_normalizes_slug() -> None:
    assert build_teamtailor_rss_endpoint("Acme-AI") == (
        "https://acme-ai.teamtailor.com/jobs.rss"
    )
