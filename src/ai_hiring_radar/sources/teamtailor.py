from __future__ import annotations

import xml.etree.ElementTree as ET
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
from ai_hiring_radar.storage_json import (
    DEFAULT_DATA_DIR,
    raw_ats_dir,
    write_json,
    write_raw_ats_response,
)


RAW_ATS_RECORD_TYPE = "raw_ats_response"
ATS_COLLECTION_MANIFEST_RECORD_TYPE = "ats_collection_manifest"
TEAMTAILOR_ACCESS_TYPE = "public_job_board_endpoint"
TEAMTAILOR_STABILITY = "stable_public_rss_feed"
DEFAULT_TEAMTAILOR_DISCOVERY_RESULTS_PER_QUERY = DEFAULT_ATS_DISCOVERY_RESULTS_PER_QUERY
MAX_TEAMTAILOR_DISCOVERY_RESULTS_PER_QUERY = MAX_ATS_DISCOVERY_RESULTS_PER_QUERY
DEFAULT_TEAMTAILOR_DISCOVERY_PAGES = DEFAULT_ATS_DISCOVERY_PAGES
TEAMTAILOR_DISCOVERY_SIGNAL_TERMS = DEFAULT_ATS_DISCOVERY_SIGNAL_TERMS
TeamtailorDiscoveryDepth = AtsDiscoveryDepth
TeamtailorDiscoveryQuery = AtsDiscoveryQuery
TeamtailorDiscoveryResult = AtsDiscoveryResult


@dataclass(frozen=True)
class TeamtailorBoard:
    platform_company_slug: str
    board_url: str


@dataclass(frozen=True)
class TeamtailorFetchResult:
    response: str
    endpoint: str


@dataclass
class TeamtailorCollectionResult:
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
    def search(self, search_query: TeamtailorDiscoveryQuery) -> dict[str, Any]: ...


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def teamtailor_board_from_slug(platform_company_slug: str) -> TeamtailorBoard:
    slug = platform_company_slug.strip().strip("/").casefold()
    if not slug:
        raise ValueError("Teamtailor company slug is required.")
    return TeamtailorBoard(
        platform_company_slug=slug,
        board_url=f"https://{quote(slug, safe='-_~.')}.teamtailor.com",
    )


def parse_teamtailor_board_url(value: object | None) -> TeamtailorBoard | None:
    raw_url = str(value or "").strip()
    if not raw_url:
        return None
    if "://" not in raw_url and ".teamtailor.com" in raw_url.split(
        "/", 1
    )[0].casefold():
        raw_url = f"https://{raw_url}"

    parsed_url = urlparse(raw_url)
    if parsed_url.scheme not in {"http", "https"}:
        return None

    host = parsed_url.netloc.casefold()
    suffix = ".teamtailor.com"
    if not host.endswith(suffix):
        return None

    slug = unquote(host[: -len(suffix)]).strip()
    if not slug or "." in slug:
        return None

    return teamtailor_board_from_slug(slug)


def normalize_teamtailor_board(value: str) -> TeamtailorBoard:
    parsed_board = parse_teamtailor_board_url(value)
    if parsed_board is not None:
        return parsed_board
    return teamtailor_board_from_slug(value)


TEAMTAILOR_DISCOVERY_PROVIDER = AtsDiscoveryProvider(
    platform=SourceName.TEAMTAILOR.value,
    site="*.teamtailor.com",
    parse_board_url=parse_teamtailor_board_url,
)


def build_teamtailor_discovery_search_query(
    *,
    terms: Iterable[object | None] = (),
) -> str:
    return build_ats_discovery_search_query(
        provider=TEAMTAILOR_DISCOVERY_PROVIDER,
        terms=terms,
    )


def generate_teamtailor_discovery_queries(
    *,
    countries_config: CountriesConfig,
    country_codes: Iterable[str],
    limit: int | None = None,
    num: int = DEFAULT_TEAMTAILOR_DISCOVERY_RESULTS_PER_QUERY,
    pages: int = DEFAULT_TEAMTAILOR_DISCOVERY_PAGES,
    location_depth: LocationDepth = LocationDepth.CITIES,
    discovery_depth: TeamtailorDiscoveryDepth = TeamtailorDiscoveryDepth.EXHAUSTIVE,
    role_terms: Iterable[str] = (),
    signal_terms: Iterable[str] = TEAMTAILOR_DISCOVERY_SIGNAL_TERMS,
) -> list[TeamtailorDiscoveryQuery]:
    return generate_ats_discovery_queries(
        provider=TEAMTAILOR_DISCOVERY_PROVIDER,
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


def extract_teamtailor_board_records(
    *,
    discovery_query: TeamtailorDiscoveryQuery,
    response: dict[str, Any],
    collected_at: str,
) -> list[dict[str, Any]]:
    return extract_ats_board_records(
        provider=TEAMTAILOR_DISCOVERY_PROVIDER,
        discovery_query=discovery_query,
        response=response,
        collected_at=collected_at,
    )


def discover_teamtailor_boards(
    discovery_queries: Iterable[TeamtailorDiscoveryQuery],
    *,
    client: DiscoverySearchClient,
    data_dir: Path = DEFAULT_DATA_DIR,
    clock: Callable[[], str] = utc_now_iso,
) -> TeamtailorDiscoveryResult:
    return discover_ats_boards(
        discovery_queries,
        provider=TEAMTAILOR_DISCOVERY_PROVIDER,
        client=client,
        data_dir=data_dir,
        clock=clock,
    )


def build_teamtailor_rss_endpoint(platform_company_slug: str) -> str:
    slug = platform_company_slug.strip().strip("/").casefold()
    if not slug:
        raise ValueError("Teamtailor company slug is required.")
    return f"https://{quote(slug, safe='-_~.')}.teamtailor.com/jobs.rss"


class TeamtailorClient:
    def __init__(
        self,
        *,
        timeout: float = 30.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._client = http_client or httpx.Client(timeout=timeout)
        self._owns_client = http_client is None

    def fetch_board(self, board_url_or_slug: str) -> TeamtailorFetchResult:
        board = normalize_teamtailor_board(board_url_or_slug)
        endpoint = build_teamtailor_rss_endpoint(board.platform_company_slug)
        response = self._client.get(
            endpoint,
            headers={"User-Agent": "ai-hiring-radar-teamtailor-prototype"},
        )
        response.raise_for_status()
        return TeamtailorFetchResult(response=response.text, endpoint=endpoint)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


def build_raw_teamtailor_response_record(
    *,
    board: TeamtailorBoard,
    response: str,
    collected_at: str,
    endpoint: str | None = None,
) -> dict[str, Any]:
    return {
        "record_type": RAW_ATS_RECORD_TYPE,
        "platform": SourceName.TEAMTAILOR.value,
        "access_type": TEAMTAILOR_ACCESS_TYPE,
        "official_api": False,
        "stability": TEAMTAILOR_STABILITY,
        "source": SourceName.TEAMTAILOR.value,
        "source_mode": SourceMode.PUBLIC_JOB_BOARD_ENDPOINT.value,
        "platform_company_slug": board.platform_company_slug,
        "board_url": board.board_url,
        "endpoint": endpoint or build_teamtailor_rss_endpoint(board.platform_company_slug),
        "response_format": "rss_xml",
        "collected_at": collected_at,
        "title_prefilter": _teamtailor_title_prefilter_metadata(response),
        "response": response,
    }


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _xml_child_text(element: ET.Element, name: str) -> str | None:
    for child in element:
        if _xml_local_name(child.tag) == name:
            return " ".join(str(child.text or "").split()).strip() or None
    return None


def _teamtailor_items(response: str) -> list[ET.Element]:
    try:
        root = ET.fromstring(response)
    except ET.ParseError:
        return []
    if _xml_local_name(root.tag) == "item":
        return [root]
    return [element for element in root.iter() if _xml_local_name(element.tag) == "item"]


def _teamtailor_title_prefilter_metadata(response: str) -> dict[str, int | str]:
    items = _teamtailor_items(response)
    matched_count = sum(
        1
        for item in items
        if is_ai_role_title_candidate(_xml_child_text(item, "title"))
    )
    return title_prefilter_metadata(
        listed_count=len(items),
        matched_count=matched_count,
    )


def _has_rss_feed_response(response: str) -> bool:
    normalized_response = response.casefold()
    return "<rss" in normalized_response and "<channel" in normalized_response


def _collection_error_record(
    *,
    board: TeamtailorBoard,
    error: str,
    error_type: str | None = None,
    output_file: str | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "platform": SourceName.TEAMTAILOR.value,
        "platform_company_slug": board.platform_company_slug,
        "board_url": board.board_url,
        "error": error,
    }
    if error_type is not None:
        record["error_type"] = error_type
    if output_file is not None:
        record["output_file"] = output_file
    return record


def collect_teamtailor_boards(
    board_urls_or_slugs: Iterable[str],
    *,
    client: TeamtailorClient,
    data_dir: Path = DEFAULT_DATA_DIR,
    clock: Callable[[], str] = utc_now_iso,
) -> TeamtailorCollectionResult:
    boards_by_slug: dict[str, TeamtailorBoard] = {}
    for value in board_urls_or_slugs:
        board = normalize_teamtailor_board(value)
        boards_by_slug.setdefault(board.platform_company_slug, board)

    boards = list(boards_by_slug.values())
    started_at = clock()
    collection_date = started_at[:10]
    result_files: list[str] = []
    errors: list[dict[str, Any]] = []

    for board in boards:
        try:
            fetch_result = client.fetch_board(board.board_url)
            raw_record = build_raw_teamtailor_response_record(
                board=board,
                response=fetch_result.response,
                endpoint=fetch_result.endpoint,
                collected_at=clock(),
            )
            path = write_raw_ats_response(
                raw_record,
                platform_company_slug=board.platform_company_slug,
                collection_date=collection_date,
                data_dir=data_dir,
                platform=SourceName.TEAMTAILOR.value,
            )
            output_file = path.as_posix()
            result_files.append(output_file)

            if not _has_rss_feed_response(fetch_result.response):
                errors.append(
                    _collection_error_record(
                        board=board,
                        error="Teamtailor response did not look like an RSS feed.",
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
        platform=SourceName.TEAMTAILOR.value,
    ) / "manifest.json"
    write_json(
        manifest_path,
        {
            "record_type": ATS_COLLECTION_MANIFEST_RECORD_TYPE,
            "platform": SourceName.TEAMTAILOR.value,
            "source": SourceName.TEAMTAILOR.value,
            "source_mode": SourceMode.PUBLIC_JOB_BOARD_ENDPOINT.value,
            "started_at": started_at,
            "finished_at": finished_at,
            "board_count": len(boards),
            "result_files": result_files,
            "errors": errors,
        },
    )

    return TeamtailorCollectionResult(
        manifest_path=manifest_path,
        board_count=len(boards),
        result_files=result_files,
        errors=errors,
    )
