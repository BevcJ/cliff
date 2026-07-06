from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

from ai_hiring_radar.config import CountriesConfig, CountryConfig, SearchLocationConfig


DEFAULT_SEARCH_NUM_RESULTS = 10


class LocationDepth(StrEnum):
    COUNTRY = "country"
    CITIES = "cities"


@dataclass(frozen=True)
class SearchQuery:
    country_code: str
    country: str
    search_location_label: str
    query_location: str
    serper_location: str
    role_search_term: str
    search_query: str
    request_params: dict[str, str | int]


def build_linkedin_jobs_query(*, role_term: str, query_location: str) -> str:
    normalized_role = role_term.strip()
    normalized_location = query_location.strip()

    if not normalized_role:
        raise ValueError("Role term is required.")
    if not normalized_location:
        raise ValueError("Search location is required.")

    return f'"{normalized_role}" site:linkedin.com/jobs/view {normalized_location}'


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


def build_google_search_query(
    *,
    country_code: str,
    country: CountryConfig,
    search_location: SearchLocationConfig | None = None,
    role_term: str,
    num: int = DEFAULT_SEARCH_NUM_RESULTS,
) -> SearchQuery:
    normalized_country_code = country_code.strip().lower()
    normalized_role = role_term.strip()
    selected_location = search_location or country_search_location(country)
    search_query = build_linkedin_jobs_query(
        role_term=normalized_role,
        query_location=selected_location.query_location,
    )

    return SearchQuery(
        country_code=normalized_country_code,
        country=country.name,
        search_location_label=selected_location.label,
        query_location=selected_location.query_location,
        serper_location=selected_location.serper_location,
        role_search_term=normalized_role,
        search_query=search_query,
        request_params={
            "q": search_query,
            "location": selected_location.serper_location,
            "gl": country.gl,
            "hl": country.hl,
            "num": num,
        },
    )


def generate_search_queries(
    *,
    countries_config: CountriesConfig,
    country_codes: Iterable[str],
    role_terms: Iterable[str],
    limit: int | None = None,
    num: int = DEFAULT_SEARCH_NUM_RESULTS,
    location_depth: LocationDepth = LocationDepth.COUNTRY,
) -> list[SearchQuery]:
    if limit is not None and limit < 1:
        raise ValueError("Limit must be greater than zero.")

    queries: list[SearchQuery] = []
    for raw_country_code in country_codes:
        country_code = raw_country_code.strip().lower()
        country = countries_config.countries.get(country_code)
        if country is None:
            raise ValueError(f"Unknown country code: {raw_country_code}")

        for search_location in iter_search_locations(
            country,
            location_depth=location_depth,
        ):
            for role_term in role_terms:
                queries.append(
                    build_google_search_query(
                        country_code=country_code,
                        country=country,
                        search_location=search_location,
                        role_term=role_term,
                        num=num,
                    )
                )
                if limit is not None and len(queries) >= limit:
                    return queries

    return queries
