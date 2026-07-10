from ai_hiring_radar.config import load_countries_config
from ai_hiring_radar.search_locations import (
    LocationDepth,
    country_search_location,
    iter_search_locations,
)


def test_country_search_location_uses_country_level_location() -> None:
    country = load_countries_config().countries["nl"]

    search_location = country_search_location(country)

    assert search_location.label == "Netherlands"
    assert search_location.query_location == "Netherlands"
    assert search_location.serper_location == "Netherlands"


def test_iter_search_locations_defaults_to_country_level_location() -> None:
    country = load_countries_config().countries["nl"]

    search_locations = iter_search_locations(country)

    assert [location.label for location in search_locations] == ["Netherlands"]


def test_iter_search_locations_can_expand_city_locations() -> None:
    country = load_countries_config().countries["nl"]

    search_locations = iter_search_locations(
        country,
        location_depth=LocationDepth.CITIES,
    )

    assert [location.label for location in search_locations[:3]] == [
        "Netherlands",
        "Amsterdam",
        "Rotterdam",
    ]
    assert search_locations[1].query_location == "Amsterdam Netherlands"
    assert search_locations[1].serper_location == "Amsterdam, North Holland, Netherlands"
