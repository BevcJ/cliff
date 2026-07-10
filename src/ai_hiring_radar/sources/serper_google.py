from __future__ import annotations

from typing import Any, Protocol

import httpx


SERPER_SEARCH_URL = "https://google.serper.dev/search"


class SerperSearchRequest(Protocol):
    request_params: dict[str, str | int]


def redact_secret_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[redacted]"
            if key.lower() in {"api_key", "x-api-key"}
            else redact_secret_fields(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_secret_fields(item) for item in value]
    return value


def normalize_serper_response(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    if "organic_results" not in normalized and isinstance(normalized.get("organic"), list):
        normalized["organic_results"] = normalized["organic"]
    return normalized


class SerperGoogleClient:
    def __init__(
        self,
        *,
        api_key: str,
        endpoint: str = SERPER_SEARCH_URL,
        timeout: float = 30.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.endpoint = endpoint
        self._client = http_client or httpx.Client(timeout=timeout)
        self._owns_client = http_client is None

    def search(self, search_query: SerperSearchRequest) -> dict[str, Any]:
        response = self._client.post(
            self.endpoint,
            headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"},
            json=dict(search_query.request_params),
        )
        response.raise_for_status()
        payload = response.json()

        if not isinstance(payload, dict):
            raise ValueError("Expected Serper to return a JSON object.")

        return normalize_serper_response(payload)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()
