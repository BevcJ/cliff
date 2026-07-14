from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

import pytest

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
from ai_hiring_radar.sources.ats_providers import (
    ATS_PROVIDER_SPECS,
    AtsClientOptions,
    AtsProvider,
    get_ats_provider_spec,
)


PROVIDER_MODULES = {
    AtsProvider.ASHBY: ashby,
    AtsProvider.GREENHOUSE: greenhouse,
    AtsProvider.LEVER: lever,
    AtsProvider.PERSONIO: personio,
    AtsProvider.RECRUITEE: recruitee,
    AtsProvider.TEAMTAILOR: teamtailor,
    AtsProvider.SMARTRECRUITERS: smartrecruiters,
    AtsProvider.WORKABLE: workable,
}

CLIENT_TYPES = {
    AtsProvider.ASHBY: ashby.AshbyClient,
    AtsProvider.GREENHOUSE: greenhouse.GreenhouseClient,
    AtsProvider.LEVER: lever.LeverClient,
    AtsProvider.PERSONIO: personio.PersonioClient,
    AtsProvider.RECRUITEE: recruitee.RecruiteeClient,
    AtsProvider.TEAMTAILOR: teamtailor.TeamtailorClient,
    AtsProvider.SMARTRECRUITERS: smartrecruiters.SmartRecruitersClient,
    AtsProvider.WORKABLE: workable.WorkableClient,
}

DISCOVERY_METADATA = {
    AtsProvider.ASHBY: (
        ashby.DEFAULT_ASHBY_DISCOVERY_RESULTS_PER_QUERY,
        ashby.MAX_ASHBY_DISCOVERY_RESULTS_PER_QUERY,
        ashby.DEFAULT_ASHBY_DISCOVERY_PAGES,
    ),
    AtsProvider.GREENHOUSE: (
        greenhouse.DEFAULT_GREENHOUSE_DISCOVERY_RESULTS_PER_QUERY,
        greenhouse.MAX_GREENHOUSE_DISCOVERY_RESULTS_PER_QUERY,
        greenhouse.DEFAULT_GREENHOUSE_DISCOVERY_PAGES,
    ),
    AtsProvider.LEVER: (
        lever.DEFAULT_LEVER_DISCOVERY_RESULTS_PER_QUERY,
        lever.MAX_LEVER_DISCOVERY_RESULTS_PER_QUERY,
        lever.DEFAULT_LEVER_DISCOVERY_PAGES,
    ),
    AtsProvider.PERSONIO: (
        personio.DEFAULT_PERSONIO_DISCOVERY_RESULTS_PER_QUERY,
        personio.MAX_PERSONIO_DISCOVERY_RESULTS_PER_QUERY,
        personio.DEFAULT_PERSONIO_DISCOVERY_PAGES,
    ),
    AtsProvider.RECRUITEE: (
        recruitee.DEFAULT_RECRUITEE_DISCOVERY_RESULTS_PER_QUERY,
        recruitee.MAX_RECRUITEE_DISCOVERY_RESULTS_PER_QUERY,
        recruitee.DEFAULT_RECRUITEE_DISCOVERY_PAGES,
    ),
    AtsProvider.TEAMTAILOR: (
        teamtailor.DEFAULT_TEAMTAILOR_DISCOVERY_RESULTS_PER_QUERY,
        teamtailor.MAX_TEAMTAILOR_DISCOVERY_RESULTS_PER_QUERY,
        teamtailor.DEFAULT_TEAMTAILOR_DISCOVERY_PAGES,
    ),
    AtsProvider.SMARTRECRUITERS: (
        smartrecruiters.DEFAULT_SMARTRECRUITERS_DISCOVERY_RESULTS_PER_QUERY,
        smartrecruiters.MAX_SMARTRECRUITERS_DISCOVERY_RESULTS_PER_QUERY,
        smartrecruiters.DEFAULT_SMARTRECRUITERS_DISCOVERY_PAGES,
    ),
    AtsProvider.WORKABLE: (
        workable.DEFAULT_WORKABLE_DISCOVERY_RESULTS_PER_QUERY,
        workable.MAX_WORKABLE_DISCOVERY_RESULTS_PER_QUERY,
        workable.DEFAULT_WORKABLE_DISCOVERY_PAGES,
    ),
}


def test_registry_has_exactly_the_eight_ats_providers() -> None:
    assert [provider.value for provider in AtsProvider] == [
        "ashby",
        "greenhouse",
        "lever",
        "personio",
        "recruitee",
        "teamtailor",
        "smartrecruiters",
        "workable",
    ]
    assert set(ATS_PROVIDER_SPECS) == set(AtsProvider)
    assert all(
        get_ats_provider_spec(provider).provider is provider for provider in AtsProvider
    )


@pytest.mark.parametrize("provider", AtsProvider)
def test_registry_has_valid_provider_discovery_metadata(provider: AtsProvider) -> None:
    spec = get_ats_provider_spec(provider)
    expected_default, expected_max, expected_pages = DISCOVERY_METADATA[provider]

    assert (
        spec.default_results_per_query,
        spec.max_results_per_query,
        spec.default_pages,
    ) == (expected_default, expected_max, expected_pages)
    assert 1 <= spec.default_results_per_query <= spec.max_results_per_query
    assert spec.default_pages >= 1


@pytest.mark.parametrize("provider", AtsProvider)
def test_every_provider_spec_normalizes_boards(provider: AtsProvider) -> None:
    board = get_ats_provider_spec(provider).normalize_board("acme-ai")

    assert board.platform_company_slug == "acme-ai"
    assert board.board_url.startswith("https://")


@pytest.mark.parametrize("provider", AtsProvider)
def test_every_factory_builds_the_right_resilient_client(provider: AtsProvider) -> None:
    options = AtsClientOptions(
        request_delay_seconds=1.25,
        max_retries=7,
        language="de",
    )
    client = cast(Any, get_ats_provider_spec(provider).make_client(options))

    try:
        assert isinstance(client, CLIENT_TYPES[provider])
        assert client._requester._request_delay_seconds == 1.25
        assert client._requester._max_retries == 7
        if provider is not AtsProvider.PERSONIO:
            assert not hasattr(client, "language")
    finally:
        client.close()

    assert client._client.is_closed


def test_factories_preserve_provider_specific_client_defaults() -> None:
    options = AtsClientOptions(request_delay_seconds=0, max_retries=0)
    ashby_client = cast(
        Any,
        ATS_PROVIDER_SPECS[AtsProvider.ASHBY].make_client(options),
    )
    smartrecruiters_client = cast(
        Any,
        ATS_PROVIDER_SPECS[AtsProvider.SMARTRECRUITERS].make_client(options),
    )

    try:
        assert ashby_client.endpoint == ashby.ASHBY_PUBLIC_GRAPHQL_URL
        assert (
            smartrecruiters_client.page_limit
            == smartrecruiters.SMARTRECRUITERS_DEFAULT_PAGE_LIMIT
        )
        assert smartrecruiters_client.search_text is None
    finally:
        ashby_client.close()
        smartrecruiters_client.close()


def test_personio_factory_defaults_and_honors_language() -> None:
    personio_spec = get_ats_provider_spec(AtsProvider.PERSONIO)
    default_client = cast(
        Any,
        personio_spec.make_client(
            AtsClientOptions(request_delay_seconds=0, max_retries=0)
        ),
    )
    localized_client = cast(
        Any,
        personio_spec.make_client(
            AtsClientOptions(
                request_delay_seconds=0,
                max_retries=0,
                language="de",
            )
        )
    )

    try:
        assert default_client.language == personio.DEFAULT_PERSONIO_LANGUAGE == "en"
        assert localized_client.language == "de"
    finally:
        default_client.close()
        localized_client.close()


def test_registry_pairs_each_provider_with_its_existing_callables() -> None:
    callable_names: dict[str, Callable[[AtsProvider], str]] = {
        "normalize_board": lambda provider: f"normalize_{provider.value}_board",
        "generate_discovery_queries": lambda provider: (
            f"generate_{provider.value}_discovery_queries"
        ),
        "discover_boards": lambda provider: f"discover_{provider.value}_boards",
        "collect_boards": lambda provider: f"collect_{provider.value}_boards",
    }

    for provider, module in PROVIDER_MODULES.items():
        spec = get_ats_provider_spec(provider)
        for spec_field, name_for_provider in callable_names.items():
            assert getattr(spec, spec_field) is getattr(
                module,
                name_for_provider(provider),
            )
