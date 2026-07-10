from __future__ import annotations

import time
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


RAW_ATS_RECORD_TYPE = "raw_ats_response"
ATS_COLLECTION_MANIFEST_RECORD_TYPE = "ats_collection_manifest"
PERSONIO_ACCESS_TYPE = "public_job_board_endpoint"
PERSONIO_STABILITY = "stable_public_xml_feed"
DEFAULT_PERSONIO_LANGUAGE = "en"
DEFAULT_PERSONIO_DISCOVERY_RESULTS_PER_QUERY = DEFAULT_ATS_DISCOVERY_RESULTS_PER_QUERY
MAX_PERSONIO_DISCOVERY_RESULTS_PER_QUERY = MAX_ATS_DISCOVERY_RESULTS_PER_QUERY
DEFAULT_PERSONIO_DISCOVERY_PAGES = DEFAULT_ATS_DISCOVERY_PAGES
PERSONIO_DISCOVERY_SIGNAL_TERMS = DEFAULT_ATS_DISCOVERY_SIGNAL_TERMS
PersonioDiscoveryDepth = AtsDiscoveryDepth
PersonioDiscoveryQuery = AtsDiscoveryQuery
PersonioDiscoveryResult = AtsDiscoveryResult


@dataclass(frozen=True)
class PersonioBoard:
    platform_company_slug: str
    board_url: str


@dataclass
class PersonioCollectionResult:
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
    def search(self, search_query: PersonioDiscoveryQuery) -> dict[str, Any]: ...


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def personio_board_from_slug(platform_company_slug: str) -> PersonioBoard:
    slug = platform_company_slug.strip().strip("/").casefold()
    if not slug:
        raise ValueError("Personio company slug is required.")
    return PersonioBoard(
        platform_company_slug=slug,
        board_url=f"https://{quote(slug, safe='-_~.')}.jobs.personio.com",
    )


def parse_personio_board_url(value: object | None) -> PersonioBoard | None:
    raw_url = str(value or "").strip()
    if not raw_url:
        return None
    if "://" not in raw_url and ".jobs.personio.com" in raw_url.split(
        "/", 1
    )[0].casefold():
        raw_url = f"https://{raw_url}"

    parsed_url = urlparse(raw_url)
    if parsed_url.scheme not in {"http", "https"}:
        return None

    host = parsed_url.netloc.casefold()
    suffix = ".jobs.personio.com"
    if not host.endswith(suffix):
        return None

    slug = unquote(host[: -len(suffix)]).strip()
    if not slug or "." in slug:
        return None

    return personio_board_from_slug(slug)


def normalize_personio_board(value: str) -> PersonioBoard:
    parsed_board = parse_personio_board_url(value)
    if parsed_board is not None:
        return parsed_board
    return personio_board_from_slug(value)


PERSONIO_DISCOVERY_PROVIDER = AtsDiscoveryProvider(
    platform=SourceName.PERSONIO.value,
    site="*.jobs.personio.com",
    parse_board_url=parse_personio_board_url,
)


def build_personio_discovery_search_query(
    *,
    terms: Iterable[object | None] = (),
) -> str:
    return build_ats_discovery_search_query(
        provider=PERSONIO_DISCOVERY_PROVIDER,
        terms=terms,
    )


def generate_personio_discovery_queries(
    *,
    countries_config: CountriesConfig,
    country_codes: Iterable[str],
    limit: int | None = None,
    num: int = DEFAULT_PERSONIO_DISCOVERY_RESULTS_PER_QUERY,
    pages: int = DEFAULT_PERSONIO_DISCOVERY_PAGES,
    location_depth: LocationDepth = LocationDepth.CITIES,
    discovery_depth: PersonioDiscoveryDepth = PersonioDiscoveryDepth.EXHAUSTIVE,
    role_terms: Iterable[str] = (),
    signal_terms: Iterable[str] = PERSONIO_DISCOVERY_SIGNAL_TERMS,
) -> list[PersonioDiscoveryQuery]:
    return generate_ats_discovery_queries(
        provider=PERSONIO_DISCOVERY_PROVIDER,
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


def extract_personio_board_records(
    *,
    discovery_query: PersonioDiscoveryQuery,
    response: dict[str, Any],
    collected_at: str,
) -> list[dict[str, Any]]:
    return extract_ats_board_records(
        provider=PERSONIO_DISCOVERY_PROVIDER,
        discovery_query=discovery_query,
        response=response,
        collected_at=collected_at,
    )


def discover_personio_boards(
    discovery_queries: Iterable[PersonioDiscoveryQuery],
    *,
    client: DiscoverySearchClient,
    data_dir: Path = DEFAULT_DATA_DIR,
    clock: Callable[[], str] = utc_now_iso,
) -> PersonioDiscoveryResult:
    return discover_ats_boards(
        discovery_queries,
        provider=PERSONIO_DISCOVERY_PROVIDER,
        client=client,
        data_dir=data_dir,
        clock=clock,
    )


def build_personio_xml_endpoint(
    platform_company_slug: str,
    *,
    language: str = DEFAULT_PERSONIO_LANGUAGE,
) -> str:
    slug = platform_company_slug.strip().strip("/").casefold()
    if not slug:
        raise ValueError("Personio company slug is required.")
    normalized_language = language.strip() or DEFAULT_PERSONIO_LANGUAGE
    return (
        f"https://{quote(slug, safe='-_~.')}.jobs.personio.com/xml"
        f"?language={quote(normalized_language, safe='-_~.')}"
    )


@dataclass(frozen=True)
class PersonioFetchResult:
    response: str
    endpoint: str
    language: str


class PersonioClient:
    def __init__(
        self,
        *,
        language: str = DEFAULT_PERSONIO_LANGUAGE,
        timeout: float = 30.0,
        http_client: httpx.Client | None = None,
        request_delay_seconds: float = DEFAULT_REQUEST_DELAY_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.language = language
        self._client = http_client or httpx.Client(timeout=timeout)
        self._owns_client = http_client is None
        self._requester = ResilientHttpRequester(
            http_client=self._client,
            request_delay_seconds=request_delay_seconds,
            max_retries=max_retries,
            sleeper=sleeper,
        )

    def fetch_board(self, board_url_or_slug: str) -> PersonioFetchResult:
        board = normalize_personio_board(board_url_or_slug)
        endpoint = build_personio_xml_endpoint(
            board.platform_company_slug,
            language=self.language,
        )
        response = self._requester.get(
            endpoint,
            headers={"User-Agent": "ai-hiring-radar-personio-prototype"},
        )
        return PersonioFetchResult(
            response=response.text,
            endpoint=endpoint,
            language=self.language,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


def build_raw_personio_response_record(
    *,
    board: PersonioBoard,
    response: str,
    collected_at: str,
    endpoint: str | None = None,
    language: str = DEFAULT_PERSONIO_LANGUAGE,
) -> dict[str, Any]:
    return {
        "record_type": RAW_ATS_RECORD_TYPE,
        "platform": SourceName.PERSONIO.value,
        "access_type": PERSONIO_ACCESS_TYPE,
        "official_api": True,
        "stability": PERSONIO_STABILITY,
        "source": SourceName.PERSONIO.value,
        "source_mode": SourceMode.PUBLIC_JOB_BOARD_ENDPOINT.value,
        "platform_company_slug": board.platform_company_slug,
        "board_url": board.board_url,
        "endpoint": endpoint
        or build_personio_xml_endpoint(board.platform_company_slug, language=language),
        "request_params": {"language": language},
        "response_format": "xml",
        "collected_at": collected_at,
        "title_prefilter": _personio_title_prefilter_metadata(response),
        "response": response,
    }


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _xml_child_text(element: ET.Element, name: str) -> str | None:
    for child in element:
        if _xml_local_name(child.tag) == name:
            return " ".join(str(child.text or "").split()).strip() or None
    return None


def _personio_positions(response: str) -> list[ET.Element]:
    try:
        root = ET.fromstring(response)
    except ET.ParseError:
        return []
    if _xml_local_name(root.tag) == "position":
        return [root]
    return [
        element for element in root.iter() if _xml_local_name(element.tag) == "position"
    ]


def _personio_title_prefilter_metadata(response: str) -> dict[str, int | str]:
    positions = _personio_positions(response)
    matched_count = sum(
        1
        for position in positions
        if is_ai_role_title_candidate(_xml_child_text(position, "name"))
    )
    return title_prefilter_metadata(
        listed_count=len(positions),
        matched_count=matched_count,
        source_field="name",
    )


def _has_xml_feed_response(response: str) -> bool:
    normalized_response = response.casefold()
    return "<workzag-jobs" in normalized_response or "<position" in normalized_response


def _collection_error_record(
    *,
    board: PersonioBoard,
    error: str,
    error_type: str | None = None,
    output_file: str | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "platform": SourceName.PERSONIO.value,
        "platform_company_slug": board.platform_company_slug,
        "board_url": board.board_url,
        "error": error,
    }
    if error_type is not None:
        record["error_type"] = error_type
    if output_file is not None:
        record["output_file"] = output_file
    return record


def collect_personio_boards(
    board_urls_or_slugs: Iterable[str],
    *,
    client: PersonioClient,
    data_dir: Path = DEFAULT_DATA_DIR,
    clock: Callable[[], str] = utc_now_iso,
    collection_date: str | None = None,
    resume: bool = True,
) -> PersonioCollectionResult:
    boards_by_slug: dict[str, PersonioBoard] = {}
    for value in board_urls_or_slugs:
        board = normalize_personio_board(value)
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
            platform=SourceName.PERSONIO.value,
        )
        if resume and is_valid_raw_ats_resume_file(
            resume_path,
            platform=SourceName.PERSONIO.value,
            platform_company_slug=board.platform_company_slug,
        ):
            output_file = resume_path.as_posix()
            result_files.append(output_file)
            resumed_files.append(output_file)
            continue

        try:
            fetch_result = client.fetch_board(board.board_url)
            raw_record = build_raw_personio_response_record(
                board=board,
                response=fetch_result.response,
                endpoint=fetch_result.endpoint,
                language=fetch_result.language,
                collected_at=clock(),
            )
            path = write_raw_ats_response(
                raw_record,
                platform_company_slug=board.platform_company_slug,
                collection_date=effective_collection_date,
                data_dir=data_dir,
                platform=SourceName.PERSONIO.value,
            )
            output_file = path.as_posix()
            result_files.append(output_file)
            written_files.append(output_file)

            if not _has_xml_feed_response(fetch_result.response):
                errors.append(
                    _collection_error_record(
                        board=board,
                        error="Personio response did not look like a jobs XML feed.",
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
        platform=SourceName.PERSONIO.value,
    ) / "manifest.json"
    write_json(
        manifest_path,
        {
            "record_type": ATS_COLLECTION_MANIFEST_RECORD_TYPE,
            "platform": SourceName.PERSONIO.value,
            "source": SourceName.PERSONIO.value,
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

    return PersonioCollectionResult(
        manifest_path=manifest_path,
        board_count=len(boards),
        result_files=result_files,
        written_files=written_files,
        resumed_files=resumed_files,
        errors=errors,
    )
