from __future__ import annotations

from enum import StrEnum

from ai_hiring_radar.config import CountryConfig, SearchLocationConfig


class LocationDepth(StrEnum):
    COUNTRY = "country"
    CITIES = "cities"


def country_search_location(country: CountryConfig) -> SearchLocationConfig:
    return SearchLocationConfig(
        label=country.name,
        query_location=country.name,
        serper_location=country.search_location,
    )


def iter_search_locations(
    country: CountryConfig,
    *,
    location_depth: LocationDepth = LocationDepth.COUNTRY,
) -> list[SearchLocationConfig]:
    if location_depth == LocationDepth.CITIES and country.search_locations:
        return country.search_locations
    return [country_search_location(country)]
