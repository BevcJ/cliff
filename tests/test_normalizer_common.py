from pathlib import Path

import pytest

from ai_hiring_radar.country_inference import CountryInference
from ai_hiring_radar.hashing import stable_sha256
from ai_hiring_radar.models import SourceName
from ai_hiring_radar.normalizers.common.candidate import build_ats_candidate
from ai_hiring_radar.normalizers.common.company import (
    company_name_from_slug,
    normalize_company_name,
)
from ai_hiring_radar.normalizers.common.countries import normalize_country_code


def test_build_ats_candidate_emits_base_fields_and_preserves_extra_fields() -> None:
    candidate = build_ats_candidate(
        source=SourceName.WORKABLE,
        metadata={
            "search_location_label": "Amsterdam",
            "query_location": "Amsterdam Netherlands",
            "serper_location": "Amsterdam, North Holland, Netherlands",
            "collected_at": "2026-06-16T10:00:01Z",
        },
        raw_file=Path("data/raw/ats/2026-06-16/workable/acme-ai.json"),
        platform_company_slug="acme-ai",
        platform_job_id="AIENG",
        board_url="https://apply.workable.com/acme-ai",
        source_url="https://apply.workable.com/acme-ai/j/AIENG",
        job_url="https://apply.workable.com/acme-ai/j/AIENG",
        job_title_raw="Senior AI Engineer",
        company_raw="Acme AI",
        country_inference=CountryInference(
            country_codes=["nl"],
            countries=["Netherlands"],
        ),
        location="Amsterdam, North Holland, Netherlands",
        job_locations_raw=["Amsterdam, North Holland, Netherlands"],
        extra_fields={
            "team": None,
            "departments": [],
            "remote": False,
        },
    )

    assert candidate["record_type"] == "job_candidate"
    assert candidate["job_id"] == stable_sha256(("workable", "acme-ai", "AIENG"))
    assert candidate["country_code"] == "nl"
    assert candidate["country"] == "Netherlands"
    assert candidate["job_country_codes"] == ["nl"]
    assert candidate["job_countries"] == ["Netherlands"]
    assert candidate["source"] == "workable"
    assert candidate["source_mode"] == "public_job_board_endpoint"
    assert candidate["source_url"] == "https://apply.workable.com/acme-ai/j/AIENG"
    assert candidate["board_url"] == "https://apply.workable.com/acme-ai"
    assert candidate["job_url"] == "https://apply.workable.com/acme-ai/j/AIENG"
    assert candidate["platform"] == "workable"
    assert candidate["platform_company_slug"] == "acme-ai"
    assert candidate["platform_job_id"] == "AIENG"
    assert candidate["result_rank"] is None
    assert candidate["displayed_link"] is None
    assert candidate["company_raw"] == "Acme AI"
    assert candidate["company_normalized"] == "Acme AI"
    assert candidate["job_title_raw"] == "Senior AI Engineer"
    assert candidate["job_title_normalized"] == "AI Engineer"
    assert candidate["role_search_term"] == "AI Engineer"
    assert candidate["role_group"] == "AI Execution Role"
    assert candidate["search_query"] is None
    assert candidate["snippet"] is None
    assert candidate["search_location_label"] == "Amsterdam"
    assert candidate["query_location"] == "Amsterdam Netherlands"
    assert candidate["serper_location"] == "Amsterdam, North Holland, Netherlands"
    assert candidate["location"] == "Amsterdam, North Holland, Netherlands"
    assert candidate["job_location_raw"] == "Amsterdam, North Holland, Netherlands"
    assert candidate["job_locations_raw"] == ["Amsterdam, North Holland, Netherlands"]
    assert candidate["evidence_quality"] == "title_only_ats_listing"
    assert candidate["needs_review"] is True
    assert candidate["collected_at"] == "2026-06-16T10:00:01Z"
    assert candidate["raw_file"] == "data/raw/ats/2026-06-16/workable/acme-ai.json"
    assert candidate["team"] is None
    assert candidate["departments"] == []
    assert candidate["remote"] is False


def test_build_ats_candidate_preserves_empty_country_fields() -> None:
    candidate = build_ats_candidate(
        source=SourceName.ASHBY,
        metadata={},
        raw_file=Path("raw.json"),
        platform_company_slug="acme-ai",
        platform_job_id="job-ai-engineer",
        board_url="https://jobs.ashbyhq.com/acme-ai",
        source_url="https://jobs.ashbyhq.com/acme-ai",
        job_title_raw="AI Engineer",
        company_raw="Acme AI",
        country_inference=CountryInference(country_codes=[], countries=[]),
    )

    assert candidate["country_code"] == ""
    assert candidate["country"] is None
    assert candidate["job_country_codes"] == []
    assert candidate["job_countries"] == []
    assert candidate["search_location_label"] is None
    assert candidate["query_location"] is None
    assert candidate["serper_location"] is None
    assert candidate["job_url"] is None
    assert candidate["location"] is None
    assert candidate["job_location_raw"] is None
    assert candidate["job_locations_raw"] == []


def test_build_ats_candidate_rejects_base_field_conflicts() -> None:
    with pytest.raises(ValueError, match="source_url"):
        build_ats_candidate(
            source=SourceName.WORKABLE,
            metadata={},
            raw_file=Path("raw.json"),
            platform_company_slug="acme-ai",
            platform_job_id="AIENG",
            board_url="https://apply.workable.com/acme-ai",
            source_url="https://apply.workable.com/acme-ai/j/AIENG",
            job_title_raw="AI Engineer",
            company_raw="Acme AI",
            country_inference=CountryInference(country_codes=[], countries=[]),
            extra_fields={"source_url": "https://example.com"},
        )


def test_common_company_and_country_helpers_preserve_existing_behavior() -> None:
    assert company_name_from_slug("acme-ai") == "Acme Ai"
    assert normalize_company_name("Discover International is hiring AI Engineer") == (
        "Discover International"
    )
    assert normalize_company_name("LinkedIn jobs") is None
    assert normalize_country_code("GB") == "uk"
    assert normalize_country_code("NL") == "nl"
    assert normalize_country_code("unknown") is None
