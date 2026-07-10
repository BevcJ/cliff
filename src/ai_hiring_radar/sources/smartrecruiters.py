from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote, unquote, urlencode, urlparse

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


SMARTRECRUITERS_PUBLIC_API_BASE_URL = "https://api.smartrecruiters.com"
SMARTRECRUITERS_DEFAULT_PAGE_LIMIT = 100
RAW_ATS_RECORD_TYPE = "raw_ats_response"
ATS_COLLECTION_MANIFEST_RECORD_TYPE = "ats_collection_manifest"
SMARTRECRUITERS_ACCESS_TYPE = "public_job_board_endpoint"
SMARTRECRUITERS_STABILITY = "stable_public_endpoint"
DEFAULT_SMARTRECRUITERS_DISCOVERY_RESULTS_PER_QUERY = (
    DEFAULT_ATS_DISCOVERY_RESULTS_PER_QUERY
)
MAX_SMARTRECRUITERS_DISCOVERY_RESULTS_PER_QUERY = MAX_ATS_DISCOVERY_RESULTS_PER_QUERY
DEFAULT_SMARTRECRUITERS_DISCOVERY_PAGES = DEFAULT_ATS_DISCOVERY_PAGES
SMARTRECRUITERS_DISCOVERY_SIGNAL_TERMS = DEFAULT_ATS_DISCOVERY_SIGNAL_TERMS
SmartRecruitersDiscoveryDepth = AtsDiscoveryDepth
SmartRecruitersDiscoveryQuery = AtsDiscoveryQuery
SmartRecruitersDiscoveryResult = AtsDiscoveryResult


@dataclass(frozen=True)
class SmartRecruitersBoard:
    platform_company_slug: str
    board_url: str


@dataclass(frozen=True)
class SmartRecruitersFetchResult:
    response: list[dict[str, Any]]
    endpoint: str
    page_endpoints: list[str]
    request_params: dict[str, str | int]


@dataclass
class SmartRecruitersCollectionResult:
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
    def search(self, search_query: SmartRecruitersDiscoveryQuery) -> dict[str, Any]: ...


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def smartrecruiters_board_from_slug(
    platform_company_slug: str,
) -> SmartRecruitersBoard:
    slug = platform_company_slug.strip().strip("/")
    if not slug:
        raise ValueError("SmartRecruiters company identifier is required.")
    return SmartRecruitersBoard(
        platform_company_slug=slug,
        board_url=f"https://careers.smartrecruiters.com/{quote(slug, safe='-_~.')}",
    )


def _parse_api_company_slug(path_segments: list[str]) -> str | None:
    if len(path_segments) >= 3 and [segment.casefold() for segment in path_segments[:2]] == [
        "v1",
        "companies",
    ]:
        return path_segments[2]
    return None


def parse_smartrecruiters_board_url(value: object | None) -> SmartRecruitersBoard | None:
    raw_url = str(value or "").strip()
    if not raw_url:
        return None
    if raw_url.startswith(("careers.smartrecruiters.com/", "jobs.smartrecruiters.com/")):
        raw_url = f"https://{raw_url}"

    parsed_url = urlparse(raw_url)
    if parsed_url.scheme not in {"http", "https"}:
        return None

    host = parsed_url.netloc.casefold()
    path_segments = [unquote(segment) for segment in parsed_url.path.split("/") if segment]
    if host == "api.smartrecruiters.com":
        slug = _parse_api_company_slug(path_segments)
        return smartrecruiters_board_from_slug(slug) if slug else None

    if host not in {"careers.smartrecruiters.com", "jobs.smartrecruiters.com"}:
        return None
    if not path_segments:
        return None

    slug = path_segments[0].strip()
    if slug.casefold() in {"api", "assets", "favicon.ico"}:
        return None
    return smartrecruiters_board_from_slug(slug)


def normalize_smartrecruiters_board(value: str) -> SmartRecruitersBoard:
    parsed_board = parse_smartrecruiters_board_url(value)
    if parsed_board is not None:
        return parsed_board
    return smartrecruiters_board_from_slug(value)


SMARTRECRUITERS_DISCOVERY_PROVIDER = AtsDiscoveryProvider(
    platform=SourceName.SMARTRECRUITERS.value,
    site="careers.smartrecruiters.com",
    parse_board_url=parse_smartrecruiters_board_url,
)


def build_smartrecruiters_discovery_search_query(
    *,
    terms: Iterable[object | None] = (),
) -> str:
    return build_ats_discovery_search_query(
        provider=SMARTRECRUITERS_DISCOVERY_PROVIDER,
        terms=terms,
    )


def generate_smartrecruiters_discovery_queries(
    *,
    countries_config: CountriesConfig,
    country_codes: Iterable[str],
    limit: int | None = None,
    num: int = DEFAULT_SMARTRECRUITERS_DISCOVERY_RESULTS_PER_QUERY,
    pages: int = DEFAULT_SMARTRECRUITERS_DISCOVERY_PAGES,
    location_depth: LocationDepth = LocationDepth.CITIES,
    discovery_depth: SmartRecruitersDiscoveryDepth = SmartRecruitersDiscoveryDepth.EXHAUSTIVE,
    role_terms: Iterable[str] = (),
    signal_terms: Iterable[str] = SMARTRECRUITERS_DISCOVERY_SIGNAL_TERMS,
) -> list[SmartRecruitersDiscoveryQuery]:
    return generate_ats_discovery_queries(
        provider=SMARTRECRUITERS_DISCOVERY_PROVIDER,
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


def extract_smartrecruiters_board_records(
    *,
    discovery_query: SmartRecruitersDiscoveryQuery,
    response: dict[str, Any],
    collected_at: str,
) -> list[dict[str, Any]]:
    return extract_ats_board_records(
        provider=SMARTRECRUITERS_DISCOVERY_PROVIDER,
        discovery_query=discovery_query,
        response=response,
        collected_at=collected_at,
    )


def discover_smartrecruiters_boards(
    discovery_queries: Iterable[SmartRecruitersDiscoveryQuery],
    *,
    client: DiscoverySearchClient,
    data_dir: Path = DEFAULT_DATA_DIR,
    clock: Callable[[], str] = utc_now_iso,
) -> SmartRecruitersDiscoveryResult:
    return discover_ats_boards(
        discovery_queries,
        provider=SMARTRECRUITERS_DISCOVERY_PROVIDER,
        client=client,
        data_dir=data_dir,
        clock=clock,
    )


def _smartrecruiters_request_params(
    *,
    limit: int,
    offset: int,
    search_text: str | None = None,
) -> dict[str, str | int]:
    params: dict[str, str | int] = {"limit": limit, "offset": offset}
    normalized_search_text = " ".join(str(search_text or "").split()).strip()
    if normalized_search_text:
        params["q"] = normalized_search_text
    return params


def build_smartrecruiters_postings_endpoint(
    platform_company_slug: str,
    *,
    limit: int = SMARTRECRUITERS_DEFAULT_PAGE_LIMIT,
    offset: int = 0,
    search_text: str | None = None,
    api_base_url: str = SMARTRECRUITERS_PUBLIC_API_BASE_URL,
) -> str:
    slug = platform_company_slug.strip().strip("/")
    if not slug:
        raise ValueError("SmartRecruiters company identifier is required.")
    params = _smartrecruiters_request_params(
        limit=limit,
        offset=offset,
        search_text=search_text,
    )
    return (
        f"{api_base_url.rstrip('/')}/v1/companies/{quote(slug, safe='-_~.')}/postings"
        f"?{urlencode(params)}"
    )


def _integer_value(value: object | None) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdecimal():
        return int(value)
    return None


def _smartrecruiters_postings(response: list[dict[str, Any]]) -> list[dict[str, Any]]:
    postings: list[dict[str, Any]] = []
    for page in response:
        content = page.get("content")
        if not isinstance(content, list):
            continue
        postings.extend(item for item in content if isinstance(item, dict))
    return postings


def _smartrecruiters_title_prefilter_metadata(
    response: list[dict[str, Any]],
) -> dict[str, int | str]:
    postings = _smartrecruiters_postings(response)
    matched_count = sum(
        1
        for posting in postings
        if is_ai_role_title_candidate(posting.get("name") or posting.get("title"))
    )
    return title_prefilter_metadata(
        listed_count=len(postings),
        matched_count=matched_count,
        source_field="name/title",
    )


class SmartRecruitersClient:
    def __init__(
        self,
        *,
        page_limit: int = SMARTRECRUITERS_DEFAULT_PAGE_LIMIT,
        search_text: str | None = None,
        timeout: float = 30.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        if page_limit < 1:
            raise ValueError("SmartRecruiters page limit must be greater than zero.")
        self.page_limit = page_limit
        self.search_text = search_text
        self._client = http_client or httpx.Client(timeout=timeout)
        self._owns_client = http_client is None

    def fetch_board(self, board_url_or_slug: str) -> SmartRecruitersFetchResult:
        board = normalize_smartrecruiters_board(board_url_or_slug)
        pages: list[dict[str, Any]] = []
        endpoints: list[str] = []
        offset = 0

        while True:
            endpoint = build_smartrecruiters_postings_endpoint(
                board.platform_company_slug,
                limit=self.page_limit,
                offset=offset,
                search_text=self.search_text,
            )
            response = self._client.get(
                endpoint,
                headers={"User-Agent": "ai-hiring-radar-smartrecruiters-prototype"},
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("Expected SmartRecruiters to return a JSON object.")

            pages.append(payload)
            endpoints.append(endpoint)

            response_limit = _integer_value(payload.get("limit")) or self.page_limit
            response_offset = _integer_value(payload.get("offset"))
            total_found = _integer_value(payload.get("totalFound"))
            if response_offset is None or total_found is None:
                break
            if response_limit < 1 or response_offset + response_limit >= total_found:
                break
            offset = response_offset + response_limit

        return SmartRecruitersFetchResult(
            response=pages,
            endpoint=endpoints[0],
            page_endpoints=endpoints,
            request_params=_smartrecruiters_request_params(
                limit=self.page_limit,
                offset=0,
                search_text=self.search_text,
            ),
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


def build_raw_smartrecruiters_response_record(
    *,
    board: SmartRecruitersBoard,
    response: list[dict[str, Any]],
    collected_at: str,
    endpoint: str | None = None,
    page_endpoints: list[str] | None = None,
    request_params: dict[str, str | int] | None = None,
) -> dict[str, Any]:
    params = request_params or _smartrecruiters_request_params(
        limit=SMARTRECRUITERS_DEFAULT_PAGE_LIMIT,
        offset=0,
    )
    first_endpoint = endpoint or build_smartrecruiters_postings_endpoint(
        board.platform_company_slug,
        limit=int(params.get("limit") or SMARTRECRUITERS_DEFAULT_PAGE_LIMIT),
        offset=int(params.get("offset") or 0),
        search_text=str(params.get("q")) if params.get("q") is not None else None,
    )
    return {
        "record_type": RAW_ATS_RECORD_TYPE,
        "platform": SourceName.SMARTRECRUITERS.value,
        "access_type": SMARTRECRUITERS_ACCESS_TYPE,
        "official_api": True,
        "stability": SMARTRECRUITERS_STABILITY,
        "source": SourceName.SMARTRECRUITERS.value,
        "source_mode": SourceMode.PUBLIC_JOB_BOARD_ENDPOINT.value,
        "platform_company_slug": board.platform_company_slug,
        "board_url": board.board_url,
        "endpoint": first_endpoint,
        "page_endpoints": page_endpoints or [first_endpoint],
        "request_params": params,
        "response_format": "json",
        "title_prefilter": _smartrecruiters_title_prefilter_metadata(response),
        "collected_at": collected_at,
        "response": response,
    }


def _has_postings_response(response: list[dict[str, Any]]) -> bool:
    return all(isinstance(page.get("content"), list) for page in response)


def _collection_error_record(
    *,
    board: SmartRecruitersBoard,
    error: str,
    error_type: str | None = None,
    output_file: str | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "platform": SourceName.SMARTRECRUITERS.value,
        "platform_company_slug": board.platform_company_slug,
        "board_url": board.board_url,
        "error": error,
    }
    if error_type is not None:
        record["error_type"] = error_type
    if output_file is not None:
        record["output_file"] = output_file
    return record


def collect_smartrecruiters_boards(
    board_urls_or_slugs: Iterable[str],
    *,
    client: SmartRecruitersClient,
    data_dir: Path = DEFAULT_DATA_DIR,
    clock: Callable[[], str] = utc_now_iso,
) -> SmartRecruitersCollectionResult:
    boards_by_slug: dict[str, SmartRecruitersBoard] = {}
    for value in board_urls_or_slugs:
        board = normalize_smartrecruiters_board(value)
        boards_by_slug.setdefault(board.platform_company_slug, board)

    boards = list(boards_by_slug.values())
    started_at = clock()
    collection_date = started_at[:10]
    result_files: list[str] = []
    errors: list[dict[str, Any]] = []

    for board in boards:
        try:
            fetch_result = client.fetch_board(board.board_url)
            raw_record = build_raw_smartrecruiters_response_record(
                board=board,
                response=fetch_result.response,
                endpoint=fetch_result.endpoint,
                page_endpoints=fetch_result.page_endpoints,
                request_params=fetch_result.request_params,
                collected_at=clock(),
            )
            path = write_raw_ats_response(
                raw_record,
                platform_company_slug=board.platform_company_slug,
                collection_date=collection_date,
                data_dir=data_dir,
                platform=SourceName.SMARTRECRUITERS.value,
            )
            output_file = path.as_posix()
            result_files.append(output_file)

            if not _has_postings_response(fetch_result.response):
                errors.append(
                    _collection_error_record(
                        board=board,
                        error="SmartRecruiters response did not contain content lists.",
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
        platform=SourceName.SMARTRECRUITERS.value,
    ) / "manifest.json"
    write_json(
        manifest_path,
        {
            "record_type": ATS_COLLECTION_MANIFEST_RECORD_TYPE,
            "platform": SourceName.SMARTRECRUITERS.value,
            "source": SourceName.SMARTRECRUITERS.value,
            "source_mode": SourceMode.PUBLIC_JOB_BOARD_ENDPOINT.value,
            "started_at": started_at,
            "finished_at": finished_at,
            "board_count": len(boards),
            "result_files": result_files,
            "errors": errors,
        },
    )

    return SmartRecruitersCollectionResult(
        manifest_path=manifest_path,
        board_count=len(boards),
        result_files=result_files,
        errors=errors,
    )
