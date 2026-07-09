from ai_hiring_radar.classify import (
    classify_role,
    is_ai_role_title_candidate,
    normalize_job_title,
    title_prefilter_metadata,
)


def test_normalize_job_title_prefers_longest_known_role_match() -> None:
    assert (
        normalize_job_title(
            "Senior Applied AI Engineer - Example Company",
            role_search_term="AI Engineer",
        )
        == "Applied AI Engineer"
    )


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
    assert is_ai_role_title_candidate("Head of Artificial Intelligence") is True
    assert is_ai_role_title_candidate("Backend Engineer") is False
    assert (
        is_ai_role_title_candidate("Machine Learning Engineer - AI Trainer - Freelance")
        is False
    )


def test_title_prefilter_metadata_counts_skipped_titles() -> None:
    assert title_prefilter_metadata(listed_count=4, matched_count=2) == {
        "mode": "strict_title",
        "source": "listing_title",
        "source_field": "title",
        "listed_count": 4,
        "matched_count": 2,
        "skipped_count": 2,
    }
