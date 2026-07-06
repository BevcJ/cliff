from typing import Any

from ai_hiring_radar.aggregate import aggregate_companies


def _candidate(**overrides: Any) -> dict[str, Any]:
    candidate = {
        "company_normalized": "Example Company",
        "job_title_raw": "Senior AI Product Manager - Example Company",
        "country": "Netherlands",
        "job_title_normalized": "AI Product Manager",
        "role_search_term": "AI Product Manager",
        "role_group": "AI Product Role",
        "source_url": "https://www.linkedin.com/jobs/view/1",
        "source": "serper_google",
        "evidence_quality": "title_only_search_result",
        "needs_review": True,
    }
    candidate.update(overrides)
    return candidate


def test_aggregate_company_detects_both_role_groups() -> None:
    companies = aggregate_companies(
        [
            _candidate(),
            _candidate(
                country="Denmark",
                job_title_raw="Staff LLM Engineer - Example Company",
                job_title_normalized="LLM Engineer",
                role_search_term="LLM Engineer",
                role_group="AI Execution Role",
                source_url="https://www.linkedin.com/jobs/view/2",
            ),
        ]
    )

    assert companies == [
        {
            "record_type": "company_intelligence_title_only",
            "company": "Example Company",
            "countries": ["Netherlands", "Denmark"],
            "role_classification": "Both Execution + Product",
            "ai_execution_titles": ["LLM Engineer"],
            "ai_product_titles": ["AI Product Manager"],
            "ai_role_title_counts": [
                {"title": "Senior AI Product Manager - Example Company", "count": 1},
                {"title": "Staff LLM Engineer - Example Company", "count": 1},
            ],
            "matched_search_terms": ["AI Product Manager", "LLM Engineer"],
            "evidence_urls": [
                "https://www.linkedin.com/jobs/view/1",
                "https://www.linkedin.com/jobs/view/2",
            ],
            "sources": ["serper_google"],
            "evidence_quality": ["title_only_search_result"],
            "needs_review": True,
            "review_status": "new",
            "why_interesting": (
                "Example Company appears in search results for AI Product Manager, "
                "LLM Engineer in Netherlands, Denmark. Needs manual validation because "
                "evidence is title-only."
            ),
        }
    ]


def test_aggregate_excludes_candidates_without_company() -> None:
    assert aggregate_companies([_candidate(company_normalized=None)]) == []


def test_aggregate_excludes_company_records_without_evidence_url() -> None:
    assert aggregate_companies([_candidate(source_url=None)]) == []


def test_aggregate_prefers_inferred_job_countries() -> None:
    companies = aggregate_companies(
        [
            _candidate(
                country="Amsterdam",
                job_countries=["Netherlands"],
                job_country_codes=["nl"],
            )
        ]
    )

    assert companies[0]["countries"] == ["Netherlands"]


def test_aggregate_counts_raw_titles_and_includes_unclear_roles() -> None:
    companies = aggregate_companies(
        [
            _candidate(
                job_title_raw="Senior AI Engineer",
                job_title_normalized="AI Engineer",
                role_search_term="AI Engineer",
                role_group="AI Execution Role",
                source_url="https://www.linkedin.com/jobs/view/1",
            ),
            _candidate(
                job_title_raw="Senior AI Engineer",
                job_title_normalized="AI Engineer",
                role_search_term="AI Engineer",
                role_group="AI Execution Role",
                source_url="https://www.linkedin.com/jobs/view/2",
            ),
            _candidate(
                job_title_raw="Head of Artificial Intelligence",
                job_title_normalized="Head of Artificial Intelligence",
                role_search_term="title contains AI",
                role_group="Unclear AI Role",
                source_url="https://www.linkedin.com/jobs/view/3",
            ),
        ]
    )

    assert companies[0]["ai_role_title_counts"] == [
        {"title": "Senior AI Engineer", "count": 2},
        {"title": "Head of Artificial Intelligence", "count": 1},
    ]
