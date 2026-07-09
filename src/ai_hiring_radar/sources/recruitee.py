from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote, unquote, urlparse

import httpx

from ai_hiring_radar.classify import (
    has_ai_signal,
    is_excluded_ai_trainer_title,
    match_known_role,
)
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
RECRUITEE_ACCESS_TYPE = "public_job_board_endpoint"
RECRUITEE_STABILITY = "stable_public_endpoint"
DEFAULT_RECRUITEE_DISCOVERY_RESULTS_PER_QUERY = DEFAULT_ATS_DISCOVERY_RESULTS_PER_QUERY
MAX_RECRUITEE_DISCOVERY_RESULTS_PER_QUERY = MAX_ATS_DISCOVERY_RESULTS_PER_QUERY
DEFAULT_RECRUITEE_DISCOVERY_PAGES = DEFAULT_ATS_DISCOVERY_PAGES
RECRUITEE_DISCOVERY_SIGNAL_TERMS = DEFAULT_ATS_DISCOVERY_SIGNAL_TERMS
RECRUITEE_RESERVED_SUBDOMAINS = {
    "api",
    "app",
    "assets",
    "blog",
    "developers",
    "docs",
    "help",
    "support",
    "www",
}
RECRUITEE_SUBDOMAIN_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
RecruiteeDiscoveryDepth = AtsDiscoveryDepth
RecruiteeDiscoveryQuery = AtsDiscoveryQuery
RecruiteeDiscoveryResult = AtsDiscoveryResult


@dataclass(frozen=True)
class RecruiteeBoard:
    platform_company_slug: str
    board_url: str


@dataclass(frozen=True)
class RecruiteeFetchResult:
    response: dict[str, Any]
    endpoint: str


@dataclass(frozen=True)
class RecruiteeOfferDetailResult:
    response: dict[str, Any]
    endpoint: str
    offer_identifier: str


@dataclass
class RecruiteeCollectionResult:
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
    def search(self, search_query: RecruiteeDiscoveryQuery) -> dict[str, Any]: ...


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _normalize_recruitee_slug(platform_company_slug: str) -> str:
    slug = platform_company_slug.strip().strip("/").casefold()
    if not slug:
        raise ValueError("Recruitee company slug is required.")
    if (
        slug in RECRUITEE_RESERVED_SUBDOMAINS
        or not RECRUITEE_SUBDOMAIN_RE.fullmatch(slug)
    ):
        raise ValueError(
            "Recruitee company slug must be a DNS-safe subdomain such as 'acme-ai'."
        )
    return slug


def recruitee_board_from_slug(platform_company_slug: str) -> RecruiteeBoard:
    slug = _normalize_recruitee_slug(platform_company_slug)
    return RecruiteeBoard(
        platform_company_slug=slug,
        board_url=f"https://{slug}.recruitee.com",
    )


def parse_recruitee_board_url(value: object | None) -> RecruiteeBoard | None:
    raw_url = str(value or "").strip()
    if not raw_url:
        return None
    if "://" not in raw_url and ".recruitee.com" in raw_url.split("/", 1)[0].casefold():
        raw_url = f"https://{raw_url}"

    parsed_url = urlparse(raw_url)
    if parsed_url.scheme not in {"http", "https"}:
        return None

    host = parsed_url.netloc.casefold()
    suffix = ".recruitee.com"
    if not host.endswith(suffix):
        return None

    slug = unquote(host[: -len(suffix)]).strip().casefold()
    try:
        return recruitee_board_from_slug(slug)
    except ValueError:
        return None


def normalize_recruitee_board(value: str) -> RecruiteeBoard:
    parsed_board = parse_recruitee_board_url(value)
    if parsed_board is not None:
        return parsed_board
    return recruitee_board_from_slug(value)


RECRUITEE_DISCOVERY_PROVIDER = AtsDiscoveryProvider(
    platform=SourceName.RECRUITEE.value,
    site="*.recruitee.com",
    parse_board_url=parse_recruitee_board_url,
)


def build_recruitee_discovery_search_query(
    *,
    terms: Iterable[object | None] = (),
) -> str:
    return build_ats_discovery_search_query(
        provider=RECRUITEE_DISCOVERY_PROVIDER,
        terms=terms,
    )


def generate_recruitee_discovery_queries(
    *,
    countries_config: CountriesConfig,
    country_codes: Iterable[str],
    limit: int | None = None,
    num: int = DEFAULT_RECRUITEE_DISCOVERY_RESULTS_PER_QUERY,
    pages: int = DEFAULT_RECRUITEE_DISCOVERY_PAGES,
    location_depth: LocationDepth = LocationDepth.CITIES,
    discovery_depth: RecruiteeDiscoveryDepth = RecruiteeDiscoveryDepth.EXHAUSTIVE,
    role_terms: Iterable[str] = (),
    signal_terms: Iterable[str] = RECRUITEE_DISCOVERY_SIGNAL_TERMS,
) -> list[RecruiteeDiscoveryQuery]:
    return generate_ats_discovery_queries(
        provider=RECRUITEE_DISCOVERY_PROVIDER,
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


def extract_recruitee_board_records(
    *,
    discovery_query: RecruiteeDiscoveryQuery,
    response: dict[str, Any],
    collected_at: str,
) -> list[dict[str, Any]]:
    return extract_ats_board_records(
        provider=RECRUITEE_DISCOVERY_PROVIDER,
        discovery_query=discovery_query,
        response=response,
        collected_at=collected_at,
    )


def discover_recruitee_boards(
    discovery_queries: Iterable[RecruiteeDiscoveryQuery],
    *,
    client: DiscoverySearchClient,
    data_dir: Path = DEFAULT_DATA_DIR,
    clock: Callable[[], str] = utc_now_iso,
) -> RecruiteeDiscoveryResult:
    return discover_ats_boards(
        discovery_queries,
        provider=RECRUITEE_DISCOVERY_PROVIDER,
        client=client,
        data_dir=data_dir,
        clock=clock,
    )


def build_recruitee_offers_endpoint(platform_company_slug: str) -> str:
    slug = _normalize_recruitee_slug(platform_company_slug)
    return f"https://{slug}.recruitee.com/api/offers/"


def build_recruitee_offer_detail_endpoint(
    *,
    platform_company_slug: str,
    offer_identifier: str,
) -> str:
    slug = _normalize_recruitee_slug(platform_company_slug)
    identifier = str(offer_identifier or "").strip().strip("/")
    if not identifier:
        raise ValueError("Recruitee offer identifier is required.")
    return (
        f"https://{slug}.recruitee.com/api/offers/"
        f"{quote(identifier, safe='-_~.')}"
    )


def _clean_identifier(value: object | None) -> str | None:
    identifier = str(value or "").strip()
    return identifier or None


def _offers(response: dict[str, Any]) -> list[dict[str, Any]]:
    offers = response.get("offers")
    if not isinstance(offers, list):
        return []
    return [item for item in offers if isinstance(item, dict)]


def _offer_platform_job_id(offer: dict[str, Any]) -> str | None:
    return _clean_identifier(offer.get("id")) or _clean_identifier(offer.get("slug"))


def _offer_detail_identifier(offer: dict[str, Any]) -> str | None:
    return _clean_identifier(offer.get("id")) or _clean_identifier(offer.get("slug"))


def _is_recruitee_detail_candidate_title(value: object | None) -> bool:
    if is_excluded_ai_trainer_title(value):
        return False
    return match_known_role(value) is not None or has_ai_signal(value)


class RecruiteeClient:
    def __init__(
        self,
        *,
        timeout: float = 30.0,
        http_client: httpx.Client | None = None,
        request_delay_seconds: float = 0.2,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = http_client or httpx.Client(timeout=timeout)
        self._owns_client = http_client is None
        self._request_delay_seconds = max(request_delay_seconds, 0.0)
        self._sleeper = sleeper
        self._request_count = 0

    def _wait_between_requests(self) -> None:
        if self._request_count > 0 and self._request_delay_seconds > 0:
            self._sleeper(self._request_delay_seconds)
        self._request_count += 1

    def fetch_board(self, board_url_or_slug: str) -> RecruiteeFetchResult:
        board = normalize_recruitee_board(board_url_or_slug)
        endpoint = build_recruitee_offers_endpoint(board.platform_company_slug)
        self._wait_between_requests()
        response = self._client.get(
            endpoint,
            headers={"User-Agent": "ai-hiring-radar-recruitee-prototype"},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Expected Recruitee to return a JSON object.")
        return RecruiteeFetchResult(response=payload, endpoint=endpoint)

    def fetch_offer_detail(
        self,
        *,
        board_url_or_slug: str,
        offer_identifier: str,
    ) -> RecruiteeOfferDetailResult:
        board = normalize_recruitee_board(board_url_or_slug)
        endpoint = build_recruitee_offer_detail_endpoint(
            platform_company_slug=board.platform_company_slug,
            offer_identifier=offer_identifier,
        )
        self._wait_between_requests()
        response = self._client.get(
            endpoint,
            headers={"User-Agent": "ai-hiring-radar-recruitee-prototype"},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Expected Recruitee offer detail to return a JSON object.")
        return RecruiteeOfferDetailResult(
            response=payload,
            endpoint=endpoint,
            offer_identifier=offer_identifier,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


def build_raw_recruitee_response_record(
    *,
    board: RecruiteeBoard,
    response: dict[str, Any],
    collected_at: str,
    endpoint: str | None = None,
    offer_detail_responses: dict[str, Any] | None = None,
    offer_detail_endpoints: dict[str, str] | None = None,
    offer_detail_errors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "record_type": RAW_ATS_RECORD_TYPE,
        "platform": SourceName.RECRUITEE.value,
        "access_type": RECRUITEE_ACCESS_TYPE,
        "official_api": True,
        "stability": RECRUITEE_STABILITY,
        "source": SourceName.RECRUITEE.value,
        "source_mode": SourceMode.PUBLIC_JOB_BOARD_ENDPOINT.value,
        "platform_company_slug": board.platform_company_slug,
        "board_url": board.board_url,
        "endpoint": endpoint or build_recruitee_offers_endpoint(board.platform_company_slug),
        "request_params": {},
        "response_format": "json",
        "offer_detail_endpoint_template": (
            f"https://{board.platform_company_slug}.recruitee.com"
            "/api/offers/{offer_identifier}"
        ),
        "offer_detail_endpoints": offer_detail_endpoints or {},
        "offer_detail_responses": offer_detail_responses or {},
        "offer_detail_errors": offer_detail_errors or [],
        "collected_at": collected_at,
        "response": response,
    }


def _has_offers_response(response: dict[str, Any]) -> bool:
    return isinstance(response.get("offers"), list)


def _collection_error_record(
    *,
    board: RecruiteeBoard,
    error: str,
    error_type: str | None = None,
    output_file: str | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "platform": SourceName.RECRUITEE.value,
        "platform_company_slug": board.platform_company_slug,
        "board_url": board.board_url,
        "error": error,
    }
    if error_type is not None:
        record["error_type"] = error_type
    if output_file is not None:
        record["output_file"] = output_file
    return record


def _offer_detail_error_record(
    *,
    board: RecruiteeBoard,
    platform_job_id: str,
    offer_identifier: str,
    error: str,
    error_type: str | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "platform": SourceName.RECRUITEE.value,
        "platform_company_slug": board.platform_company_slug,
        "board_url": board.board_url,
        "platform_job_id": platform_job_id,
        "offer_identifier": offer_identifier,
        "error_scope": "offer_detail",
        "error": error,
    }
    if error_type is not None:
        record["error_type"] = error_type
    return record


def collect_recruitee_boards(
    board_urls_or_slugs: Iterable[str],
    *,
    client: RecruiteeClient,
    data_dir: Path = DEFAULT_DATA_DIR,
    clock: Callable[[], str] = utc_now_iso,
) -> RecruiteeCollectionResult:
    boards_by_slug: dict[str, RecruiteeBoard] = {}
    for value in board_urls_or_slugs:
        board = normalize_recruitee_board(value)
        boards_by_slug.setdefault(board.platform_company_slug, board)

    boards = list(boards_by_slug.values())
    started_at = clock()
    collection_date = started_at[:10]
    result_files: list[str] = []
    errors: list[dict[str, Any]] = []

    for board in boards:
        try:
            fetch_result = client.fetch_board(board.board_url)
            offer_detail_responses: dict[str, Any] = {}
            offer_detail_endpoints: dict[str, str] = {}
            offer_detail_errors: list[dict[str, Any]] = []

            for offer in _offers(fetch_result.response):
                if not _is_recruitee_detail_candidate_title(
                    offer.get("title") or offer.get("name")
                ):
                    continue
                platform_job_id = _offer_platform_job_id(offer)
                offer_identifier = _offer_detail_identifier(offer)
                if platform_job_id is None or offer_identifier is None:
                    continue
                try:
                    detail_result = client.fetch_offer_detail(
                        board_url_or_slug=board.board_url,
                        offer_identifier=offer_identifier,
                    )
                    offer_detail_responses[platform_job_id] = detail_result.response
                    offer_detail_endpoints[platform_job_id] = detail_result.endpoint
                except Exception as exc:  # noqa: BLE001 - keep collecting other jobs.
                    error_record = _offer_detail_error_record(
                        board=board,
                        platform_job_id=platform_job_id,
                        offer_identifier=offer_identifier,
                        error=str(exc),
                        error_type=exc.__class__.__name__,
                    )
                    offer_detail_errors.append(error_record)
                    errors.append(error_record)

            raw_record = build_raw_recruitee_response_record(
                board=board,
                response=fetch_result.response,
                endpoint=fetch_result.endpoint,
                offer_detail_responses=offer_detail_responses,
                offer_detail_endpoints=offer_detail_endpoints,
                offer_detail_errors=offer_detail_errors,
                collected_at=clock(),
            )
            path = write_raw_ats_response(
                raw_record,
                platform_company_slug=board.platform_company_slug,
                collection_date=collection_date,
                data_dir=data_dir,
                platform=SourceName.RECRUITEE.value,
            )
            output_file = path.as_posix()
            result_files.append(output_file)

            if not _has_offers_response(fetch_result.response):
                errors.append(
                    _collection_error_record(
                        board=board,
                        error="Recruitee response did not contain an offers list.",
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
        platform=SourceName.RECRUITEE.value,
    ) / "manifest.json"
    write_json(
        manifest_path,
        {
            "record_type": ATS_COLLECTION_MANIFEST_RECORD_TYPE,
            "platform": SourceName.RECRUITEE.value,
            "source": SourceName.RECRUITEE.value,
            "source_mode": SourceMode.PUBLIC_JOB_BOARD_ENDPOINT.value,
            "started_at": started_at,
            "finished_at": finished_at,
            "board_count": len(boards),
            "result_files": result_files,
            "errors": errors,
        },
    )

    return RecruiteeCollectionResult(
        manifest_path=manifest_path,
        board_count=len(boards),
        result_files=result_files,
        errors=errors,
    )
