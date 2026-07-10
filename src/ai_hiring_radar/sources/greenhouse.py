from __future__ import annotations

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
from ai_hiring_radar.search_locations import LocationDepth
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
from ai_hiring_radar.storage_json import (
    DEFAULT_DATA_DIR,
    raw_ats_dir,
    write_json,
    write_raw_ats_response,
)


GREENHOUSE_PUBLIC_JOBS_URL_TEMPLATE = (
    "https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
)
RAW_ATS_RECORD_TYPE = "raw_ats_response"
ATS_COMPANY_BOARD_RECORD_TYPE = "ats_company_board"
ATS_DISCOVERY_MANIFEST_RECORD_TYPE = "ats_discovery_manifest"
ATS_COLLECTION_MANIFEST_RECORD_TYPE = "ats_collection_manifest"
GREENHOUSE_DISCOVERY_SOURCE = "search_index"
GREENHOUSE_ACCESS_TYPE = "public_job_board_endpoint"
GREENHOUSE_STABILITY = "stable_public_endpoint"
DEFAULT_GREENHOUSE_DISCOVERY_RESULTS_PER_QUERY = DEFAULT_ATS_DISCOVERY_RESULTS_PER_QUERY
MAX_GREENHOUSE_DISCOVERY_RESULTS_PER_QUERY = MAX_ATS_DISCOVERY_RESULTS_PER_QUERY
DEFAULT_GREENHOUSE_DISCOVERY_PAGES = DEFAULT_ATS_DISCOVERY_PAGES
GREENHOUSE_DISCOVERY_SIGNAL_TERMS = DEFAULT_ATS_DISCOVERY_SIGNAL_TERMS
GreenhouseDiscoveryDepth = AtsDiscoveryDepth
GreenhouseDiscoveryQuery = AtsDiscoveryQuery
GreenhouseDiscoveryResult = AtsDiscoveryResult


@dataclass(frozen=True)
class GreenhouseBoard:
    platform_company_slug: str
    board_url: str


@dataclass
class GreenhouseCollectionResult:
    manifest_path: Path
    board_count: int
    result_files: list[str]
    errors: list[dict[str, Any]]

    @property
    def successful_count(self) -> int:
        return len(self.result_files)

    @property
    def error_count(self) -> int:
        return len(self.errors)


class DiscoverySearchClient(Protocol):
    def search(self, search_query: GreenhouseDiscoveryQuery) -> dict[str, Any]: ...


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def greenhouse_board_from_slug(platform_company_slug: str) -> GreenhouseBoard:
    slug = platform_company_slug.strip().strip("/")
    if not slug:
        raise ValueError("Greenhouse board token is required.")
    return GreenhouseBoard(
        platform_company_slug=slug,
        board_url=f"https://boards.greenhouse.io/{quote(slug, safe='-_~.')}",
    )


def parse_greenhouse_board_url(value: object | None) -> GreenhouseBoard | None:
    raw_url = str(value or "").strip()
    if not raw_url:
        return None
    if raw_url.startswith("boards.greenhouse.io/"):
        raw_url = f"https://{raw_url}"

    parsed_url = urlparse(raw_url)
    if parsed_url.scheme not in {"http", "https"}:
        return None
    if parsed_url.netloc.casefold() != "boards.greenhouse.io":
        return None

    path_segments = [unquote(segment) for segment in parsed_url.path.split("/") if segment]
    if not path_segments:
        return None

    slug = path_segments[0].strip()
    if slug.casefold() in {"embed", "api", "assets", "favicon.ico"}:
        return None

    return greenhouse_board_from_slug(slug)


def normalize_greenhouse_board(value: str) -> GreenhouseBoard:
    parsed_board = parse_greenhouse_board_url(value)
    if parsed_board is not None:
        return parsed_board
    return greenhouse_board_from_slug(value)


GREENHOUSE_DISCOVERY_PROVIDER = AtsDiscoveryProvider(
    platform=SourceName.GREENHOUSE.value,
    site="boards.greenhouse.io",
    parse_board_url=parse_greenhouse_board_url,
)


def build_greenhouse_discovery_search_query(
    *,
    search_text: str | None = None,
    terms: Iterable[object | None] = (),
) -> str:
    discovery_terms = (search_text,) if search_text is not None else terms
    return build_ats_discovery_search_query(
        provider=GREENHOUSE_DISCOVERY_PROVIDER,
        terms=discovery_terms,
    )


def generate_greenhouse_discovery_queries(
    *,
    countries_config: CountriesConfig,
    country_codes: Iterable[str],
    limit: int | None = None,
    num: int = DEFAULT_GREENHOUSE_DISCOVERY_RESULTS_PER_QUERY,
    pages: int = DEFAULT_GREENHOUSE_DISCOVERY_PAGES,
    location_depth: LocationDepth = LocationDepth.CITIES,
    discovery_depth: GreenhouseDiscoveryDepth = GreenhouseDiscoveryDepth.EXHAUSTIVE,
    role_terms: Iterable[str] = (),
    signal_terms: Iterable[str] = GREENHOUSE_DISCOVERY_SIGNAL_TERMS,
) -> list[GreenhouseDiscoveryQuery]:
    return generate_ats_discovery_queries(
        provider=GREENHOUSE_DISCOVERY_PROVIDER,
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


def extract_greenhouse_board_records(
    *,
    discovery_query: GreenhouseDiscoveryQuery,
    response: dict[str, Any],
    collected_at: str,
) -> list[dict[str, Any]]:
    return extract_ats_board_records(
        provider=GREENHOUSE_DISCOVERY_PROVIDER,
        discovery_query=discovery_query,
        response=response,
        collected_at=collected_at,
    )


def discover_greenhouse_boards(
    discovery_queries: Iterable[GreenhouseDiscoveryQuery],
    *,
    client: DiscoverySearchClient,
    data_dir: Path = DEFAULT_DATA_DIR,
    clock: Callable[[], str] = utc_now_iso,
) -> GreenhouseDiscoveryResult:
    return discover_ats_boards(
        discovery_queries,
        provider=GREENHOUSE_DISCOVERY_PROVIDER,
        client=client,
        data_dir=data_dir,
        clock=clock,
    )


def build_greenhouse_jobs_endpoint(platform_company_slug: str) -> str:
    board_token = quote(platform_company_slug.strip().strip("/"), safe="-_~.")
    if not board_token:
        raise ValueError("Greenhouse board token is required.")
    return GREENHOUSE_PUBLIC_JOBS_URL_TEMPLATE.format(board_token=board_token)


class GreenhouseClient:
    def __init__(
        self,
        *,
        timeout: float = 30.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._client = http_client or httpx.Client(timeout=timeout)
        self._owns_client = http_client is None

    def fetch_board(self, board_url_or_slug: str) -> dict[str, Any]:
        board = normalize_greenhouse_board(board_url_or_slug)
        response = self._client.get(
            build_greenhouse_jobs_endpoint(board.platform_company_slug),
            headers={"User-Agent": "ai-hiring-radar-greenhouse-prototype"},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Expected Greenhouse to return a JSON object.")
        return payload

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


def build_raw_greenhouse_response_record(
    *,
    board: GreenhouseBoard,
    response: dict[str, Any],
    collected_at: str,
) -> dict[str, Any]:
    return {
        "record_type": RAW_ATS_RECORD_TYPE,
        "platform": SourceName.GREENHOUSE.value,
        "access_type": GREENHOUSE_ACCESS_TYPE,
        "official_api": True,
        "stability": GREENHOUSE_STABILITY,
        "source": SourceName.GREENHOUSE.value,
        "source_mode": SourceMode.PUBLIC_JOB_BOARD_ENDPOINT.value,
        "platform_company_slug": board.platform_company_slug,
        "board_url": board.board_url,
        "endpoint": build_greenhouse_jobs_endpoint(board.platform_company_slug),
        "request_params": {"content": "true"},
        "collected_at": collected_at,
        "title_prefilter": _greenhouse_title_prefilter_metadata(response),
        "response": response,
    }


def _greenhouse_jobs(response: dict[str, Any]) -> list[dict[str, Any]]:
    jobs = response.get("jobs")
    if not isinstance(jobs, list):
        return []
    return [job for job in jobs if isinstance(job, dict)]


def _greenhouse_title_prefilter_metadata(response: dict[str, Any]) -> dict[str, int | str]:
    jobs = _greenhouse_jobs(response)
    matched_count = sum(
        1 for job in jobs if is_ai_role_title_candidate(job.get("title"))
    )
    return title_prefilter_metadata(
        listed_count=len(jobs),
        matched_count=matched_count,
    )


def _has_jobs_response(response: dict[str, Any]) -> bool:
    return isinstance(response.get("jobs"), list)


def _collection_error_record(
    *,
    board: GreenhouseBoard,
    error: str,
    error_type: str | None = None,
    output_file: str | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "platform": SourceName.GREENHOUSE.value,
        "platform_company_slug": board.platform_company_slug,
        "board_url": board.board_url,
        "error": error,
    }
    if error_type is not None:
        record["error_type"] = error_type
    if output_file is not None:
        record["output_file"] = output_file
    return record


def collect_greenhouse_boards(
    board_urls_or_slugs: Iterable[str],
    *,
    client: GreenhouseClient,
    data_dir: Path = DEFAULT_DATA_DIR,
    clock: Callable[[], str] = utc_now_iso,
) -> GreenhouseCollectionResult:
    boards_by_slug: dict[str, GreenhouseBoard] = {}
    for value in board_urls_or_slugs:
        board = normalize_greenhouse_board(value)
        boards_by_slug.setdefault(board.platform_company_slug, board)

    boards = list(boards_by_slug.values())
    started_at = clock()
    collection_date = started_at[:10]
    result_files: list[str] = []
    errors: list[dict[str, Any]] = []

    for board in boards:
        try:
            response = client.fetch_board(board.board_url)
            raw_record = build_raw_greenhouse_response_record(
                board=board,
                response=response,
                collected_at=clock(),
            )
            path = write_raw_ats_response(
                raw_record,
                platform_company_slug=board.platform_company_slug,
                collection_date=collection_date,
                data_dir=data_dir,
                platform=SourceName.GREENHOUSE.value,
            )
            output_file = path.as_posix()
            result_files.append(output_file)

            if not _has_jobs_response(response):
                errors.append(
                    _collection_error_record(
                        board=board,
                        error="Greenhouse response did not contain a jobs list.",
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
        collection_date,
        data_dir=data_dir,
        platform=SourceName.GREENHOUSE.value,
    ) / "manifest.json"
    write_json(
        manifest_path,
        {
            "record_type": ATS_COLLECTION_MANIFEST_RECORD_TYPE,
            "platform": SourceName.GREENHOUSE.value,
            "source": SourceName.GREENHOUSE.value,
            "source_mode": SourceMode.PUBLIC_JOB_BOARD_ENDPOINT.value,
            "started_at": started_at,
            "finished_at": finished_at,
            "board_count": len(boards),
            "result_files": result_files,
            "errors": errors,
        },
    )

    return GreenhouseCollectionResult(
        manifest_path=manifest_path,
        board_count=len(boards),
        result_files=result_files,
        errors=errors,
    )
