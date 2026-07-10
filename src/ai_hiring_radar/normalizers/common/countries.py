from __future__ import annotations

from ai_hiring_radar.classify import clean_text
from ai_hiring_radar.country_inference import COUNTRY_NAMES_BY_CODE, CountryInference


def normalize_country_code(value: object | None) -> str | None:
    country_code = clean_text(value).casefold()
    if country_code == "gb":
        country_code = "uk"
    if country_code in COUNTRY_NAMES_BY_CODE:
        return country_code
    return None


def country_inference_from_codes(country_codes: list[str]) -> CountryInference:
    return CountryInference(
        country_codes=country_codes,
        countries=[COUNTRY_NAMES_BY_CODE[code] for code in country_codes],
    )
