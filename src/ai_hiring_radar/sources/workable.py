from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote, unquote, urlparse

import httpx

from ai_hiring_radar.classify import (
    is_ai_role_title_candidate,
    title_prefilter_metadata,
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


WORKABLE_PUBLIC_BASE_URL = "https://apply.workable.com"
RAW_ATS_RECORD_TYPE = "raw_ats_response"
ATS_COLLECTION_MANIFEST_RECORD_TYPE = "ats_collection_manifest"
WORKABLE_ACCESS_TYPE = "public_job_board_endpoint"
WORKABLE_STABILITY = "public_hosted_careers_app_endpoint"
DEFAULT_WORKABLE_DISCOVERY_RESULTS_PER_QUERY = DEFAULT_ATS_DISCOVERY_RESULTS_PER_QUERY
MAX_WORKABLE_DISCOVERY_RESULTS_PER_QUERY = MAX_ATS_DISCOVERY_RESULTS_PER_QUERY
DEFAULT_WORKABLE_DISCOVERY_PAGES = DEFAULT_ATS_DISCOVERY_PAGES
WORKABLE_DISCOVERY_SIGNAL_TERMS = DEFAULT_ATS_DISCOVERY_SIGNAL_TERMS
WorkableDiscoveryDepth = AtsDiscoveryDepth
WorkableDiscoveryQuery = AtsDiscoveryQuery
WorkableDiscoveryResult = AtsDiscoveryResult


@dataclass(frozen=True)
class WorkableBoard:
    platform_company_slug: str
    board_url: str


@dataclass(frozen=True)
class WorkableFetchResult:
    response: dict[str, Any]
    endpoint: str
    request_body: dict[str, Any]
    account_response: dict[str, Any]
    account_endpoint: str
    job_detail_responses: dict[str, dict[str, Any]]
    job_detail_endpoints: list[str]
    job_detail_errors: list[dict[str, Any]]


@dataclass
class WorkableCollectionResult:
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
    def search(self, search_query: WorkableDiscoveryQuery) -> dict[str, Any]: ...


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def workable_board_from_slug(platform_company_slug: str) -> WorkableBoard:
    slug = platform_company_slug.strip().strip("/").casefold()
    if not slug:
        raise ValueError("Workable account slug is required.")
    return WorkableBoard(
        platform_company_slug=slug,
        board_url=f"{WORKABLE_PUBLIC_BASE_URL}/{quote(slug, safe='-_~.')}",
    )


def parse_workable_board_url(value: object | None) -> WorkableBoard | None:
    raw_url = str(value or "").strip()
    if not raw_url:
        return None
    if raw_url.startswith(("apply.workable.com/", "www.workable.com/")):
        raw_url = f"https://{raw_url}"
    if "://" not in raw_url and raw_url.split("/", 1)[0].casefold().endswith(
        ".workable.com"
    ):
        raw_url = f"https://{raw_url}"

    parsed_url = urlparse(raw_url)
    if parsed_url.scheme not in {"http", "https"}:
        return None

    host = parsed_url.netloc.casefold()
    path_segments = [unquote(segment) for segment in parsed_url.path.split("/") if segment]
    if host == "apply.workable.com":
        if not path_segments:
            return None
        slug = path_segments[0].strip()
        if slug.casefold() in {"api", "assets", "cdn-cgi", "favicon.ico"}:
            return None
        return workable_board_from_slug(slug)

    suffix = ".workable.com"
    if not host.endswith(suffix):
        return None
    slug = unquote(host[: -len(suffix)]).strip()
    if not slug or "." in slug or slug.casefold() in {"api", "apply", "www"}:
        return None
    return workable_board_from_slug(slug)


def normalize_workable_board(value: str) -> WorkableBoard:
    parsed_board = parse_workable_board_url(value)
    if parsed_board is not None:
        return parsed_board
    return workable_board_from_slug(value)


WORKABLE_DISCOVERY_PROVIDER = AtsDiscoveryProvider(
    platform=SourceName.WORKABLE.value,
    site="apply.workable.com",
    parse_board_url=parse_workable_board_url,
)


def build_workable_discovery_search_query(
    *,
    terms: Iterable[object | None] = (),
) -> str:
    return build_ats_discovery_search_query(
        provider=WORKABLE_DISCOVERY_PROVIDER,
        terms=terms,
    )


def generate_workable_discovery_queries(
    *,
    countries_config: CountriesConfig,
    country_codes: Iterable[str],
    limit: int | None = None,
    num: int = DEFAULT_WORKABLE_DISCOVERY_RESULTS_PER_QUERY,
    pages: int = DEFAULT_WORKABLE_DISCOVERY_PAGES,
    location_depth: LocationDepth = LocationDepth.CITIES,
    discovery_depth: WorkableDiscoveryDepth = WorkableDiscoveryDepth.EXHAUSTIVE,
    role_terms: Iterable[str] = (),
    signal_terms: Iterable[str] = WORKABLE_DISCOVERY_SIGNAL_TERMS,
) -> list[WorkableDiscoveryQuery]:
    return generate_ats_discovery_queries(
        provider=WORKABLE_DISCOVERY_PROVIDER,
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


def extract_workable_board_records(
    *,
    discovery_query: WorkableDiscoveryQuery,
    response: dict[str, Any],
    collected_at: str,
) -> list[dict[str, Any]]:
    return extract_ats_board_records(
        provider=WORKABLE_DISCOVERY_PROVIDER,
        discovery_query=discovery_query,
        response=response,
        collected_at=collected_at,
    )


def discover_workable_boards(
    discovery_queries: Iterable[WorkableDiscoveryQuery],
    *,
    client: DiscoverySearchClient,
    data_dir: Path = DEFAULT_DATA_DIR,
    clock: Callable[[], str] = utc_now_iso,
) -> WorkableDiscoveryResult:
    return discover_ats_boards(
        discovery_queries,
        provider=WORKABLE_DISCOVERY_PROVIDER,
        client=client,
        data_dir=data_dir,
        clock=clock,
    )


def build_workable_account_endpoint(
    platform_company_slug: str,
    *,
    base_url: str = WORKABLE_PUBLIC_BASE_URL,
) -> str:
    slug = quote(platform_company_slug.strip().strip("/").casefold(), safe="-_~.")
    if not slug:
        raise ValueError("Workable account slug is required.")
    return f"{base_url.rstrip('/')}/api/v1/accounts/{slug}?full=true"


def build_workable_jobs_endpoint(
    platform_company_slug: str,
    *,
    base_url: str = WORKABLE_PUBLIC_BASE_URL,
) -> str:
    slug = quote(platform_company_slug.strip().strip("/").casefold(), safe="-_~.")
    if not slug:
        raise ValueError("Workable account slug is required.")
    return f"{base_url.rstrip('/')}/api/v3/accounts/{slug}/jobs"


def build_workable_job_detail_endpoint(
    platform_company_slug: str,
    shortcode: str,
    *,
    base_url: str = WORKABLE_PUBLIC_BASE_URL,
) -> str:
    slug = quote(platform_company_slug.strip().strip("/").casefold(), safe="-_~.")
    normalized_shortcode = quote(shortcode.strip(), safe="-_~.")
    if not slug:
        raise ValueError("Workable account slug is required.")
    if not normalized_shortcode:
        raise ValueError("Workable job shortcode is required.")
    return f"{base_url.rstrip('/')}/api/v2/accounts/{slug}/jobs/{normalized_shortcode}"


def build_workable_public_job_url(platform_company_slug: str, shortcode: str) -> str:
    slug = quote(platform_company_slug.strip().strip("/").casefold(), safe="-_~.")
    normalized_shortcode = quote(shortcode.strip(), safe="-_~.")
    return f"{WORKABLE_PUBLIC_BASE_URL}/{slug}/j/{normalized_shortcode}"


def _workable_jobs(response: dict[str, Any]) -> list[dict[str, Any]]:
    results = response.get("results")
    if not isinstance(results, list):
        return []
    return [item for item in results if isinstance(item, dict)]


def _job_shortcode(job: dict[str, Any]) -> str | None:
    shortcode = " ".join(str(job.get("shortcode") or "").split()).strip()
    return shortcode or None


def _is_workable_public_job(job: dict[str, Any]) -> bool:
    state = str(job.get("state") or "").strip().casefold()
    if state and state != "published":
        return False
    if job.get("isInternal") is True:
        return False
    if job.get("hidden") is True:
        return False
    return True


def _is_workable_detail_candidate_title(value: object | None) -> bool:
    return is_ai_role_title_candidate(value)


def _is_workable_detail_candidate_job(job: dict[str, Any]) -> bool:
    if not _is_workable_public_job(job):
        return False
    return _is_workable_detail_candidate_title(job.get("title") or job.get("name"))


def _workable_title_prefilter_metadata(response: dict[str, Any]) -> dict[str, int | str]:
    jobs = _workable_jobs(response)
    public_jobs = [job for job in jobs if _is_workable_public_job(job)]
    matched_count = sum(
        1
        for job in public_jobs
        if _is_workable_detail_candidate_title(job.get("title") or job.get("name"))
    )
    metadata = title_prefilter_metadata(
        listed_count=len(jobs),
        matched_count=matched_count,
        source_field="title/name",
    )
    metadata["eligible_count"] = len(public_jobs)
    return metadata


def _error_record(
    *,
    error: str,
    error_type: str | None = None,
    endpoint: str | None = None,
    shortcode: str | None = None,
    error_scope: str | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {"error": error}
    if error_type is not None:
        record["error_type"] = error_type
    if endpoint is not None:
        record["endpoint"] = endpoint
    if shortcode is not None:
        record["shortcode"] = shortcode
    if error_scope is not None:
        record["error_scope"] = error_scope
    return record


class WorkableClient:
    def __init__(
        self,
        *,
        timeout: float = 30.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._client = http_client or httpx.Client(timeout=timeout)
        self._owns_client = http_client is None

    def fetch_board(self, board_url_or_slug: str) -> WorkableFetchResult:
        board = normalize_workable_board(board_url_or_slug)
        headers = {
            "Accept": "application/json",
            "User-Agent": "ai-hiring-radar-workable-prototype",
        }
        account_endpoint = build_workable_account_endpoint(board.platform_company_slug)
        account_response = self._client.get(account_endpoint, headers=headers)
        account_response.raise_for_status()
        account_payload = account_response.json()
        if not isinstance(account_payload, dict):
            raise ValueError("Expected Workable account endpoint to return a JSON object.")

        endpoint = build_workable_jobs_endpoint(board.platform_company_slug)
        request_body: dict[str, Any] = {}
        jobs_response = self._client.post(
            endpoint,
            headers={**headers, "Content-Type": "application/json"},
            json=request_body,
        )
        jobs_response.raise_for_status()
        jobs_payload = jobs_response.json()
        if not isinstance(jobs_payload, dict):
            raise ValueError("Expected Workable jobs endpoint to return a JSON object.")

        job_detail_responses: dict[str, dict[str, Any]] = {}
        job_detail_endpoints: list[str] = []
        job_detail_errors: list[dict[str, Any]] = []
        for job in _workable_jobs(jobs_payload):
            if not _is_workable_detail_candidate_job(job):
                continue
            shortcode = _job_shortcode(job)
            if shortcode is None:
                continue
            detail_endpoint = build_workable_job_detail_endpoint(
                board.platform_company_slug,
                shortcode,
            )
            job_detail_endpoints.append(detail_endpoint)
            try:
                detail_response = self._client.get(detail_endpoint, headers=headers)
                detail_response.raise_for_status()
                detail_payload = detail_response.json()
                if not isinstance(detail_payload, dict):
                    raise ValueError(
                        "Expected Workable job detail endpoint to return a JSON object."
                    )
                job_detail_responses[shortcode] = detail_payload
            except Exception as exc:  # noqa: BLE001 - continue per job detail.
                job_detail_errors.append(
                    _error_record(
                        shortcode=shortcode,
                        endpoint=detail_endpoint,
                        error=str(exc),
                        error_type=exc.__class__.__name__,
                        error_scope="job_detail",
                    )
                )

        return WorkableFetchResult(
            response=jobs_payload,
            endpoint=endpoint,
            request_body=request_body,
            account_response=account_payload,
            account_endpoint=account_endpoint,
            job_detail_responses=job_detail_responses,
            job_detail_endpoints=job_detail_endpoints,
            job_detail_errors=job_detail_errors,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


def build_raw_workable_response_record(
    *,
    board: WorkableBoard,
    response: dict[str, Any],
    collected_at: str,
    endpoint: str | None = None,
    request_body: dict[str, Any] | None = None,
    account_response: dict[str, Any] | None = None,
    account_endpoint: str | None = None,
    job_detail_responses: dict[str, dict[str, Any]] | None = None,
    job_detail_endpoints: list[str] | None = None,
    job_detail_errors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "record_type": RAW_ATS_RECORD_TYPE,
        "platform": SourceName.WORKABLE.value,
        "access_type": WORKABLE_ACCESS_TYPE,
        "official_api": False,
        "stability": WORKABLE_STABILITY,
        "source": SourceName.WORKABLE.value,
        "source_mode": SourceMode.PUBLIC_JOB_BOARD_ENDPOINT.value,
        "platform_company_slug": board.platform_company_slug,
        "board_url": board.board_url,
        "account_endpoint": account_endpoint
        or build_workable_account_endpoint(board.platform_company_slug),
        "account_response": account_response or {},
        "endpoint": endpoint or build_workable_jobs_endpoint(board.platform_company_slug),
        "request_method": "POST",
        "request_body": request_body or {},
        "job_detail_endpoints": job_detail_endpoints or [],
        "job_detail_responses": job_detail_responses or {},
        "job_detail_errors": job_detail_errors or [],
        "title_prefilter": _workable_title_prefilter_metadata(response),
        "response_format": "json",
        "collected_at": collected_at,
        "response": response,
    }


def _has_jobs_response(response: dict[str, Any]) -> bool:
    return isinstance(response.get("results"), list)


def _collection_error_record(
    *,
    board: WorkableBoard,
    error: str,
    error_type: str | None = None,
    output_file: str | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "platform": SourceName.WORKABLE.value,
        "platform_company_slug": board.platform_company_slug,
        "board_url": board.board_url,
        "error": error,
    }
    if error_type is not None:
        record["error_type"] = error_type
    if output_file is not None:
        record["output_file"] = output_file
    return record


def collect_workable_boards(
    board_urls_or_slugs: Iterable[str],
    *,
    client: WorkableClient,
    data_dir: Path = DEFAULT_DATA_DIR,
    clock: Callable[[], str] = utc_now_iso,
) -> WorkableCollectionResult:
    boards_by_slug: dict[str, WorkableBoard] = {}
    for value in board_urls_or_slugs:
        board = normalize_workable_board(value)
        boards_by_slug.setdefault(board.platform_company_slug, board)

    boards = list(boards_by_slug.values())
    started_at = clock()
    collection_date = started_at[:10]
    result_files: list[str] = []
    errors: list[dict[str, Any]] = []

    for board in boards:
        try:
            fetch_result = client.fetch_board(board.board_url)
            raw_record = build_raw_workable_response_record(
                board=board,
                response=fetch_result.response,
                endpoint=fetch_result.endpoint,
                request_body=fetch_result.request_body,
                account_response=fetch_result.account_response,
                account_endpoint=fetch_result.account_endpoint,
                job_detail_responses=fetch_result.job_detail_responses,
                job_detail_endpoints=fetch_result.job_detail_endpoints,
                job_detail_errors=fetch_result.job_detail_errors,
                collected_at=clock(),
            )
            path = write_raw_ats_response(
                raw_record,
                platform_company_slug=board.platform_company_slug,
                collection_date=collection_date,
                data_dir=data_dir,
                platform=SourceName.WORKABLE.value,
            )
            output_file = path.as_posix()
            result_files.append(output_file)

            if not _has_jobs_response(fetch_result.response):
                errors.append(
                    _collection_error_record(
                        board=board,
                        error="Workable response did not contain a results list.",
                        output_file=output_file,
                    )
                )
            for detail_error in fetch_result.job_detail_errors:
                error_record = _collection_error_record(
                    board=board,
                    error=str(detail_error.get("error") or "Workable detail failed."),
                    error_type=str(detail_error.get("error_type") or ""),
                    output_file=output_file,
                )
                for field in ("shortcode", "endpoint", "error_scope"):
                    value = detail_error.get(field)
                    if value is not None:
                        error_record[field] = value
                errors.append(error_record)
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
        platform=SourceName.WORKABLE.value,
    ) / "manifest.json"
    write_json(
        manifest_path,
        {
            "record_type": ATS_COLLECTION_MANIFEST_RECORD_TYPE,
            "platform": SourceName.WORKABLE.value,
            "source": SourceName.WORKABLE.value,
            "source_mode": SourceMode.PUBLIC_JOB_BOARD_ENDPOINT.value,
            "started_at": started_at,
            "finished_at": finished_at,
            "board_count": len(boards),
            "result_files": result_files,
            "errors": errors,
        },
    )

    return WorkableCollectionResult(
        manifest_path=manifest_path,
        board_count=len(boards),
        result_files=result_files,
        errors=errors,
    )
