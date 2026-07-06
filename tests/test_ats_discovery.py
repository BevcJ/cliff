from dataclasses import dataclass

from ai_hiring_radar.config import load_countries_config
from ai_hiring_radar.query_builder import LocationDepth
from ai_hiring_radar.sources.ats_discovery import (
    AtsDiscoveryDepth,
    AtsDiscoveryProvider,
    build_ats_discovery_search_query,
    extract_ats_board_records,
    generate_ats_discovery_queries,
)


@dataclass(frozen=True)
class FakeBoard:
    platform_company_slug: str
    board_url: str


def _parse_fake_board(value: object | None) -> FakeBoard | None:
    raw_url = str(value or "")
    marker = "https://jobs.example.com/"
    if not raw_url.startswith(marker):
        return None
    slug = raw_url.removeprefix(marker).split("/", 1)[0]
    return FakeBoard(
        platform_company_slug=slug,
        board_url=f"https://jobs.example.com/{slug}",
    )


FAKE_PROVIDER = AtsDiscoveryProvider(
    platform="fakeats",
    site="jobs.example.com",
    parse_board_url=_parse_fake_board,
)


def test_build_ats_discovery_search_query_supports_site_only_and_terms() -> None:
    assert build_ats_discovery_search_query(provider=FAKE_PROVIDER) == "site:jobs.example.com"
    assert (
        build_ats_discovery_search_query(
            provider=FAKE_PROVIDER,
            terms=["AI Engineer", "Netherlands"],
        )
        == 'site:jobs.example.com "AI Engineer" "Netherlands"'
    )


def test_generate_ats_discovery_queries_supports_exhaustive_scale() -> None:
    queries = generate_ats_discovery_queries(
        provider=FAKE_PROVIDER,
        countries_config=load_countries_config(),
        country_codes=["nl"],
        role_terms=["AI Engineer"],
        signal_terms=["LLM"],
        pages=1,
        num=5,
        location_depth=LocationDepth.CITIES,
        discovery_depth=AtsDiscoveryDepth.EXHAUSTIVE,
    )

    query_types = {query.discovery_query_type for query in queries}
    assert query_types == {
        "site_only",
        "location",
        "role",
        "ai_signal",
        "role_country",
        "ai_signal_country",
        "role_location",
        "ai_signal_location",
    }
    assert any(query.search_query == "site:jobs.example.com" for query in queries)
    assert any(
        query.search_query == 'site:jobs.example.com "AI Engineer" "Amsterdam"'
        for query in queries
    )
    assert {query.request_params["num"] for query in queries} == {5}


def test_extract_ats_board_records_dedupes_by_provider_slug() -> None:
    query = generate_ats_discovery_queries(
        provider=FAKE_PROVIDER,
        countries_config=load_countries_config(),
        country_codes=["nl"],
        limit=1,
    )[0]

    records = extract_ats_board_records(
        provider=FAKE_PROVIDER,
        discovery_query=query,
        collected_at="2026-06-16T10:00:00Z",
        response={
            "organic_results": [
                {
                    "position": 1,
                    "title": "Acme jobs",
                    "link": "https://jobs.example.com/acme/jobs/123",
                    "snippet": "Acme is hiring.",
                },
                {
                    "position": 2,
                    "title": "Acme careers",
                    "link": "https://jobs.example.com/acme",
                },
                {
                    "position": 3,
                    "title": "Other",
                    "link": "https://example.com/acme",
                },
            ]
        },
    )

    assert len(records) == 1
    assert records[0]["platform"] == "fakeats"
    assert records[0]["platform_company_slug"] == "acme"
    assert records[0]["discovery_query_type"] == "site_only"
    assert records[0]["search_page"] == 1
