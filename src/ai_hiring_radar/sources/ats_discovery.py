from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

import httpx

from ai_hiring_radar.config import CountriesConfig, CountryConfig, SearchLocationConfig
from ai_hiring_radar.models import SourceMode, SourceName
from ai_hiring_radar.search_locations import LocationDepth, iter_search_locations
from ai_hiring_radar.storage_json import (
    DEFAULT_DATA_DIR,
    ats_discovery_dir,
    write_json,
    write_jsonl,
)


DEFAULT_ATS_DISCOVERY_RESULTS_PER_QUERY = 10
MAX_ATS_DISCOVERY_RESULTS_PER_QUERY = 10
DEFAULT_ATS_DISCOVERY_PAGES = 2
DEFAULT_ATS_DISCOVERY_SIGNAL_TERMS = (
    "AI",
    "Artificial Intelligence",
    "LLM",
    "GenAI",
    "Generative AI",
    "OpenAI",
    "Azure OpenAI",
    "Anthropic",
    "RAG",
    "vector search",
    "Copilot",
    "Agent",
)
ATS_COMPANY_BOARD_RECORD_TYPE = "ats_company_board"
ATS_DISCOVERY_MANIFEST_RECORD_TYPE = "ats_discovery_manifest"
ATS_DISCOVERY_SOURCE = "search_index"


class AtsDiscoveryDepth(StrEnum):
    STANDARD = "standard"
    BROAD = "broad"
    EXHAUSTIVE = "exhaustive"


@dataclass(frozen=True)
class AtsDiscoveryProvider:
    platform: str
    site: str
    parse_board_url: Callable[[object | None], Any | None]


@dataclass(frozen=True)
class AtsDiscoveryQuery:
    country_code: str
    country: str
    search_location_label: str
    query_location: str
    serper_location: str
    discovery_query_type: str
    discovery_terms: tuple[str, ...]
    page: int
    search_query: str
    request_params: dict[str, str | int]


@dataclass
class AtsDiscoveryResult:
    manifest_path: Path
    boards_path: Path
    query_count: int
    boards: list[dict[str, Any]]
    errors: list[dict[str, Any]]

    @property
    def board_count(self) -> int:
        return len(self.boards)

    @property
    def error_count(self) -> int:
        return len(self.errors)


class DiscoverySearchClient(Protocol):
    def search(self, search_query: AtsDiscoveryQuery) -> dict[str, Any]: ...


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _clean_discovery_term(value: object | None) -> str:
    return " ".join(str(value or "").split()).strip()


def unique_discovery_terms(values: Iterable[object | None]) -> tuple[str, ...]:
    terms: list[str] = []
    seen: set[str] = set()
    for value in values:
        term = _clean_discovery_term(value)
        key = term.casefold()
        if term and key not in seen:
            seen.add(key)
            terms.append(term)
    return tuple(terms)


def build_ats_discovery_search_query(
    *,
    provider: AtsDiscoveryProvider,
    terms: Iterable[object | None] = (),
) -> str:
    normalized_terms = unique_discovery_terms(terms)
    if not normalized_terms:
        return f"site:{provider.site}"
    quoted_terms = " ".join(f'"{term}"' for term in normalized_terms)
    return f"site:{provider.site} {quoted_terms}"


def _page_values(pages: int) -> range:
    if pages < 1:
        raise ValueError("Pages must be greater than zero.")
    return range(1, pages + 1)


def _discovery_request_params(
    *,
    search_query: str,
    country: CountryConfig,
    search_location: SearchLocationConfig,
    num: int,
    page: int,
) -> dict[str, str | int]:
    if num < 1:
        raise ValueError("Results per query must be greater than zero.")
    if num > MAX_ATS_DISCOVERY_RESULTS_PER_QUERY:
        raise ValueError(
            "Serper accepts at most "
            f"{MAX_ATS_DISCOVERY_RESULTS_PER_QUERY} results per query."
        )

    request_params: dict[str, str | int] = {
        "q": search_query,
        "location": search_location.serper_location,
        "gl": country.gl,
        "hl": country.hl,
        "num": num,
    }
    if page > 1:
        request_params["page"] = page
    return request_params


def build_ats_discovery_query(
    *,
    provider: AtsDiscoveryProvider,
    country_code: str,
    country: CountryConfig,
    search_location: SearchLocationConfig,
    discovery_query_type: str = "location",
    terms: Iterable[object | None] = (),
    page: int = 1,
    num: int = DEFAULT_ATS_DISCOVERY_RESULTS_PER_QUERY,
) -> AtsDiscoveryQuery:
    discovery_terms = unique_discovery_terms(terms)
    if not discovery_terms and discovery_query_type == "location":
        discovery_terms = unique_discovery_terms((search_location.label,))
    search_query = build_ats_discovery_search_query(
        provider=provider,
        terms=discovery_terms,
    )

    return AtsDiscoveryQuery(
        country_code=country_code.strip().lower(),
        country=country.name,
        search_location_label=search_location.label,
        query_location=search_location.query_location,
        serper_location=search_location.serper_location,
        discovery_query_type=discovery_query_type,
        discovery_terms=discovery_terms,
        page=page,
        search_query=search_query,
        request_params=_discovery_request_params(
            search_query=search_query,
            country=country,
            search_location=search_location,
            num=num,
            page=page,
        ),
    )


def _ats_discovery_term_groups(
    *,
    country: CountryConfig,
    search_locations: list[SearchLocationConfig],
    role_terms: Iterable[str],
    signal_terms: Iterable[str],
    discovery_depth: AtsDiscoveryDepth,
) -> list[tuple[str, SearchLocationConfig, tuple[str, ...]]]:
    country_location = SearchLocationConfig(
        label=country.name,
        query_location=country.name,
        serper_location=country.search_location,
    )
    location_terms = unique_discovery_terms(
        location.label for location in search_locations
    )
    roles = unique_discovery_terms(role_terms)
    signals = unique_discovery_terms(signal_terms)

    groups: list[tuple[str, SearchLocationConfig, tuple[str, ...]]] = [
        ("site_only", country_location, ()),
    ]

    for location in search_locations:
        groups.append(("location", location, (location.label,)))

    if discovery_depth == AtsDiscoveryDepth.STANDARD:
        return _dedupe_discovery_groups(groups)

    for role in roles:
        groups.append(("role", country_location, (role,)))
    for signal in signals:
        groups.append(("ai_signal", country_location, (signal,)))
    for role in roles:
        groups.append(("role_country", country_location, (role, country.name)))
    for signal in signals:
        groups.append(("ai_signal_country", country_location, (signal, country.name)))

    if discovery_depth == AtsDiscoveryDepth.EXHAUSTIVE:
        for role in roles:
            for location_term in location_terms:
                groups.append(("role_location", country_location, (role, location_term)))
        for signal in signals:
            for location_term in location_terms:
                groups.append(
                    ("ai_signal_location", country_location, (signal, location_term))
                )

    return _dedupe_discovery_groups(groups)


def _dedupe_discovery_groups(
    groups: list[tuple[str, SearchLocationConfig, tuple[str, ...]]],
) -> list[tuple[str, SearchLocationConfig, tuple[str, ...]]]:
    deduped_groups: list[tuple[str, SearchLocationConfig, tuple[str, ...]]] = []
    seen_searches: set[tuple[str, tuple[str, ...]]] = set()
    for query_type, search_location, terms in groups:
        normalized_terms = unique_discovery_terms(terms)
        key = (search_location.serper_location.casefold(), normalized_terms)
        if key in seen_searches:
            continue
        seen_searches.add(key)
        deduped_groups.append((query_type, search_location, normalized_terms))
    return deduped_groups


def generate_ats_discovery_queries(
    *,
    provider: AtsDiscoveryProvider,
    countries_config: CountriesConfig,
    country_codes: Iterable[str],
    limit: int | None = None,
    num: int = DEFAULT_ATS_DISCOVERY_RESULTS_PER_QUERY,
    pages: int = DEFAULT_ATS_DISCOVERY_PAGES,
    location_depth: LocationDepth = LocationDepth.CITIES,
    discovery_depth: AtsDiscoveryDepth = AtsDiscoveryDepth.EXHAUSTIVE,
    role_terms: Iterable[str] = (),
    signal_terms: Iterable[str] = DEFAULT_ATS_DISCOVERY_SIGNAL_TERMS,
) -> list[AtsDiscoveryQuery]:
    if limit is not None and limit < 1:
        raise ValueError("Limit must be greater than zero.")

    queries: list[AtsDiscoveryQuery] = []
    for raw_country_code in country_codes:
        country_code = raw_country_code.strip().lower()
        country = countries_config.countries.get(country_code)
        if country is None:
            raise ValueError(f"Unknown country code: {raw_country_code}")

        search_locations = iter_search_locations(
            country,
            location_depth=location_depth,
        )
        term_groups = _ats_discovery_term_groups(
            country=country,
            search_locations=search_locations,
            role_terms=role_terms,
            signal_terms=signal_terms,
            discovery_depth=discovery_depth,
        )

        for query_type, search_location, terms in term_groups:
            for page in _page_values(pages):
                queries.append(
                    build_ats_discovery_query(
                        provider=provider,
                        country_code=country_code,
                        country=country,
                        search_location=search_location,
                        discovery_query_type=query_type,
                        terms=terms,
                        num=num,
                        page=page,
                    )
                )
                if limit is not None and len(queries) >= limit:
                    return queries

    return queries


def _organic_results(response: dict[str, Any]) -> list[dict[str, Any]]:
    organic_results = response.get("organic_results") or response.get("organic")
    if not isinstance(organic_results, list):
        return []
    return [item for item in organic_results if isinstance(item, dict)]


def _result_rank(result: dict[str, Any]) -> int | None:
    position = result.get("position")
    if isinstance(position, int):
        return position
    if isinstance(position, str) and position.isdecimal():
        return int(position)
    return None


def _board_record(
    *,
    provider: AtsDiscoveryProvider,
    discovery_query: AtsDiscoveryQuery,
    board: Any,
    result: dict[str, Any],
    collected_at: str,
) -> dict[str, Any]:
    return {
        "record_type": ATS_COMPANY_BOARD_RECORD_TYPE,
        "platform": provider.platform,
        "platform_company_slug": board.platform_company_slug,
        "board_url": board.board_url,
        "discovered_from": ATS_DISCOVERY_SOURCE,
        "source": SourceName.SERPER_GOOGLE.value,
        "source_mode": SourceMode.ATS_BOARD_DISCOVERY_SEARCH.value,
        "country_code": discovery_query.country_code,
        "country": discovery_query.country,
        "search_location_label": discovery_query.search_location_label,
        "query_location": discovery_query.query_location,
        "serper_location": discovery_query.serper_location,
        "discovery_query_type": discovery_query.discovery_query_type,
        "discovery_terms": list(discovery_query.discovery_terms),
        "search_page": discovery_query.page,
        "search_query": discovery_query.search_query,
        "result_rank": _result_rank(result),
        "source_url": str(result.get("link") or "").strip() or None,
        "title": str(result.get("title") or "").strip() or None,
        "snippet": str(result.get("snippet") or "").strip() or None,
        "collected_at": collected_at,
    }


def extract_ats_board_records(
    *,
    provider: AtsDiscoveryProvider,
    discovery_query: AtsDiscoveryQuery,
    response: dict[str, Any],
    collected_at: str,
) -> list[dict[str, Any]]:
    records_by_slug: dict[str, dict[str, Any]] = {}
    for result in _organic_results(response):
        board = provider.parse_board_url(result.get("link"))
        if board is None:
            continue
        records_by_slug.setdefault(
            board.platform_company_slug,
            _board_record(
                provider=provider,
                discovery_query=discovery_query,
                board=board,
                result=result,
                collected_at=collected_at,
            ),
        )
    return list(records_by_slug.values())


def _discovery_error_record(
    *,
    discovery_query: AtsDiscoveryQuery,
    error: str,
    error_type: str | None = None,
    status_code: int | None = None,
    response_body: str | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "country_code": discovery_query.country_code,
        "country": discovery_query.country,
        "search_location_label": discovery_query.search_location_label,
        "query_location": discovery_query.query_location,
        "serper_location": discovery_query.serper_location,
        "discovery_query_type": discovery_query.discovery_query_type,
        "discovery_terms": list(discovery_query.discovery_terms),
        "search_page": discovery_query.page,
        "search_query": discovery_query.search_query,
        "request_params": dict(discovery_query.request_params),
        "error": error,
    }
    if error_type is not None:
        record["error_type"] = error_type
    if status_code is not None:
        record["status_code"] = status_code
    if response_body is not None:
        record["response_body"] = response_body[:2000]
    return record


def _http_error_response_body(exc: httpx.HTTPStatusError) -> str | None:
    try:
        return exc.response.text
    except Exception:  # noqa: BLE001 - best-effort debug detail only.
        return None


def discover_ats_boards(
    discovery_queries: Iterable[AtsDiscoveryQuery],
    *,
    provider: AtsDiscoveryProvider,
    client: DiscoverySearchClient,
    data_dir: Path = DEFAULT_DATA_DIR,
    clock: Callable[[], str] = utc_now_iso,
) -> AtsDiscoveryResult:
    queries = list(discovery_queries)
    started_at = clock()
    collection_date = started_at[:10]
    boards_by_slug: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []

    for discovery_query in queries:
        try:
            response = client.search(discovery_query)
            collected_at = clock()
            for record in extract_ats_board_records(
                provider=provider,
                discovery_query=discovery_query,
                response=response,
                collected_at=collected_at,
            ):
                boards_by_slug.setdefault(record["platform_company_slug"], record)

            api_error = response.get("error")
            if api_error:
                errors.append(
                    _discovery_error_record(
                        discovery_query=discovery_query,
                        error=str(api_error),
                    )
                )
        except httpx.HTTPStatusError as exc:
            errors.append(
                _discovery_error_record(
                    discovery_query=discovery_query,
                    error=str(exc),
                    error_type=exc.__class__.__name__,
                    status_code=exc.response.status_code,
                    response_body=_http_error_response_body(exc),
                )
            )
        except Exception as exc:  # noqa: BLE001 - discovery continues per query.
            errors.append(
                _discovery_error_record(
                    discovery_query=discovery_query,
                    error=str(exc),
                    error_type=exc.__class__.__name__,
                )
            )

    finished_at = clock()
    boards = sorted(
        boards_by_slug.values(),
        key=lambda item: str(item.get("platform_company_slug") or "").casefold(),
    )
    output_dir = ats_discovery_dir(
        collection_date,
        data_dir=data_dir,
        platform=provider.platform,
    )
    boards_path = output_dir / "boards.jsonl"
    write_jsonl(boards_path, boards)

    manifest_path = output_dir / "manifest.json"
    write_json(
        manifest_path,
        {
            "record_type": ATS_DISCOVERY_MANIFEST_RECORD_TYPE,
            "platform": provider.platform,
            "source": SourceName.SERPER_GOOGLE.value,
            "source_mode": SourceMode.ATS_BOARD_DISCOVERY_SEARCH.value,
            "started_at": started_at,
            "finished_at": finished_at,
            "countries": list(dict.fromkeys(query.country_code for query in queries)),
            "search_locations": list(
                dict.fromkeys(query.search_location_label for query in queries)
            ),
            "query_types": list(
                dict.fromkeys(query.discovery_query_type for query in queries)
            ),
            "pages": sorted(set(query.page for query in queries)),
            "results_per_query": sorted(
                set(int(query.request_params.get("num", 0)) for query in queries)
            ),
            "query_count": len(queries),
            "board_count": len(boards),
            "boards_file": boards_path.as_posix(),
            "errors": errors,
        },
    )

    return AtsDiscoveryResult(
        manifest_path=manifest_path,
        boards_path=boards_path,
        query_count=len(queries),
        boards=boards,
        errors=errors,
    )
