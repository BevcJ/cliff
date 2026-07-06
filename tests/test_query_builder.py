import pytest

from ai_hiring_radar.config import load_countries_config, load_taxonomy_config
from ai_hiring_radar.query_builder import LocationDepth, generate_search_queries


def test_generate_search_queries_creates_initial_country_level_queries() -> None:
    countries_config = load_countries_config()
    taxonomy_config = load_taxonomy_config()

    queries = generate_search_queries(
        countries_config=countries_config,
        country_codes=["nl", "uk", "dk"],
        role_terms=taxonomy_config.all_roles,
    )

    assert len(queries) == 30
    assert queries[0].search_query == (
        '"AI Engineer" site:linkedin.com/jobs/view Netherlands'
    )
    assert queries[0].request_params == {
        "q": '"AI Engineer" site:linkedin.com/jobs/view Netherlands',
        "location": "Netherlands",
        "gl": "nl",
        "hl": "en",
        "num": 10,
    }
    assert queries[0].search_location_label == "Netherlands"
    assert queries[0].query_location == "Netherlands"
    assert queries[0].serper_location == "Netherlands"
    assert queries[-1].search_query == (
        '"AI Solutions Product Manager" site:linkedin.com/jobs/view Denmark'
    )
    assert all("api_key" not in query.request_params for query in queries)


def test_generate_search_queries_can_expand_netherlands_city_locations() -> None:
    countries_config = load_countries_config()

    queries = generate_search_queries(
        countries_config=countries_config,
        country_codes=["nl"],
        role_terms=["AI Engineer", "LLM Engineer"],
        location_depth=LocationDepth.CITIES,
    )

    assert len(queries) == 22
    assert [query.search_location_label for query in queries[:4]] == [
        "Netherlands",
        "Netherlands",
        "Amsterdam",
        "Amsterdam",
    ]
    assert queries[2].search_query == (
        '"AI Engineer" site:linkedin.com/jobs/view Amsterdam Netherlands'
    )
    assert queries[2].request_params["location"] == (
        "Amsterdam, North Holland, Netherlands"
    )


def test_generate_search_queries_limit_preserves_country_role_order() -> None:
    countries_config = load_countries_config()

    queries = generate_search_queries(
        countries_config=countries_config,
        country_codes=["nl", "dk"],
        role_terms=["AI Engineer", "LLM Engineer"],
        limit=3,
    )

    assert [query.search_query for query in queries] == [
        '"AI Engineer" site:linkedin.com/jobs/view Netherlands',
        '"LLM Engineer" site:linkedin.com/jobs/view Netherlands',
        '"AI Engineer" site:linkedin.com/jobs/view Denmark',
    ]


def test_generate_search_queries_rejects_unknown_country() -> None:
    countries_config = load_countries_config()

    with pytest.raises(ValueError, match="Unknown country code: se"):
        generate_search_queries(
            countries_config=countries_config,
            country_codes=["se"],
            role_terms=["AI Engineer"],
        )


def test_generate_search_queries_rejects_empty_role_term() -> None:
    countries_config = load_countries_config()

    with pytest.raises(ValueError, match="Role term is required"):
        generate_search_queries(
            countries_config=countries_config,
            country_codes=["nl"],
            role_terms=["  "],
        )
