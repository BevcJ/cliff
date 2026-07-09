from typing import Any

from ai_hiring_radar.dedupe import dedupe_job_candidates


def _candidate(**overrides: Any) -> dict[str, Any]:
    candidate = {
        "record_type": "job_candidate",
        "job_id": "job-1",
        "country": "Netherlands",
        "company_normalized": "Example Company",
        "job_title_raw": "AI Product Manager - Example Company",
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


def test_dedupe_exact_source_url_preserves_search_terms() -> None:
    deduped = dedupe_job_candidates(
        [
            _candidate(role_search_term="AI Product Manager"),
            _candidate(role_search_term="GenAI Product Manager"),
        ]
    )

    assert len(deduped) == 1
    assert deduped[0]["all_source_urls"] == ["https://www.linkedin.com/jobs/view/1"]
    assert deduped[0]["all_role_search_terms"] == [
        "AI Product Manager",
        "GenAI Product Manager",
    ]
    assert deduped[0]["all_postings"] == [
        {
            "posting_key": "source_url:https://www.linkedin.com/jobs/view/1",
            "job_title_raw": "AI Product Manager - Example Company",
            "role_group": "AI Product Role",
        }
    ]


def test_dedupe_same_company_title_country_after_url_pass() -> None:
    deduped = dedupe_job_candidates(
        [
            _candidate(source_url="https://www.linkedin.com/jobs/view/1"),
            _candidate(source_url="https://www.linkedin.com/jobs/view/2"),
        ]
    )

    assert len(deduped) == 1
    assert deduped[0]["all_source_urls"] == [
        "https://www.linkedin.com/jobs/view/1",
        "https://www.linkedin.com/jobs/view/2",
    ]
    assert deduped[0]["all_postings"] == [
        {
            "posting_key": "source_url:https://www.linkedin.com/jobs/view/1",
            "job_title_raw": "AI Product Manager - Example Company",
            "role_group": "AI Product Role",
        },
        {
            "posting_key": "source_url:https://www.linkedin.com/jobs/view/2",
            "job_title_raw": "AI Product Manager - Example Company",
            "role_group": "AI Product Role",
        },
    ]


def test_dedupe_missing_company_uses_raw_title_role_country() -> None:
    deduped = dedupe_job_candidates(
        [
            _candidate(company_normalized=None, source_url=None),
            _candidate(company_normalized=None, source_url=""),
        ]
    )

    assert len(deduped) == 1


def test_dedupe_keeps_distinct_ashby_jobs_with_same_board_url() -> None:
    deduped = dedupe_job_candidates(
        [
            _candidate(
                source="ashby",
                source_url="https://jobs.ashbyhq.com/everai",
                platform_company_slug="everai",
                platform_job_id="job-1",
                job_title_raw="Senior AI Engineer",
                job_title_normalized="AI Engineer",
                role_search_term="AI Engineer",
                role_group="AI Execution Role",
            ),
            _candidate(
                source="ashby",
                source_url="https://jobs.ashbyhq.com/everai",
                platform_company_slug="everai",
                platform_job_id="job-2",
                job_title_raw="AI Product Manager",
                job_title_normalized="AI Product Manager",
                role_search_term="AI Product Manager",
                role_group="AI Product Role",
            ),
        ]
    )

    assert len(deduped) == 2
    assert deduped[0]["all_postings"] == [
        {
            "posting_key": "platform:ashby:everai:job-1",
            "job_title_raw": "Senior AI Engineer",
            "role_group": "AI Execution Role",
        }
    ]


def test_dedupe_keeps_distinct_greenhouse_jobs_with_same_board_url() -> None:
    deduped = dedupe_job_candidates(
        [
            _candidate(
                source="greenhouse",
                source_url="https://boards.greenhouse.io/acme",
                platform_company_slug="acme",
                platform_job_id="7995153",
                job_title_raw="Senior AI Engineer",
                job_title_normalized="AI Engineer",
                role_search_term="AI Engineer",
                role_group="AI Execution Role",
            ),
            _candidate(
                source="greenhouse",
                source_url="https://boards.greenhouse.io/acme",
                platform_company_slug="acme",
                platform_job_id="7995155",
                job_title_raw="AI Product Manager",
                job_title_normalized="AI Product Manager",
                role_search_term="AI Product Manager",
                role_group="AI Product Role",
            ),
        ]
    )

    assert len(deduped) == 2


def test_dedupe_keeps_distinct_lever_jobs_with_same_board_url() -> None:
    deduped = dedupe_job_candidates(
        [
            _candidate(
                source="lever",
                source_url="https://jobs.lever.co/acme",
                platform_company_slug="acme",
                platform_job_id="job-ai-engineer",
                job_title_raw="Senior AI Engineer",
                job_title_normalized="AI Engineer",
                role_search_term="AI Engineer",
                role_group="AI Execution Role",
            ),
            _candidate(
                source="lever",
                source_url="https://jobs.lever.co/acme",
                platform_company_slug="acme",
                platform_job_id="job-ai-product",
                job_title_raw="AI Product Manager",
                job_title_normalized="AI Product Manager",
                role_search_term="AI Product Manager",
                role_group="AI Product Role",
            ),
        ]
    )

    assert len(deduped) == 2


def test_dedupe_keeps_distinct_personio_jobs_with_same_board_url() -> None:
    deduped = dedupe_job_candidates(
        [
            _candidate(
                source="personio",
                source_url="https://acme.jobs.personio.com",
                platform_company_slug="acme",
                platform_job_id="job-ai-engineer",
                job_title_raw="Senior AI Engineer",
                job_title_normalized="AI Engineer",
                role_search_term="AI Engineer",
                role_group="AI Execution Role",
            ),
            _candidate(
                source="personio",
                source_url="https://acme.jobs.personio.com",
                platform_company_slug="acme",
                platform_job_id="job-ai-product",
                job_title_raw="AI Product Manager",
                job_title_normalized="AI Product Manager",
                role_search_term="AI Product Manager",
                role_group="AI Product Role",
            ),
        ]
    )

    assert len(deduped) == 2


def test_dedupe_keeps_distinct_smartrecruiters_jobs_with_same_board_url() -> None:
    deduped = dedupe_job_candidates(
        [
            _candidate(
                source="smartrecruiters",
                source_url="https://careers.smartrecruiters.com/acme",
                platform_company_slug="acme",
                platform_job_id="job-ai-engineer",
                job_title_raw="Senior AI Engineer",
                job_title_normalized="AI Engineer",
                role_search_term="AI Engineer",
                role_group="AI Execution Role",
            ),
            _candidate(
                source="smartrecruiters",
                source_url="https://careers.smartrecruiters.com/acme",
                platform_company_slug="acme",
                platform_job_id="job-ai-product",
                job_title_raw="AI Product Manager",
                job_title_normalized="AI Product Manager",
                role_search_term="AI Product Manager",
                role_group="AI Product Role",
            ),
        ]
    )

    assert len(deduped) == 2


def test_dedupe_keeps_distinct_workable_jobs_with_same_board_url() -> None:
    deduped = dedupe_job_candidates(
        [
            _candidate(
                source="workable",
                source_url="https://apply.workable.com/acme",
                platform_company_slug="acme",
                platform_job_id="AIENG",
                job_title_raw="Senior AI Engineer",
                job_title_normalized="AI Engineer",
                role_search_term="AI Engineer",
                role_group="AI Execution Role",
            ),
            _candidate(
                source="workable",
                source_url="https://apply.workable.com/acme",
                platform_company_slug="acme",
                platform_job_id="AIPM",
                job_title_raw="AI Product Manager",
                job_title_normalized="AI Product Manager",
                role_search_term="AI Product Manager",
                role_group="AI Product Role",
            ),
        ]
    )

    assert len(deduped) == 2
