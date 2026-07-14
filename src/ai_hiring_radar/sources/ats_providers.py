from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    class StrEnum(str, Enum):
        pass
else:
    from enum import StrEnum

from ai_hiring_radar.sources import (
    ashby,
    greenhouse,
    lever,
    personio,
    recruitee,
    smartrecruiters,
    teamtailor,
    workable,
)
from ai_hiring_radar.sources.ats_discovery import (
    AtsDiscoveryQuery,
    AtsDiscoveryResult,
)


class AtsProvider(StrEnum):
    ASHBY = "ashby"
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    PERSONIO = "personio"
    RECRUITEE = "recruitee"
    TEAMTAILOR = "teamtailor"
    SMARTRECRUITERS = "smartrecruiters"
    WORKABLE = "workable"


class NormalizedAtsBoard(Protocol):
    @property
    def platform_company_slug(self) -> str: ...

    @property
    def board_url(self) -> str: ...


class CloseableAtsClient(Protocol):
    def close(self) -> None: ...


class AtsCollectionResult(Protocol):
    @property
    def manifest_path(self) -> Path: ...

    @property
    def board_count(self) -> int: ...

    @property
    def result_files(self) -> list[str]: ...

    @property
    def written_files(self) -> list[str]: ...

    @property
    def resumed_files(self) -> list[str]: ...

    @property
    def errors(self) -> list[dict[str, Any]]: ...

    @property
    def successful_count(self) -> int: ...

    @property
    def written_count(self) -> int: ...

    @property
    def resumed_count(self) -> int: ...

    @property
    def error_count(self) -> int: ...


@dataclass(frozen=True)
class AtsClientOptions:
    request_delay_seconds: float
    max_retries: int
    language: str | None = None


NormalizeBoard = Callable[[str], NormalizedAtsBoard]
GenerateDiscoveryQueries = Callable[..., list[AtsDiscoveryQuery]]
DiscoverBoards = Callable[..., AtsDiscoveryResult]
MakeClient = Callable[[AtsClientOptions], CloseableAtsClient]
CollectBoards = Callable[..., AtsCollectionResult]


@dataclass(frozen=True)
class AtsProviderSpec:
    provider: AtsProvider
    display_name: str
    normalize_board: NormalizeBoard
    generate_discovery_queries: GenerateDiscoveryQueries
    discover_boards: DiscoverBoards
    make_client: MakeClient
    collect_boards: CollectBoards
    default_results_per_query: int
    max_results_per_query: int
    default_pages: int


def _standard_client_factory(
    client_type: Callable[..., CloseableAtsClient],
) -> MakeClient:
    def make_client(options: AtsClientOptions) -> CloseableAtsClient:
        return client_type(
            request_delay_seconds=options.request_delay_seconds,
            max_retries=options.max_retries,
        )

    return make_client


def _make_personio_client(options: AtsClientOptions) -> CloseableAtsClient:
    return personio.PersonioClient(
        request_delay_seconds=options.request_delay_seconds,
        max_retries=options.max_retries,
        language=options.language or personio.DEFAULT_PERSONIO_LANGUAGE,
    )


ATS_PROVIDER_SPECS: dict[AtsProvider, AtsProviderSpec] = {
    AtsProvider.ASHBY: AtsProviderSpec(
        provider=AtsProvider.ASHBY,
        display_name="Ashby",
        normalize_board=ashby.normalize_ashby_board,
        generate_discovery_queries=ashby.generate_ashby_discovery_queries,
        discover_boards=ashby.discover_ashby_boards,
        make_client=_standard_client_factory(ashby.AshbyClient),
        collect_boards=ashby.collect_ashby_boards,
        default_results_per_query=ashby.DEFAULT_ASHBY_DISCOVERY_RESULTS_PER_QUERY,
        max_results_per_query=ashby.MAX_ASHBY_DISCOVERY_RESULTS_PER_QUERY,
        default_pages=ashby.DEFAULT_ASHBY_DISCOVERY_PAGES,
    ),
    AtsProvider.GREENHOUSE: AtsProviderSpec(
        provider=AtsProvider.GREENHOUSE,
        display_name="Greenhouse",
        normalize_board=greenhouse.normalize_greenhouse_board,
        generate_discovery_queries=greenhouse.generate_greenhouse_discovery_queries,
        discover_boards=greenhouse.discover_greenhouse_boards,
        make_client=_standard_client_factory(greenhouse.GreenhouseClient),
        collect_boards=greenhouse.collect_greenhouse_boards,
        default_results_per_query=(
            greenhouse.DEFAULT_GREENHOUSE_DISCOVERY_RESULTS_PER_QUERY
        ),
        max_results_per_query=greenhouse.MAX_GREENHOUSE_DISCOVERY_RESULTS_PER_QUERY,
        default_pages=greenhouse.DEFAULT_GREENHOUSE_DISCOVERY_PAGES,
    ),
    AtsProvider.LEVER: AtsProviderSpec(
        provider=AtsProvider.LEVER,
        display_name="Lever",
        normalize_board=lever.normalize_lever_board,
        generate_discovery_queries=lever.generate_lever_discovery_queries,
        discover_boards=lever.discover_lever_boards,
        make_client=_standard_client_factory(lever.LeverClient),
        collect_boards=lever.collect_lever_boards,
        default_results_per_query=lever.DEFAULT_LEVER_DISCOVERY_RESULTS_PER_QUERY,
        max_results_per_query=lever.MAX_LEVER_DISCOVERY_RESULTS_PER_QUERY,
        default_pages=lever.DEFAULT_LEVER_DISCOVERY_PAGES,
    ),
    AtsProvider.PERSONIO: AtsProviderSpec(
        provider=AtsProvider.PERSONIO,
        display_name="Personio",
        normalize_board=personio.normalize_personio_board,
        generate_discovery_queries=personio.generate_personio_discovery_queries,
        discover_boards=personio.discover_personio_boards,
        make_client=_make_personio_client,
        collect_boards=personio.collect_personio_boards,
        default_results_per_query=personio.DEFAULT_PERSONIO_DISCOVERY_RESULTS_PER_QUERY,
        max_results_per_query=personio.MAX_PERSONIO_DISCOVERY_RESULTS_PER_QUERY,
        default_pages=personio.DEFAULT_PERSONIO_DISCOVERY_PAGES,
    ),
    AtsProvider.RECRUITEE: AtsProviderSpec(
        provider=AtsProvider.RECRUITEE,
        display_name="Recruitee",
        normalize_board=recruitee.normalize_recruitee_board,
        generate_discovery_queries=recruitee.generate_recruitee_discovery_queries,
        discover_boards=recruitee.discover_recruitee_boards,
        make_client=_standard_client_factory(recruitee.RecruiteeClient),
        collect_boards=recruitee.collect_recruitee_boards,
        default_results_per_query=(
            recruitee.DEFAULT_RECRUITEE_DISCOVERY_RESULTS_PER_QUERY
        ),
        max_results_per_query=recruitee.MAX_RECRUITEE_DISCOVERY_RESULTS_PER_QUERY,
        default_pages=recruitee.DEFAULT_RECRUITEE_DISCOVERY_PAGES,
    ),
    AtsProvider.TEAMTAILOR: AtsProviderSpec(
        provider=AtsProvider.TEAMTAILOR,
        display_name="Teamtailor",
        normalize_board=teamtailor.normalize_teamtailor_board,
        generate_discovery_queries=teamtailor.generate_teamtailor_discovery_queries,
        discover_boards=teamtailor.discover_teamtailor_boards,
        make_client=_standard_client_factory(teamtailor.TeamtailorClient),
        collect_boards=teamtailor.collect_teamtailor_boards,
        default_results_per_query=(
            teamtailor.DEFAULT_TEAMTAILOR_DISCOVERY_RESULTS_PER_QUERY
        ),
        max_results_per_query=teamtailor.MAX_TEAMTAILOR_DISCOVERY_RESULTS_PER_QUERY,
        default_pages=teamtailor.DEFAULT_TEAMTAILOR_DISCOVERY_PAGES,
    ),
    AtsProvider.SMARTRECRUITERS: AtsProviderSpec(
        provider=AtsProvider.SMARTRECRUITERS,
        display_name="SmartRecruiters",
        normalize_board=smartrecruiters.normalize_smartrecruiters_board,
        generate_discovery_queries=(
            smartrecruiters.generate_smartrecruiters_discovery_queries
        ),
        discover_boards=smartrecruiters.discover_smartrecruiters_boards,
        make_client=_standard_client_factory(smartrecruiters.SmartRecruitersClient),
        collect_boards=smartrecruiters.collect_smartrecruiters_boards,
        default_results_per_query=(
            smartrecruiters.DEFAULT_SMARTRECRUITERS_DISCOVERY_RESULTS_PER_QUERY
        ),
        max_results_per_query=(
            smartrecruiters.MAX_SMARTRECRUITERS_DISCOVERY_RESULTS_PER_QUERY
        ),
        default_pages=smartrecruiters.DEFAULT_SMARTRECRUITERS_DISCOVERY_PAGES,
    ),
    AtsProvider.WORKABLE: AtsProviderSpec(
        provider=AtsProvider.WORKABLE,
        display_name="Workable",
        normalize_board=workable.normalize_workable_board,
        generate_discovery_queries=workable.generate_workable_discovery_queries,
        discover_boards=workable.discover_workable_boards,
        make_client=_standard_client_factory(workable.WorkableClient),
        collect_boards=workable.collect_workable_boards,
        default_results_per_query=workable.DEFAULT_WORKABLE_DISCOVERY_RESULTS_PER_QUERY,
        max_results_per_query=workable.MAX_WORKABLE_DISCOVERY_RESULTS_PER_QUERY,
        default_pages=workable.DEFAULT_WORKABLE_DISCOVERY_PAGES,
    ),
}


def get_ats_provider_spec(provider: AtsProvider) -> AtsProviderSpec:
    return ATS_PROVIDER_SPECS[provider]
