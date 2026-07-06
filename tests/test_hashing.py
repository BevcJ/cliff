import hashlib

from ai_hiring_radar.hashing import HASH_SEPARATOR, job_candidate_id, normalize_hash_part


def test_normalize_hash_part_is_case_and_whitespace_insensitive() -> None:
    assert normalize_hash_part("  AI   Product Manager  ") == "ai product manager"


def test_job_candidate_id_uses_url_when_present() -> None:
    job_id = job_candidate_id(
        source_url=" https://example.com/jobs/123 ",
        country_code="NL",
        role_search_term="AI Product Manager",
        job_title_raw=" AI Product Manager - Example Company ",
        snippet="ignored when URL exists",
    )

    expected_parts = (
        "https://example.com/jobs/123",
        "nl",
        "ai product manager",
        "ai product manager - example company",
    )
    expected = hashlib.sha256(HASH_SEPARATOR.join(expected_parts).encode("utf-8")).hexdigest()

    assert job_id == expected


def test_job_candidate_id_falls_back_to_snippet_without_url() -> None:
    first = job_candidate_id(
        source_url=None,
        country_code="dk",
        role_search_term="LLM Engineer",
        job_title_raw="LLM Engineer",
        snippet="Example snippet",
    )
    second = job_candidate_id(
        source_url="",
        country_code=" DK ",
        role_search_term=" llm   engineer ",
        job_title_raw=" LLM Engineer ",
        snippet=" example snippet ",
    )

    assert first == second
