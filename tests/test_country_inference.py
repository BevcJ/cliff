from ai_hiring_radar.country_inference import infer_countries_from_locations


def test_infer_countries_from_country_aliases_and_remote_locations() -> None:
    inference = infer_countries_from_locations(["Remote - Netherlands", "UK"])

    assert inference.country_codes == ["nl", "uk"]
    assert inference.countries == ["Netherlands", "United Kingdom"]


def test_infer_countries_from_city_locations() -> None:
    inference = infer_countries_from_locations(["Amsterdam", "Aachen", "Warsaw"])

    assert inference.country_codes == ["nl", "de", "pl"]
    assert inference.countries == ["Netherlands", "Germany", "Poland"]


def test_infer_countries_from_diacritic_city_names() -> None:
    inference = infer_countries_from_locations(["Köln"])

    assert inference.country_codes == ["de"]
    assert inference.countries == ["Germany"]
