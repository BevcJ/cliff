from pathlib import Path

from ai_hiring_radar.normalize import (
    extract_company_name,
    is_concrete_linkedin_job_url,
    normalize_organic_result,
)


def _metadata() -> dict[str, str]:
    return {
        "source": "serper_google",
        "source_mode": "linkedin_safe_search",
        "country_code": "nl",
        "country": "Netherlands",
        "search_location_label": "Amsterdam",
        "query_location": "Amsterdam Netherlands",
        "serper_location": "Amsterdam, North Holland, Netherlands",
        "role_search_term": "AI Product Manager",
        "search_query": '"AI Product Manager" site:linkedin.com/jobs/view Amsterdam Netherlands',
        "collected_at": "2026-06-14T10:30:00Z",
    }


def test_linkedin_job_url_quality_gate_accepts_only_view_pages() -> None:
    assert is_concrete_linkedin_job_url("https://www.linkedin.com/jobs/view/123")
    assert is_concrete_linkedin_job_url(
        "https://nl.linkedin.com/jobs/view/ai-product-manager-at-example-123"
    )

    assert not is_concrete_linkedin_job_url(
        "https://www.linkedin.com/jobs/search?keywords=AI+Product+Manager"
    )
    assert not is_concrete_linkedin_job_url(
        "https://www.linkedin.com/jobs/product-manager-jobs-rotterdam"
    )
    assert not is_concrete_linkedin_job_url("https://example.com/jobs/view/123")


def test_extract_company_name_from_linkedin_hiring_title() -> None:
    assert (
        extract_company_name(
            title="Discover International hiring AI Product Manager in European Union"
        )
        == "Discover International"
    )


def test_normalize_organic_result_skips_linkedin_listing_urls() -> None:
    candidate = normalize_organic_result(
        metadata=_metadata(),
        result={
            "position": 1,
            "title": "2,000+ Product Manager jobs in Netherlands - LinkedIn",
            "link": "https://www.linkedin.com/jobs/search?keywords=Product+Manager",
            "snippet": "AI Product Manager. Example Company. Amsterdam.",
        },
        raw_file=Path("raw.json"),
    )

    assert candidate is None


def test_normalize_organic_result_keeps_concrete_linkedin_job_view() -> None:
    candidate = normalize_organic_result(
        metadata=_metadata(),
        result={
            "position": 1,
            "title": "Discover International hiring AI Product Manager in European Union",
            "link": "https://www.linkedin.com/jobs/view/ai-product-manager-at-discover-international-4354260580",
            "snippet": "Netherlands $50,000 - $60,000 1 day ago.",
        },
        raw_file=Path("raw.json"),
    )

    assert candidate is not None
    assert candidate["search_location_label"] == "Amsterdam"
    assert candidate["query_location"] == "Amsterdam Netherlands"
    assert candidate["serper_location"] == "Amsterdam, North Holland, Netherlands"
    assert candidate["company_normalized"] == "Discover International"
    assert candidate["job_title_normalized"] == "AI Product Manager"
    assert candidate["source_url"] == (
        "https://www.linkedin.com/jobs/view/ai-product-manager-at-discover-international-4354260580"
    )
