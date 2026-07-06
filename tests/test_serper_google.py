import json
from pathlib import Path
from typing import Any

import httpx

from ai_hiring_radar.config import load_countries_config
from ai_hiring_radar.query_builder import generate_search_queries
from ai_hiring_radar.sources.serper_google import (
    SERPER_SEARCH_URL,
    SerperGoogleClient,
    build_raw_search_record,
    collect_searches,
)
from ai_hiring_radar.storage_json import read_json


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


def _sample_query():
    return generate_search_queries(
        countries_config=load_countries_config(),
        country_codes=["nl"],
        role_terms=["AI Product Manager"],
    )[0]


def test_serper_client_posts_json_and_normalizes_organic_results() -> None:
    search_query = _sample_query()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "POST"
        assert str(request.url) == SERPER_SEARCH_URL
        assert request.headers["X-API-KEY"] == "test-key"
        assert request.headers["Content-Type"] == "application/json"
        assert json.loads(request.content) == search_query.request_params
        return httpx.Response(
            200,
            json={
                "organic": [
                    {
                        "title": "AI Product Manager - Example",
                        "link": "https://www.linkedin.com/jobs/view/123",
                        "snippet": "Example is hiring.",
                        "position": 1,
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as http_client:
        client = SerperGoogleClient(api_key="test-key", http_client=http_client)
        payload = client.search(search_query)

    assert len(requests) == 1
    assert payload["organic_results"] == payload["organic"]


def test_raw_search_record_is_self_describing_and_redacts_api_keys() -> None:
    search_query = _sample_query()

    record = build_raw_search_record(
        search_query=search_query,
        collected_at="2026-06-13T10:30:00Z",
        response={
            "organic_results": [{"title": "AI Product Manager - Example"}],
            "request_headers": {"X-API-KEY": "secret-key"},
        },
    )

    assert record["record_type"] == "raw_search_response"
    assert record["source"] == "serper_google"
    assert record["source_mode"] == "linkedin_safe_search"
    assert record["country_code"] == "nl"
    assert record["country"] == "Netherlands"
    assert record["search_location_label"] == "Netherlands"
    assert record["query_location"] == "Netherlands"
    assert record["serper_location"] == "Netherlands"
    assert record["role_search_term"] == "AI Product Manager"
    assert record["search_query"] == (
        '"AI Product Manager" site:linkedin.com/jobs/view Netherlands'
    )
    assert "api_key" not in record["request_params"]
    assert record["response"]["request_headers"]["X-API-KEY"] == "[redacted]"


def test_collect_searches_writes_raw_files_and_manifest(tmp_path) -> None:
    queries = generate_search_queries(
        countries_config=load_countries_config(),
        country_codes=["nl"],
        role_terms=["AI Product Manager", "LLM Engineer"],
    )
    client = FakeSearchClient(
        [
            {"organic_results": [{"title": "AI Product Manager - Example"}]},
            RuntimeError("temporary Serper failure"),
        ]
    )
    timestamps = iter(
        [
            "2026-06-13T10:30:00Z",
            "2026-06-13T10:30:01Z",
            "2026-06-13T10:30:02Z",
        ]
    )

    result = collect_searches(
        queries,
        client=client,
        data_dir=tmp_path,
        clock=lambda: next(timestamps),
    )

    assert result.query_count == 2
    assert result.successful_count == 1
    assert result.error_count == 1
    assert result.manifest_path == (
        tmp_path / "raw" / "searches" / "2026-06-13" / "serper_google" / "manifest.json"
    )

    raw_path = Path(result.result_files[0])
    raw_record = read_json(raw_path)
    assert raw_path.name == "nl_ai-product-manager_netherlands.json"
    assert raw_record["record_type"] == "raw_search_response"
    assert raw_record["collected_at"] == "2026-06-13T10:30:01Z"
    assert "api_key" not in raw_record["request_params"]

    manifest = read_json(result.manifest_path)
    assert manifest == {
        "record_type": "collection_manifest",
        "source": "serper_google",
        "source_mode": "linkedin_safe_search",
        "started_at": "2026-06-13T10:30:00Z",
        "finished_at": "2026-06-13T10:30:02Z",
        "countries": ["nl"],
        "search_locations": ["Netherlands"],
        "query_count": 2,
        "result_files": [raw_path.as_posix()],
        "errors": [
            {
                "country_code": "nl",
                "country": "Netherlands",
                "search_location_label": "Netherlands",
                "query_location": "Netherlands",
                "serper_location": "Netherlands",
                "role_search_term": "LLM Engineer",
                "search_query": '"LLM Engineer" site:linkedin.com/jobs/view Netherlands',
                "request_params": {
                    "q": '"LLM Engineer" site:linkedin.com/jobs/view Netherlands',
                    "location": "Netherlands",
                    "gl": "nl",
                    "hl": "en",
                    "num": 10,
                },
                "error": "temporary Serper failure",
                "error_type": "RuntimeError",
            }
        ],
    }
