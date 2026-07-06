from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class CountryInference:
    country_codes: list[str]
    countries: list[str]


COUNTRY_NAMES_BY_CODE = {
    "al": "Albania",
    "ar": "Argentina",
    "at": "Austria",
    "au": "Australia",
    "be": "Belgium",
    "bg": "Bulgaria",
    "bo": "Bolivia",
    "br": "Brazil",
    "ca": "Canada",
    "ch": "Switzerland",
    "cl": "Chile",
    "cn": "China",
    "co": "Colombia",
    "cz": "Czech Republic",
    "de": "Germany",
    "dk": "Denmark",
    "ec": "Ecuador",
    "ee": "Estonia",
    "eg": "Egypt",
    "es": "Spain",
    "fi": "Finland",
    "fr": "France",
    "hk": "Hong Kong",
    "hr": "Croatia",
    "hu": "Hungary",
    "id": "Indonesia",
    "ie": "Ireland",
    "il": "Israel",
    "in": "India",
    "it": "Italy",
    "jp": "Japan",
    "kr": "South Korea",
    "lt": "Lithuania",
    "lv": "Latvia",
    "mx": "Mexico",
    "my": "Malaysia",
    "nl": "Netherlands",
    "no": "Norway",
    "nz": "New Zealand",
    "pe": "Peru",
    "ph": "Philippines",
    "pl": "Poland",
    "pt": "Portugal",
    "py": "Paraguay",
    "ro": "Romania",
    "rs": "Serbia",
    "se": "Sweden",
    "sg": "Singapore",
    "si": "Slovenia",
    "sk": "Slovakia",
    "th": "Thailand",
    "tr": "Turkey",
    "tw": "Taiwan",
    "ua": "Ukraine",
    "uk": "United Kingdom",
    "us": "United States",
    "uy": "Uruguay",
    "vn": "Vietnam",
    "za": "South Africa",
}

COUNTRY_ALIASES = {
    "albania": "al",
    "argentina": "ar",
    "austria": "at",
    "australia": "au",
    "au": "au",
    "belgium": "be",
    "brazil": "br",
    "bulgaria": "bg",
    "bolivia": "bo",
    "canada": "ca",
    "switzerland": "ch",
    "chile": "cl",
    "china": "cn",
    "colombia": "co",
    "czech republic": "cz",
    "czechia": "cz",
    "denmark": "dk",
    "deutschland": "de",
    "ecuador": "ec",
    "egypt": "eg",
    "england": "uk",
    "estonia": "ee",
    "finland": "fi",
    "france": "fr",
    "germany": "de",
    "hong kong": "hk",
    "croatia": "hr",
    "hungary": "hu",
    "india": "in",
    "indonesia": "id",
    "ireland": "ie",
    "israel": "il",
    "italy": "it",
    "japan": "jp",
    "latvia": "lv",
    "lithuania": "lt",
    "malaysia": "my",
    "mexico": "mx",
    "netherlands": "nl",
    "the netherlands": "nl",
    "holland": "nl",
    "new zealand": "nz",
    "norway": "no",
    "paraguay": "py",
    "peru": "pe",
    "philippines": "ph",
    "poland": "pl",
    "portugal": "pt",
    "romania": "ro",
    "scotland": "uk",
    "serbia": "rs",
    "singapore": "sg",
    "slovakia": "sk",
    "slovenia": "si",
    "south africa": "za",
    "south korea": "kr",
    "spain": "es",
    "sweden": "se",
    "taiwan": "tw",
    "thailand": "th",
    "turkey": "tr",
    "u k": "uk",
    "uk": "uk",
    "united kingdom": "uk",
    "northern ireland": "uk",
    "wales": "uk",
    "u s": "us",
    "u s a": "us",
    "us": "us",
    "usa": "us",
    "united states": "us",
    "united states of america": "us",
    "ukraine": "ua",
    "uruguay": "uy",
    "vietnam": "vn",
}

CITY_COUNTRY_CODES = {
    "aachen": "de",
    "amsterdam": "nl",
    "arnhem": "nl",
    "atlanta": "us",
    "austin": "us",
    "bangalore": "in",
    "bangkok": "th",
    "barcelona": "es",
    "beijing": "cn",
    "belfast": "uk",
    "belgrade": "rs",
    "bellevue": "us",
    "bengaluru": "in",
    "berlin": "de",
    "berlin metropolitain area": "de",
    "birmingham": "uk",
    "bologna": "it",
    "boston": "us",
    "bristol": "uk",
    "brussels": "be",
    "bucharest": "ro",
    "budapest": "hu",
    "buenos aires": "ar",
    "cambridge": "uk",
    "cardiff": "uk",
    "chicago": "us",
    "cologne": "de",
    "copenhagen": "dk",
    "dallas": "us",
    "delft": "nl",
    "den haag": "nl",
    "denver": "us",
    "dublin": "ie",
    "edinburgh": "uk",
    "eindhoven": "nl",
    "geneva": "ch",
    "glasgow": "uk",
    "groningen": "nl",
    "haarlem": "nl",
    "hamburg": "de",
    "helsinki": "fi",
    "ho chi minh": "vn",
    "istanbul": "tr",
    "jakarta": "id",
    "koln": "de",
    "krakow": "pl",
    "kuala lumpur": "my",
    "leeds": "uk",
    "leiden": "nl",
    "leuven": "be",
    "lisbon": "pt",
    "london": "uk",
    "london metropolitain area": "uk",
    "los angeles": "us",
    "madrid": "es",
    "manchester": "uk",
    "manila": "ph",
    "melbourne": "au",
    "mexico city": "mx",
    "miami": "us",
    "milan": "it",
    "montreal": "ca",
    "mumbai": "in",
    "munchen": "de",
    "munich": "de",
    "new york": "us",
    "new york city": "us",
    "north brabant": "nl",
    "north holland": "nl",
    "north rhine westphalia": "de",
    "oslo": "no",
    "oxford": "uk",
    "paris": "fr",
    "phoenix": "us",
    "portland": "us",
    "porto": "pt",
    "prague": "cz",
    "presidio ca": "us",
    "randstad": "nl",
    "rome": "it",
    "rome metropolitain area": "it",
    "rotterdam": "nl",
    "salt lake city": "us",
    "san carlos": "us",
    "san francisco": "us",
    "seattle": "us",
    "seoul": "kr",
    "sf bay area": "us",
    "shanghai": "cn",
    "shenzhen": "cn",
    "south holland": "nl",
    "stockholm": "se",
    "stuttgart": "de",
    "sydney": "au",
    "tallinn": "ee",
    "the hague": "nl",
    "tirana": "al",
    "tokyo": "jp",
    "toronto": "ca",
    "turin": "it",
    "utrecht": "nl",
    "vancouver": "ca",
    "vienna": "at",
    "warsaw": "pl",
    "washington dc": "us",
    "waterloo": "ca",
    "zagreb": "hr",
    "zurich": "ch",
}


def _normalized_text(value: object | None) -> str:
    raw = " ".join(str(value or "").split()).strip()
    if not raw:
        return ""

    ascii_text = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", ascii_text.casefold()).strip()


def _contains_phrase(text: str, phrase: str) -> bool:
    if not text or not phrase:
        return False
    padded_text = f" {text} "
    padded_phrase = f" {phrase} "
    return padded_phrase in padded_text


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def infer_country_codes_from_location(value: object | None) -> list[str]:
    normalized = _normalized_text(value)
    if not normalized:
        return []

    country_codes: list[str] = []
    for alias, code in sorted(
        COUNTRY_ALIASES.items(), key=lambda item: len(item[0]), reverse=True
    ):
        normalized_alias = _normalized_text(alias)
        if _contains_phrase(normalized, normalized_alias):
            _append_unique(country_codes, code)

    for city, code in sorted(
        CITY_COUNTRY_CODES.items(), key=lambda item: len(item[0]), reverse=True
    ):
        normalized_city = _normalized_text(city)
        if _contains_phrase(normalized, normalized_city):
            _append_unique(country_codes, code)

    return country_codes


def infer_countries_from_locations(locations: Iterable[object | None]) -> CountryInference:
    country_codes: list[str] = []
    for location in locations:
        for code in infer_country_codes_from_location(location):
            _append_unique(country_codes, code)

    return CountryInference(
        country_codes=country_codes,
        countries=[COUNTRY_NAMES_BY_CODE[code] for code in country_codes],
    )
