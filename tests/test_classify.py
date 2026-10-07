import pytest

from ai_hiring_radar.classify import (
    classify_role,
    is_ai_role_title_candidate,
    normalize_job_title,
    title_prefilter_metadata,
)
from ai_hiring_radar.config import TaxonomyConfig


def test_normalize_job_title_prefers_longest_known_role_match() -> None:
    assert (
        normalize_job_title(
            "Senior Applied AI Engineer - Example Company",
            role_search_term="AI Engineer",
        )
        == "Applied AI Engineer"
    )


def test_normalize_job_title_uses_first_known_role_phrase() -> None:
    assert normalize_job_title("Data Scientist / AI Engineer") == "Data Scientist"
    assert normalize_job_title("AI Engineer / Data Scientist") == "AI Engineer"


def test_normalize_job_title_prefers_specific_match_at_same_position() -> None:
    taxonomy = TaxonomyConfig(
        execution_roles=["AI", "AI Engineer"],
        product_roles=[],
    )

    assert (
        normalize_job_title("AI Engineer", taxonomy_config=taxonomy) == "AI Engineer"
    )


@pytest.mark.parametrize(
    ("raw_title", "canonical_title"),
    [
        ("Senior Data Scientist", "Data Scientist"),
        ("Principal Machine Learning Engineer", "Machine Learning Engineer"),
        ("Staff ML Engineer, Personalization", "Machine Learning Engineer"),
    ],
)
def test_normalize_job_title_canonicalizes_new_roles(
    raw_title: str,
    canonical_title: str,
) -> None:
    assert normalize_job_title(raw_title) == canonical_title


def test_normalize_job_title_uses_role_search_term_as_fallback() -> None:
    assert (
        normalize_job_title(
            "Product role at Example Company",
            role_search_term="AI Product Manager",
        )
        == "AI Product Manager"
    )


def test_classify_role_detects_product_role() -> None:
    assert (
        classify_role(
            job_title_raw="Senior AI Product Manager - Example Company",
            job_title_normalized="AI Product Manager",
            role_search_term="AI Product Manager",
        )
        == "AI Product Role"
    )


@pytest.mark.parametrize(
    ("raw_title", "role_group"),
    [
        ("Senior Data Scientist", "Data Science Role"),
        ("Staff ML Engineer", "Machine Learning Role"),
    ],
)
def test_classify_role_detects_new_role_groups(
    raw_title: str,
    role_group: str,
) -> None:
    assert classify_role(job_title_raw=raw_title) == role_group


def test_classify_role_uses_raw_title_precedence() -> None:
    assert (
        classify_role(
            job_title_raw="AI Engineer / Data Scientist",
            job_title_normalized="Data Scientist",
        )
        == "AI Execution Role"
    )


def test_classify_role_marks_unknown_ai_signal_unclear() -> None:
    assert (
        classify_role(
            job_title_raw="Head of Artificial Intelligence - Example Company",
            role_search_term="Head of AI",
        )
        == "Unclear AI Role"
    )


def test_is_ai_role_title_candidate_uses_strict_title_prefilter() -> None:
    assert is_ai_role_title_candidate("Senior AI Engineer") is True
    assert is_ai_role_title_candidate("Senior Data Scientist") is True
    assert is_ai_role_title_candidate("Machine Learning Engineer") is True
    assert is_ai_role_title_candidate("ML Engineer") is True
    assert is_ai_role_title_candidate("Head of Artificial Intelligence") is True
    assert is_ai_role_title_candidate("Backend Engineer") is False
    assert (
        is_ai_role_title_candidate("Machine Learning Engineer - AI Trainer - Freelance")
        is False
    )


@pytest.mark.parametrize(
    "title",
    [
        "Data Science Manager",
        "MLOps Engineer",
        "Applied Scientist",
        "Research Scientist",
        "Data Analyst",
        "Data Engineer",
    ],
)
def test_is_ai_role_title_candidate_rejects_adjacent_roles(title: str) -> None:
    assert is_ai_role_title_candidate(title) is False


def test_title_prefilter_metadata_counts_skipped_titles() -> None:
    assert title_prefilter_metadata(listed_count=4, matched_count=2) == {
        "mode": "strict_title",
        "source": "listing_title",
        "source_field": "title",
        "listed_count": 4,
        "matched_count": 2,
        "skipped_count": 2,
    }
