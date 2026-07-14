from __future__ import annotations

import time
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


ASHBY_PUBLIC_GRAPHQL_URL = (
    "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobBoardWithTeams"
)
ASHBY_JOB_POSTING_GRAPHQL_URL = (
    "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobPosting"
)
ASHBY_JOB_BOARD_OPERATION = "ApiJobBoardWithTeams"
ASHBY_JOB_POSTING_OPERATION = "ApiJobPosting"
ASHBY_JOB_BOARD_QUERY = """query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) {
  jobBoard: jobBoardWithTeams(organizationHostedJobsPageName: $organizationHostedJobsPageName) {
    teams {
      id
      name
      externalName
      parentTeamId
    }
    jobPostings {
      id
      title
      teamId
      locationId
      locationName
      workplaceType
      employmentType
      secondaryLocations {
        locationId
        locationName
      }
      compensationTierSummary
    }
  }
}"""
ASHBY_JOB_POSTING_QUERY = """query ApiJobPosting($organizationHostedJobsPageName: String!, $jobPostingId: String!) {
  jobPosting(organizationHostedJobsPageName: $organizationHostedJobsPageName, jobPostingId: $jobPostingId) {
    id
    title
    departmentName
    departmentExternalName
    locationName
    locationAddress
    workplaceType
    employmentType
    descriptionHtml
    isListed
    isConfidential
    teamNames
    secondaryLocationNames
    compensationTierSummary
    applicationDeadline
  }
}"""

RAW_ATS_RECORD_TYPE = "raw_ats_response"
ATS_COMPANY_BOARD_RECORD_TYPE = "ats_company_board"
ATS_DISCOVERY_MANIFEST_RECORD_TYPE = "ats_discovery_manifest"
ATS_COLLECTION_MANIFEST_RECORD_TYPE = "ats_collection_manifest"
ASHBY_DISCOVERY_SOURCE = "search_index"
ASHBY_ACCESS_TYPE = "public_job_board_endpoint"
ASHBY_STABILITY = "undocumented"
DEFAULT_ASHBY_DISCOVERY_RESULTS_PER_QUERY = 10
MAX_ASHBY_DISCOVERY_RESULTS_PER_QUERY = 10
DEFAULT_ASHBY_DISCOVERY_PAGES = 2
ASHBY_DISCOVERY_SIGNAL_TERMS = DEFAULT_ATS_DISCOVERY_SIGNAL_TERMS
AshbyDiscoveryDepth = AtsDiscoveryDepth
AshbyDiscoveryQuery = AtsDiscoveryQuery
AshbyDiscoveryResult = AtsDiscoveryResult


@dataclass(frozen=True)
class AshbyBoard:
    platform_company_slug: str
    board_url: str


@dataclass
class AshbyCollectionResult:
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
    def search(self, search_query: AshbyDiscoveryQuery) -> dict[str, Any]: ...


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def ashby_board_from_slug(platform_company_slug: str) -> AshbyBoard:
    slug = platform_company_slug.strip().strip("/")
    if not slug:
        raise ValueError("Ashby company slug is required.")
    return AshbyBoard(
        platform_company_slug=slug,
        board_url=f"https://jobs.ashbyhq.com/{quote(slug, safe='-_~.')}",
    )


def parse_ashby_board_url(value: object | None) -> AshbyBoard | None:
    raw_url = str(value or "").strip()
    if not raw_url:
        return None
    if raw_url.startswith("jobs.ashbyhq.com/"):
        raw_url = f"https://{raw_url}"

    parsed_url = urlparse(raw_url)
    if parsed_url.scheme not in {"http", "https"}:
        return None
    if parsed_url.netloc.casefold() != "jobs.ashbyhq.com":
        return None

    path_segments = [unquote(segment) for segment in parsed_url.path.split("/") if segment]
    if not path_segments:
        return None

    slug = path_segments[0].strip()
    if slug.casefold() in {"api", "_next", "assets", "favicon.ico"}:
        return None

    return ashby_board_from_slug(slug)


def normalize_ashby_board(value: str) -> AshbyBoard:
    parsed_board = parse_ashby_board_url(value)
    if parsed_board is not None:
        return parsed_board
    return ashby_board_from_slug(value)


ASHBY_DISCOVERY_PROVIDER = AtsDiscoveryProvider(
    platform=SourceName.ASHBY.value,
    site="jobs.ashbyhq.com",
    parse_board_url=parse_ashby_board_url,
)


def build_ashby_discovery_search_query(
    *,
    terms: Iterable[object | None] = (),
) -> str:
    return build_ats_discovery_search_query(
        provider=ASHBY_DISCOVERY_PROVIDER,
        terms=terms,
    )


def generate_ashby_discovery_queries(
    *,
    countries_config: CountriesConfig,
    country_codes: Iterable[str],
    limit: int | None = None,
    num: int = DEFAULT_ASHBY_DISCOVERY_RESULTS_PER_QUERY,
    pages: int = DEFAULT_ASHBY_DISCOVERY_PAGES,
    location_depth: LocationDepth = LocationDepth.CITIES,
    discovery_depth: AshbyDiscoveryDepth = AshbyDiscoveryDepth.EXHAUSTIVE,
    role_terms: Iterable[str] = (),
    signal_terms: Iterable[str] = ASHBY_DISCOVERY_SIGNAL_TERMS,
) -> list[AshbyDiscoveryQuery]:
    return generate_ats_discovery_queries(
        provider=ASHBY_DISCOVERY_PROVIDER,
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


def extract_ashby_board_records(
    *,
    discovery_query: AshbyDiscoveryQuery,
    response: dict[str, Any],
    collected_at: str,
) -> list[dict[str, Any]]:
    return extract_ats_board_records(
        provider=ASHBY_DISCOVERY_PROVIDER,
        discovery_query=discovery_query,
        response=response,
        collected_at=collected_at,
    )


def discover_ashby_boards(
    discovery_queries: Iterable[AshbyDiscoveryQuery],
    *,
    client: DiscoverySearchClient,
    data_dir: Path = DEFAULT_DATA_DIR,
    clock: Callable[[], str] = utc_now_iso,
) -> AshbyDiscoveryResult:
    return discover_ats_boards(
        discovery_queries,
        provider=ASHBY_DISCOVERY_PROVIDER,
        client=client,
        data_dir=data_dir,
        clock=clock,
    )


def build_job_board_request_body(platform_company_slug: str) -> dict[str, Any]:
    return {
        "operationName": ASHBY_JOB_BOARD_OPERATION,
        "variables": {
            "organizationHostedJobsPageName": platform_company_slug,
        },
        "query": ASHBY_JOB_BOARD_QUERY,
    }


def build_job_posting_request_body(
    *,
    platform_company_slug: str,
    job_posting_id: str,
) -> dict[str, Any]:
    return {
        "operationName": ASHBY_JOB_POSTING_OPERATION,
        "variables": {
            "organizationHostedJobsPageName": platform_company_slug,
            "jobPostingId": job_posting_id,
        },
        "query": ASHBY_JOB_POSTING_QUERY,
    }


class AshbyClient:
    def __init__(
        self,
        *,
        endpoint: str = ASHBY_PUBLIC_GRAPHQL_URL,
        timeout: float = 30.0,
        http_client: httpx.Client | None = None,
        request_delay_seconds: float = DEFAULT_REQUEST_DELAY_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.endpoint = endpoint
        self._client = http_client or httpx.Client(timeout=timeout)
        self._owns_client = http_client is None
        self._requester = ResilientHttpRequester(
            http_client=self._client,
            request_delay_seconds=request_delay_seconds,
            max_retries=max_retries,
            sleeper=sleeper,
        )

    def fetch_board(self, board_url_or_slug: str) -> dict[str, Any]:
        board = normalize_ashby_board(board_url_or_slug)
        response = self._requester.post(
            self.endpoint,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "ai-hiring-radar-ashby-prototype",
            },
            json=build_job_board_request_body(board.platform_company_slug),
        )
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Expected Ashby to return a JSON object.")
        return payload

    def fetch_job_detail(
        self,
        *,
        board_url_or_slug: str,
        job_posting_id: str,
    ) -> dict[str, Any]:
        board = normalize_ashby_board(board_url_or_slug)
        response = self._requester.post(
            ASHBY_JOB_POSTING_GRAPHQL_URL,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "ai-hiring-radar-ashby-prototype",
            },
            json=build_job_posting_request_body(
                platform_company_slug=board.platform_company_slug,
                job_posting_id=job_posting_id,
            ),
        )
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Expected Ashby job detail to return a JSON object.")
        return payload

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


def build_raw_ashby_response_record(
    *,
    board: AshbyBoard,
    response: dict[str, Any],
    collected_at: str,
    job_detail_responses: dict[str, Any] | None = None,
    job_detail_errors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "record_type": RAW_ATS_RECORD_TYPE,
        "platform": SourceName.ASHBY.value,
        "access_type": ASHBY_ACCESS_TYPE,
        "official_api": False,
        "stability": ASHBY_STABILITY,
        "source": SourceName.ASHBY.value,
        "source_mode": SourceMode.PUBLIC_JOB_BOARD_ENDPOINT.value,
        "platform_company_slug": board.platform_company_slug,
        "board_url": board.board_url,
        "endpoint": ASHBY_PUBLIC_GRAPHQL_URL,
        "operation_name": ASHBY_JOB_BOARD_OPERATION,
        "request_body": build_job_board_request_body(board.platform_company_slug),
        "job_detail_endpoint": ASHBY_JOB_POSTING_GRAPHQL_URL,
        "job_detail_operation_name": ASHBY_JOB_POSTING_OPERATION,
        "collected_at": collected_at,
        "title_prefilter": _ashby_title_prefilter_metadata(response),
        "response": response,
        "job_detail_responses": job_detail_responses or {},
        "job_detail_errors": job_detail_errors or [],
    }


def _has_job_board(response: dict[str, Any]) -> bool:
    data = response.get("data")
    return isinstance(data, dict) and isinstance(data.get("jobBoard"), dict)


def _job_posting_ids(response: dict[str, Any]) -> list[str]:
    job_postings = _job_postings(response)

    job_ids: list[str] = []
    for job in job_postings:
        job_id = str(job.get("id") or "").strip()
        if job_id:
            job_ids.append(job_id)
    return job_ids


def _job_postings(response: dict[str, Any]) -> list[dict[str, Any]]:
    data = response.get("data")
    if not isinstance(data, dict):
        return []
    job_board = data.get("jobBoard")
    if not isinstance(job_board, dict):
        return []
    job_postings = job_board.get("jobPostings")
    if not isinstance(job_postings, list):
        return []
    return [job for job in job_postings if isinstance(job, dict)]


def _ashby_title_prefilter_metadata(response: dict[str, Any]) -> dict[str, int | str]:
    job_postings = _job_postings(response)
    matched_count = sum(
        1 for job in job_postings if is_ai_role_title_candidate(job.get("title"))
    )
    return title_prefilter_metadata(
        listed_count=len(job_postings),
        matched_count=matched_count,
    )


def _is_ashby_detail_candidate_title(value: object | None) -> bool:
    return is_ai_role_title_candidate(value)


def _candidate_job_posting_ids(response: dict[str, Any]) -> list[str]:
    job_ids: list[str] = []
    for job in _job_postings(response):
        if not _is_ashby_detail_candidate_title(job.get("title")):
            continue
        job_id = str(job.get("id") or "").strip()
        if job_id:
            job_ids.append(job_id)
    return job_ids


def _collection_error_record(
    *,
    board: AshbyBoard,
    error: str,
    error_type: str | None = None,
    output_file: str | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "platform": SourceName.ASHBY.value,
        "platform_company_slug": board.platform_company_slug,
        "board_url": board.board_url,
        "error": error,
    }
    if error_type is not None:
        record["error_type"] = error_type
    if output_file is not None:
        record["output_file"] = output_file
    return record


def _job_detail_error_record(
    *,
    board: AshbyBoard,
    platform_job_id: str,
    error: str,
    error_type: str | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "platform": SourceName.ASHBY.value,
        "platform_company_slug": board.platform_company_slug,
        "board_url": board.board_url,
        "platform_job_id": platform_job_id,
        "error_scope": "job_detail",
        "error": error,
    }
    if error_type is not None:
        record["error_type"] = error_type
    return record


def collect_ashby_boards(
    board_urls_or_slugs: Iterable[str],
    *,
    client: AshbyClient,
    data_dir: Path = DEFAULT_DATA_DIR,
    clock: Callable[[], str] = utc_now_iso,
    collection_date: str | None = None,
    resume: bool = True,
) -> AshbyCollectionResult:
    boards_by_slug: dict[str, AshbyBoard] = {}
    for value in board_urls_or_slugs:
        board = normalize_ashby_board(value)
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
            platform=SourceName.ASHBY.value,
        )
        if resume and is_valid_raw_ats_resume_file(
            resume_path,
            platform=SourceName.ASHBY.value,
            platform_company_slug=board.platform_company_slug,
        ):
            output_file = resume_path.as_posix()
            result_files.append(output_file)
            resumed_files.append(output_file)
            continue

        try:
            response = client.fetch_board(board.board_url)
            job_detail_responses: dict[str, Any] = {}
            job_detail_errors: list[dict[str, Any]] = []
            for platform_job_id in _candidate_job_posting_ids(response):
                try:
                    job_detail_responses[platform_job_id] = client.fetch_job_detail(
                        board_url_or_slug=board.board_url,
                        job_posting_id=platform_job_id,
                    )
                except Exception as exc:  # noqa: BLE001 - keep collecting other jobs.
                    error_record = _job_detail_error_record(
                        board=board,
                        platform_job_id=platform_job_id,
                        error=str(exc),
                        error_type=exc.__class__.__name__,
                    )
                    job_detail_errors.append(error_record)
                    errors.append(error_record)

            raw_record = build_raw_ashby_response_record(
                board=board,
                response=response,
                collected_at=clock(),
                job_detail_responses=job_detail_responses,
                job_detail_errors=job_detail_errors,
            )
            path = write_raw_ats_response(
                raw_record,
                platform_company_slug=board.platform_company_slug,
                collection_date=effective_collection_date,
                data_dir=data_dir,
                platform=SourceName.ASHBY.value,
            )
            output_file = path.as_posix()
            result_files.append(output_file)
            written_files.append(output_file)

            if not _has_job_board(response):
                errors.append(
                    _collection_error_record(
                        board=board,
                        error="Ashby response did not contain data.jobBoard.",
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
        platform=SourceName.ASHBY.value,
    ) / "manifest.json"
    write_json(
        manifest_path,
        {
            "record_type": ATS_COLLECTION_MANIFEST_RECORD_TYPE,
            "platform": SourceName.ASHBY.value,
            "source": SourceName.ASHBY.value,
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

    return AshbyCollectionResult(
        manifest_path=manifest_path,
        board_count=len(boards),
        result_files=result_files,
        written_files=written_files,
        resumed_files=resumed_files,
        errors=errors,
    )
