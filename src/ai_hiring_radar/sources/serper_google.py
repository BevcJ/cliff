from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import httpx

from ai_hiring_radar.models import SourceMode, SourceName
from ai_hiring_radar.query_builder import SearchQuery
from ai_hiring_radar.storage_json import (
    DEFAULT_DATA_DIR,
    raw_search_dir,
    write_json,
    write_raw_search_response,
)


SERPER_SEARCH_URL = "https://google.serper.dev/search"
RAW_SEARCH_RECORD_TYPE = "raw_search_response"
MANIFEST_RECORD_TYPE = "collection_manifest"


class SearchClient(Protocol):
    def search(self, search_query: SearchQuery) -> dict[str, Any]: ...


@dataclass
class CollectionResult:
    manifest_path: Path
    query_count: int
    result_files: list[str]
    errors: list[dict[str, Any]]

    @property
    def successful_count(self) -> int:
        return len(self.result_files)

    @property
    def error_count(self) -> int:
        return len(self.errors)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


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

    def search(self, search_query: SearchQuery) -> dict[str, Any]:
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


def build_raw_search_record(
    *,
    search_query: SearchQuery,
    response: dict[str, Any],
    collected_at: str,
) -> dict[str, Any]:
    return {
        "record_type": RAW_SEARCH_RECORD_TYPE,
        "source": SourceName.SERPER_GOOGLE.value,
        "source_mode": SourceMode.LINKEDIN_SAFE_SEARCH.value,
        "country_code": search_query.country_code,
        "country": search_query.country,
        "search_location_label": search_query.search_location_label,
        "query_location": search_query.query_location,
        "serper_location": search_query.serper_location,
        "role_search_term": search_query.role_search_term,
        "search_query": search_query.search_query,
        "request_params": dict(search_query.request_params),
        "collected_at": collected_at,
        "response": redact_secret_fields(response),
    }


def build_collection_manifest(
    *,
    started_at: str,
    finished_at: str,
    search_queries: list[SearchQuery],
    result_files: list[str],
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    countries = list(dict.fromkeys(query.country_code for query in search_queries))
    search_locations = list(
        dict.fromkeys(query.search_location_label for query in search_queries)
    )

    return {
        "record_type": MANIFEST_RECORD_TYPE,
        "source": SourceName.SERPER_GOOGLE.value,
        "source_mode": SourceMode.LINKEDIN_SAFE_SEARCH.value,
        "started_at": started_at,
        "finished_at": finished_at,
        "countries": countries,
        "search_locations": search_locations,
        "query_count": len(search_queries),
        "result_files": result_files,
        "errors": errors,
    }


def query_error_record(
    *,
    search_query: SearchQuery,
    error: str,
    error_type: str | None = None,
    output_file: str | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "country_code": search_query.country_code,
        "country": search_query.country,
        "search_location_label": search_query.search_location_label,
        "query_location": search_query.query_location,
        "serper_location": search_query.serper_location,
        "role_search_term": search_query.role_search_term,
        "search_query": search_query.search_query,
        "request_params": dict(search_query.request_params),
        "error": error,
    }
    if error_type is not None:
        record["error_type"] = error_type
    if output_file is not None:
        record["output_file"] = output_file
    return record


def collect_searches(
    search_queries: Iterable[SearchQuery],
    *,
    client: SearchClient,
    data_dir: Path = DEFAULT_DATA_DIR,
    clock: Callable[[], str] = utc_now_iso,
) -> CollectionResult:
    queries = list(search_queries)
    started_at = clock()
    collection_date = started_at[:10]
    result_files: list[str] = []
    errors: list[dict[str, Any]] = []

    for search_query in queries:
        try:
            response = client.search(search_query)
            raw_record = build_raw_search_record(
                search_query=search_query,
                response=response,
                collected_at=clock(),
            )
            path = write_raw_search_response(
                raw_record,
                country_code=search_query.country_code,
                role_term=search_query.role_search_term,
                search_location=search_query.search_location_label,
                collection_date=collection_date,
                data_dir=data_dir,
            )
            output_file = path.as_posix()
            result_files.append(output_file)

            api_error = response.get("error")
            if api_error:
                errors.append(
                    query_error_record(
                        search_query=search_query,
                        error=str(api_error),
                        output_file=output_file,
                    )
                )
        except Exception as exc:  # noqa: BLE001 - collection continues per query contract.
            errors.append(
                query_error_record(
                    search_query=search_query,
                    error=str(exc),
                    error_type=exc.__class__.__name__,
                )
            )

    finished_at = clock()
    manifest = build_collection_manifest(
        started_at=started_at,
        finished_at=finished_at,
        search_queries=queries,
        result_files=result_files,
        errors=errors,
    )
    manifest_path = raw_search_dir(collection_date, data_dir=data_dir) / "manifest.json"
    write_json(manifest_path, manifest)

    return CollectionResult(
        manifest_path=manifest_path,
        query_count=len(queries),
        result_files=result_files,
        errors=errors,
    )
