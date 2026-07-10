from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote, unquote, urlparse

import httpx

from ai_hiring_radar.classify import is_ai_role_title_candidate, title_prefilter_metadata
from ai_hiring_radar.config import CountriesConfig
from ai_hiring_radar.models import SourceMode, SourceName
from ai_hiring_radar.query_builder import LocationDepth
from ai_hiring_radar.sources.ats_discovery import (
    DEFAULT_ATS_DISCOVERY_PAGES,
    DEFAULT_ATS_DISCOVERY_RESULTS_PER_QUERY,
    DEFAULT_ATS_DISCOVERY_SIGNAL_TERMS,
    MAX_ATS_DISCOVERY_RESULTS_PER_QUERY,
    AtsDiscoveryDepth,
    AtsDiscoveryProvider,
    AtsDiscoveryQuery,
    AtsDiscoveryResult,
    build_ats_discovery_search_query,
    discover_ats_boards,
    extract_ats_board_records,
    generate_ats_discovery_queries,
)
from ai_hiring_radar.sources.collection_resilience import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_REQUEST_DELAY_SECONDS,
    ResilientHttpRequester,
    is_valid_raw_ats_resume_file,
    raw_ats_response_path,
)
from ai_hiring_radar.storage_json import (
    DEFAULT_DATA_DIR,
    format_date,
    raw_ats_dir,
    write_json,
    write_raw_ats_response,
)


LEVER_PUBLIC_API_BASE_URL = "https://api.lever.co"
LEVER_EU_PUBLIC_API_BASE_URL = "https://api.eu.lever.co"
RAW_ATS_RECORD_TYPE = "raw_ats_response"
ATS_COLLECTION_MANIFEST_RECORD_TYPE = "ats_collection_manifest"
LEVER_ACCESS_TYPE = "public_job_board_endpoint"
LEVER_STABILITY = "stable_public_endpoint"
DEFAULT_LEVER_DISCOVERY_RESULTS_PER_QUERY = DEFAULT_ATS_DISCOVERY_RESULTS_PER_QUERY
MAX_LEVER_DISCOVERY_RESULTS_PER_QUERY = MAX_ATS_DISCOVERY_RESULTS_PER_QUERY
DEFAULT_LEVER_DISCOVERY_PAGES = DEFAULT_ATS_DISCOVERY_PAGES
LEVER_DISCOVERY_SIGNAL_TERMS = DEFAULT_ATS_DISCOVERY_SIGNAL_TERMS
LeverDiscoveryDepth = AtsDiscoveryDepth
LeverDiscoveryQuery = AtsDiscoveryQuery
LeverDiscoveryResult = AtsDiscoveryResult


@dataclass(frozen=True)
class LeverBoard:
    platform_company_slug: str
    board_url: str


@dataclass
class LeverCollectionResult:
    manifest_path: Path
    board_count: int
    result_files: list[str]
    written_files: list[str]
    resumed_files: list[str]
    errors: list[dict[str, Any]]

    @property
    def successful_count(self) -> int:
        return len(self.result_files)

    @property
    def written_count(self) -> int:
        return len(self.written_files)

    @property
    def resumed_count(self) -> int:
        return len(self.resumed_files)

    @property
    def error_count(self) -> int:
        return len(self.errors)


class DiscoverySearchClient(Protocol):
    def search(self, search_query: LeverDiscoveryQuery) -> dict[str, Any]: ...


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def lever_board_from_slug(platform_company_slug: str) -> LeverBoard:
    slug = platform_company_slug.strip().strip("/")
    if not slug:
        raise ValueError("Lever site slug is required.")
    return LeverBoard(
        platform_company_slug=slug,
        board_url=f"https://jobs.lever.co/{quote(slug, safe='-_~.')}",
    )


def parse_lever_board_url(value: object | None) -> LeverBoard | None:
    raw_url = str(value or "").strip()
    if not raw_url:
        return None
    if raw_url.startswith("jobs.lever.co/"):
        raw_url = f"https://{raw_url}"

    parsed_url = urlparse(raw_url)
    if parsed_url.scheme not in {"http", "https"}:
        return None
    if parsed_url.netloc.casefold() != "jobs.lever.co":
        return None

    path_segments = [unquote(segment) for segment in parsed_url.path.split("/") if segment]
    if not path_segments:
        return None

    slug = path_segments[0].strip()
    if slug.casefold() in {"api", "assets", "favicon.ico"}:
        return None

    return lever_board_from_slug(slug)


def normalize_lever_board(value: str) -> LeverBoard:
    parsed_board = parse_lever_board_url(value)
    if parsed_board is not None:
        return parsed_board
    return lever_board_from_slug(value)


LEVER_DISCOVERY_PROVIDER = AtsDiscoveryProvider(
    platform=SourceName.LEVER.value,
    site="jobs.lever.co",
    parse_board_url=parse_lever_board_url,
)


def build_lever_discovery_search_query(
    *,
    terms: Iterable[object | None] = (),
) -> str:
    return build_ats_discovery_search_query(
        provider=LEVER_DISCOVERY_PROVIDER,
        terms=terms,
    )


def generate_lever_discovery_queries(
    *,
    countries_config: CountriesConfig,
    country_codes: Iterable[str],
    limit: int | None = None,
    num: int = DEFAULT_LEVER_DISCOVERY_RESULTS_PER_QUERY,
    pages: int = DEFAULT_LEVER_DISCOVERY_PAGES,
    location_depth: LocationDepth = LocationDepth.CITIES,
    discovery_depth: LeverDiscoveryDepth = LeverDiscoveryDepth.EXHAUSTIVE,
    role_terms: Iterable[str] = (),
    signal_terms: Iterable[str] = LEVER_DISCOVERY_SIGNAL_TERMS,
) -> list[LeverDiscoveryQuery]:
    return generate_ats_discovery_queries(
        provider=LEVER_DISCOVERY_PROVIDER,
        countries_config=countries_config,
        country_codes=country_codes,
        limit=limit,
        num=num,
        pages=pages,
        location_depth=location_depth,
        discovery_depth=discovery_depth,
        role_terms=role_terms,
        signal_terms=signal_terms,
    )


def extract_lever_board_records(
    *,
    discovery_query: LeverDiscoveryQuery,
    response: dict[str, Any],
    collected_at: str,
) -> list[dict[str, Any]]:
    return extract_ats_board_records(
        provider=LEVER_DISCOVERY_PROVIDER,
        discovery_query=discovery_query,
        response=response,
        collected_at=collected_at,
    )


def discover_lever_boards(
    discovery_queries: Iterable[LeverDiscoveryQuery],
    *,
    client: DiscoverySearchClient,
    data_dir: Path = DEFAULT_DATA_DIR,
    clock: Callable[[], str] = utc_now_iso,
) -> LeverDiscoveryResult:
    return discover_ats_boards(
        discovery_queries,
        provider=LEVER_DISCOVERY_PROVIDER,
        client=client,
        data_dir=data_dir,
        clock=clock,
    )


def build_lever_postings_endpoint(
    platform_company_slug: str,
    *,
    api_base_url: str = LEVER_PUBLIC_API_BASE_URL,
) -> str:
    site_slug = quote(platform_company_slug.strip().strip("/"), safe="-_~.")
    if not site_slug:
        raise ValueError("Lever site slug is required.")
    return f"{api_base_url.rstrip('/')}/v0/postings/{site_slug}?mode=json"


@dataclass(frozen=True)
class LeverFetchResult:
    response: list[Any]
    endpoint: str
    api_region: str


class LeverClient:
    def __init__(
        self,
        *,
        timeout: float = 30.0,
        http_client: httpx.Client | None = None,
        request_delay_seconds: float = DEFAULT_REQUEST_DELAY_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = http_client or httpx.Client(timeout=timeout)
        self._owns_client = http_client is None
        self._requester = ResilientHttpRequester(
            http_client=self._client,
            request_delay_seconds=request_delay_seconds,
            max_retries=max_retries,
            sleeper=sleeper,
        )

    def fetch_board(self, board_url_or_slug: str) -> LeverFetchResult:
        board = normalize_lever_board(board_url_or_slug)
        first_error: httpx.HTTPStatusError | None = None

        for api_region, api_base_url in (
            ("global", LEVER_PUBLIC_API_BASE_URL),
            ("eu", LEVER_EU_PUBLIC_API_BASE_URL),
        ):
            endpoint = build_lever_postings_endpoint(
                board.platform_company_slug,
                api_base_url=api_base_url,
            )
            try:
                response = self._requester.get(
                    endpoint,
                    headers={"User-Agent": "ai-hiring-radar-lever-prototype"},
                )
            except httpx.HTTPStatusError as exc:
                if first_error is None:
                    first_error = exc
                if exc.response.status_code == 404 and api_region == "global":
                    continue
                raise

            payload = response.json()
            if not isinstance(payload, list):
                raise ValueError("Expected Lever to return a JSON array.")
            return LeverFetchResult(
                response=payload,
                endpoint=endpoint,
                api_region=api_region,
            )

        if first_error is not None:
            raise first_error
        raise RuntimeError("Lever request failed before receiving a response.")

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


def build_raw_lever_response_record(
    *,
    board: LeverBoard,
    response: list[Any],
    collected_at: str,
    endpoint: str | None = None,
    api_region: str = "global",
) -> dict[str, Any]:
    return {
        "record_type": RAW_ATS_RECORD_TYPE,
        "platform": SourceName.LEVER.value,
        "access_type": LEVER_ACCESS_TYPE,
        "official_api": True,
        "stability": LEVER_STABILITY,
        "source": SourceName.LEVER.value,
        "source_mode": SourceMode.PUBLIC_JOB_BOARD_ENDPOINT.value,
        "platform_company_slug": board.platform_company_slug,
        "board_url": board.board_url,
        "endpoint": endpoint
        or build_lever_postings_endpoint(board.platform_company_slug),
        "api_region": api_region,
        "request_params": {"mode": "json"},
        "collected_at": collected_at,
        "title_prefilter": _lever_title_prefilter_metadata(response),
        "response": response,
    }


def _lever_postings(response: list[Any]) -> list[dict[str, Any]]:
    return [item for item in response if isinstance(item, dict)]


def _lever_title_prefilter_metadata(response: list[Any]) -> dict[str, int | str]:
    postings = _lever_postings(response)
    matched_count = sum(
        1
        for posting in postings
        if is_ai_role_title_candidate(posting.get("text") or posting.get("title"))
    )
    return title_prefilter_metadata(
        listed_count=len(postings),
        matched_count=matched_count,
        source_field="text/title",
    )


def _has_postings_response(response: list[Any]) -> bool:
    return all(isinstance(item, dict) for item in response)


def _collection_error_record(
    *,
    board: LeverBoard,
    error: str,
    error_type: str | None = None,
    output_file: str | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "platform": SourceName.LEVER.value,
        "platform_company_slug": board.platform_company_slug,
        "board_url": board.board_url,
        "error": error,
    }
    if error_type is not None:
        record["error_type"] = error_type
    if output_file is not None:
        record["output_file"] = output_file
    return record


def collect_lever_boards(
    board_urls_or_slugs: Iterable[str],
    *,
    client: LeverClient,
    data_dir: Path = DEFAULT_DATA_DIR,
    clock: Callable[[], str] = utc_now_iso,
    collection_date: str | None = None,
    resume: bool = True,
) -> LeverCollectionResult:
    boards_by_slug: dict[str, LeverBoard] = {}
    for value in board_urls_or_slugs:
        board = normalize_lever_board(value)
        boards_by_slug.setdefault(board.platform_company_slug, board)

    boards = list(boards_by_slug.values())
    started_at = clock()
    effective_collection_date = format_date(
        collection_date if collection_date is not None else started_at[:10]
    )
    result_files: list[str] = []
    written_files: list[str] = []
    resumed_files: list[str] = []
    errors: list[dict[str, Any]] = []

    for board in boards:
        resume_path = raw_ats_response_path(
            platform_company_slug=board.platform_company_slug,
            collection_date=effective_collection_date,
            data_dir=data_dir,
            platform=SourceName.LEVER.value,
        )
        if resume and is_valid_raw_ats_resume_file(
            resume_path,
            platform=SourceName.LEVER.value,
            platform_company_slug=board.platform_company_slug,
        ):
            output_file = resume_path.as_posix()
            result_files.append(output_file)
            resumed_files.append(output_file)
            continue

        try:
            fetch_result = client.fetch_board(board.board_url)
            raw_record = build_raw_lever_response_record(
                board=board,
                response=fetch_result.response,
                endpoint=fetch_result.endpoint,
                api_region=fetch_result.api_region,
                collected_at=clock(),
            )
            path = write_raw_ats_response(
                raw_record,
                platform_company_slug=board.platform_company_slug,
                collection_date=effective_collection_date,
                data_dir=data_dir,
                platform=SourceName.LEVER.value,
            )
            output_file = path.as_posix()
            result_files.append(output_file)
            written_files.append(output_file)

            if not _has_postings_response(fetch_result.response):
                errors.append(
                    _collection_error_record(
                        board=board,
                        error="Lever response did not contain only posting objects.",
                        output_file=output_file,
                    )
                )
        except Exception as exc:  # noqa: BLE001 - collection continues per board.
            errors.append(
                _collection_error_record(
                    board=board,
                    error=str(exc),
                    error_type=exc.__class__.__name__,
                )
            )

    finished_at = clock()
    manifest_path = raw_ats_dir(
        effective_collection_date,
        data_dir=data_dir,
        platform=SourceName.LEVER.value,
    ) / "manifest.json"
    write_json(
        manifest_path,
        {
            "record_type": ATS_COLLECTION_MANIFEST_RECORD_TYPE,
            "platform": SourceName.LEVER.value,
            "source": SourceName.LEVER.value,
            "source_mode": SourceMode.PUBLIC_JOB_BOARD_ENDPOINT.value,
            "started_at": started_at,
            "finished_at": finished_at,
            "board_count": len(boards),
            "result_files": result_files,
            "written_files": written_files,
            "resumed_files": resumed_files,
            "errors": errors,
        },
    )

    return LeverCollectionResult(
        manifest_path=manifest_path,
        board_count=len(boards),
        result_files=result_files,
        written_files=written_files,
        resumed_files=resumed_files,
        errors=errors,
    )
