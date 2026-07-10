import json
from dataclasses import dataclass
from typing import Any

import httpx

from ai_hiring_radar.sources.serper_google import (
    SERPER_SEARCH_URL,
    SerperGoogleClient,
    normalize_serper_response,
    redact_secret_fields,
)


@dataclass
class SearchRequest:
    request_params: dict[str, str | int]


def test_serper_client_posts_json_and_normalizes_organic_results() -> None:
    search_query = SearchRequest(
        request_params={
            "q": "site:jobs.ashbyhq.com AI Engineer Netherlands",
            "location": "Netherlands",
            "gl": "nl",
            "hl": "en",
            "num": 10,
        }
    )
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
                        "title": "AI Engineer - Example",
                        "link": "https://jobs.ashbyhq.com/example",
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


def test_normalize_serper_response_preserves_existing_organic_results() -> None:
    payload: dict[str, Any] = {"organic_results": [{"title": "existing"}], "organic": []}

    assert normalize_serper_response(payload) == payload


def test_redact_secret_fields_redacts_nested_api_keys() -> None:
    payload = {
        "headers": {"X-API-KEY": "secret-key"},
        "nested": [{"api_key": "another-secret", "safe": "value"}],
    }

    assert redact_secret_fields(payload) == {
        "headers": {"X-API-KEY": "[redacted]"},
        "nested": [{"api_key": "[redacted]", "safe": "value"}],
    }
