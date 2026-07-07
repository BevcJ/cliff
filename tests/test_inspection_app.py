from __future__ import annotations

from types import SimpleNamespace

from ai_hiring_radar import inspection_app
from ai_hiring_radar.storage_json import write_processed_jsonl


def _filters(**overrides):  # noqa: ANN001, ANN202 - compact test fixture helper.
    filters = {
        "workplace_modes": [],
        "ai_team_contexts": [],
        "delivery_contexts": [],
        "company_types": [],
        "company_sizes": [],
        "min_jobs": None,
        "max_jobs": None,
        "countries": [],
        "role_classifications": [],
        "sources": [],
        "ai_tech_forward_signals": [],
        "fit_statuses": [],
        "outreach_statuses": [],
        "needs_action": "Any",
        "has_contacts": "Any",
        "has_job_description_extracts": "Any",
        "has_company_enrichment": "Any",
        "search": "",
    }
    filters.update(overrides)
    return filters


def _record(**overrides):  # noqa: ANN001, ANN202 - compact test fixture helper.
    record = {
        "company": "Acme AI",
        "company_key": "acme ai",
        "countries": ["Netherlands"],
        "role_classification": "AI Execution Role",
        "sources": ["lever"],
        "workplace_modes": ["remote"],
        "ai_team_contexts": ["existing_ai_team"],
        "delivery_contexts": ["internal"],
        "company_type": "ai_native",
        "company_size": "101-500",
        "industry": "Software",
        "company_description": "Builds AI tooling.",
        "ai_tech_forward_signal": "strong",
        "ai_execution_titles": ["AI Engineer"],
        "ai_product_titles": [],
        "matched_search_terms": ["AI Engineer"],
        "ai_role_title_counts": [{"title": "Senior AI Engineer", "count": 1}],
        "has_contacts": True,
        "has_job_description_extracts": True,
        "has_company_enrichment": True,
        "fit_status": "unreviewed",
        "outreach_status": "not_started",
        "review_notes": "",
        "has_review_state": False,
        "job_count": 1,
        "job_description_extract_count": 1,
        "jobs": [
            {
                "job_title_raw": "Senior AI Engineer",
                "job_title_normalized": "AI Engineer",
                "platform": "lever",
                "source": "lever",
            }
        ],
    }
    record.update(overrides)
    return record


def test_collection_date_reads_script_argument() -> None:
    assert inspection_app._collection_date(["inspection_app.py", "--date", "2026-07-02"]) == (
        "2026-07-02"
    )


def test_latest_collection_date_returns_latest_company_or_artifact_file(tmp_path) -> None:
    write_processed_jsonl("companies_2026-07-01.jsonl", [_record()], data_dir=tmp_path)
    write_processed_jsonl("companies_2026-07-03.jsonl", [_record()], data_dir=tmp_path)
    write_processed_jsonl("companies_2026-07-02.jsonl", [_record()], data_dir=tmp_path)
    write_processed_jsonl(
        "inspection_companies_2026-07-04.jsonl", [_record()], data_dir=tmp_path
    )
    write_processed_jsonl("job_candidates_2026-07-04.jsonl", [_record()], data_dir=tmp_path)

    assert inspection_app._latest_collection_date(data_dir=tmp_path) == "2026-07-04"


def test_latest_collection_date_returns_none_without_company_files(tmp_path) -> None:
    assert inspection_app._latest_collection_date(data_dir=tmp_path) is None


def test_apply_filters_matches_required_optional_and_search_filters() -> None:
    records = [_record(), _record(company="Beta", workplace_modes=["onsite"])]

    filtered = inspection_app._apply_filters(
        records,
        _filters(
            workplace_modes=["remote"],
            ai_team_contexts=["existing_ai_team"],
            delivery_contexts=["internal"],
            company_types=["ai_native"],
            company_sizes=["101-500"],
            countries=["Netherlands"],
            role_classifications=["AI Execution Role"],
            sources=["lever"],
            ai_tech_forward_signals=["strong"],
            has_contacts="Yes",
            has_job_description_extracts="Yes",
            has_company_enrichment="Yes",
            search="tooling",
        ),
    )

    assert [record["company"] for record in filtered] == ["Acme AI"]


def test_apply_filters_supports_negative_boolean_filters() -> None:
    records = [
        _record(company="With contacts", has_contacts=True),
        _record(company="Without contacts", has_contacts=False),
    ]

    filtered = inspection_app._apply_filters(records, _filters(has_contacts="No"))

    assert [record["company"] for record in filtered] == ["Without contacts"]


def test_apply_filters_supports_missing_list_filter_values() -> None:
    records = [
        _record(company="With workplace", workplace_modes=["remote"]),
        _record(company="Missing workplace", workplace_modes=[]),
    ]

    filtered = inspection_app._apply_filters(
        records,
        _filters(workplace_modes=[inspection_app.MISSING_FILTER_OPTION]),
    )

    assert [record["company"] for record in filtered] == ["Missing workplace"]


def test_apply_filters_supports_missing_scalar_filter_values() -> None:
    records = [
        _record(company="With size", company_size="101-500"),
        _record(company="Missing size", company_size=None),
    ]

    filtered = inspection_app._apply_filters(
        records,
        _filters(company_sizes=[inspection_app.MISSING_FILTER_OPTION]),
    )

    assert [record["company"] for record in filtered] == ["Missing size"]


def test_apply_filters_supports_max_job_count_filter() -> None:
    records = [
        _record(company="Small pipeline", job_count=9),
        _record(company="Large pipeline", job_count=10),
    ]

    filtered = inspection_app._apply_filters(records, _filters(max_jobs=9))

    assert [record["company"] for record in filtered] == ["Small pipeline"]


def test_apply_filters_supports_min_job_count_filter() -> None:
    records = [
        _record(company="Small pipeline", job_count=2),
        _record(company="Large pipeline", job_count=10),
    ]

    filtered = inspection_app._apply_filters(records, _filters(min_jobs=3))

    assert [record["company"] for record in filtered] == ["Large pipeline"]


def test_apply_filters_supports_fit_status_filter() -> None:
    records = [
        _record(company="Unreviewed", fit_status="unreviewed"),
        _record(company="Best", fit_status="best_fit"),
    ]

    filtered = inspection_app._apply_filters(records, _filters(fit_statuses=["best_fit"]))

    assert [record["company"] for record in filtered] == ["Best"]


def test_apply_filters_supports_outreach_status_filter() -> None:
    records = [
        _record(company="Not started", outreach_status="not_started"),
        _record(company="Sent", outreach_status="message_sent"),
    ]

    filtered = inspection_app._apply_filters(
        records,
        _filters(outreach_statuses=["message_sent"]),
    )

    assert [record["company"] for record in filtered] == ["Sent"]


def test_apply_filters_supports_needs_action_filter() -> None:
    records = [
        _record(company="Best not started", fit_status="best_fit", outreach_status="not_started"),
        _record(
            company="Possible follow-up",
            fit_status="possible_fit",
            outreach_status="follow_up_needed",
        ),
        _record(
            company="Rejected follow-up",
            fit_status="not_interesting",
            outreach_status="follow_up_needed",
        ),
        _record(company="Best sent", fit_status="best_fit", outreach_status="message_sent"),
    ]

    filtered = inspection_app._apply_filters(records, _filters(needs_action="Yes"))

    assert [record["company"] for record in filtered] == [
        "Best not started",
        "Possible follow-up",
    ]


def test_apply_filters_supports_missing_source_filter_values() -> None:
    records = [
        _record(company="With source", sources=["lever"]),
        _record(company="Missing source", sources=[], jobs=[]),
    ]

    filtered = inspection_app._apply_filters(
        records,
        _filters(sources=[inspection_app.MISSING_FILTER_OPTION]),
    )

    assert [record["company"] for record in filtered] == ["Missing source"]


def test_filter_options_include_missing_when_records_are_sparse() -> None:
    records = [
        _record(company="With size", company_size="101-500"),
        _record(company="Missing size", company_size=None),
    ]

    assert inspection_app._company_size_options(records, include_missing=True) == [
        "101-500",
        inspection_app.MISSING_FILTER_OPTION,
    ]


def test_company_size_options_use_bucket_order_before_legacy_values() -> None:
    records = [
        _record(company="Large", company_size="501+"),
        _record(company="Legacy", company_size="51-200 employees"),
        _record(company="Small", company_size="0-50"),
        _record(company="Medium", company_size="51-100"),
    ]

    assert inspection_app._company_size_options(records) == [
        "0-50",
        "51-100",
        "501+",
        "51-200 employees",
    ]


def test_sort_records_orders_company_size_buckets() -> None:
    records = [
        _record(company="Large", company_size="501+"),
        _record(company="Small", company_size="0-50"),
        _record(company="Mid", company_size="101-500"),
    ]

    sorted_records = inspection_app._sort_records(
        records,
        "company_size",
        descending=False,
    )

    assert [record["company"] for record in sorted_records] == [
        "Small",
        "Mid",
        "Large",
    ]


def test_sort_records_defaults_to_jd_extracts_descending_with_company_tiebreaker() -> None:
    records = [
        _record(company="Beta", job_description_extract_count=1, job_count=10),
        _record(company="Acme", job_description_extract_count=3, job_count=1),
        _record(company="Able", job_description_extract_count=1, job_count=2),
    ]

    sorted_records = inspection_app._sort_records(
        records,
        inspection_app.SORT_FIELDS["JD Extracts"],
        descending=True,
    )

    assert [record["company"] for record in sorted_records] == ["Acme", "Able", "Beta"]


def test_sort_records_supports_jobs_ascending() -> None:
    records = [
        _record(company="Beta", job_count=10),
        _record(company="Acme", job_count=1),
    ]

    sorted_records = inspection_app._sort_records(records, "job_count", descending=False)

    assert [record["company"] for record in sorted_records] == ["Acme", "Beta"]


def test_shortlist_records_returns_suitable_companies_only() -> None:
    records = [
        _record(company="Best", fit_status="best_fit"),
        _record(company="Possible", fit_status="possible_fit"),
        _record(company="Rejected", fit_status="not_interesting"),
        _record(company="Unreviewed", fit_status="unreviewed"),
    ]

    shortlisted = inspection_app._shortlist_records(records)

    assert [record["company"] for record in shortlisted] == ["Best", "Possible"]


def test_outreach_records_excludes_not_started() -> None:
    records = [
        _record(company="Not started", fit_status="best_fit", outreach_status="not_started"),
        _record(company="Sent", fit_status="best_fit", outreach_status="message_sent"),
        _record(
            company="Follow-up",
            fit_status="possible_fit",
            outreach_status="follow_up_needed",
        ),
        _record(company="Rejected", fit_status="not_interesting", outreach_status="message_sent"),
    ]

    outreach = inspection_app._outreach_records(records)

    assert [record["company"] for record in outreach] == ["Sent", "Follow-up"]


def test_rejected_records_returns_not_interesting_only() -> None:
    records = [
        _record(company="Best", fit_status="best_fit"),
        _record(company="Rejected", fit_status="not_interesting"),
    ]

    rejected = inspection_app._rejected_records(records)

    assert [record["company"] for record in rejected] == ["Rejected"]


def test_company_table_column_order_hides_jd_extracts() -> None:
    column_order = inspection_app._company_table_column_order()

    assert "Jobs" in column_order
    assert "JD Extracts" not in column_order
    assert "Fit Status" in column_order
    assert "Outreach Status" in column_order


def test_company_table_row_includes_review_state_columns() -> None:
    row = inspection_app._company_table_row(
        _record(fit_status="best_fit", outreach_status="message_sent")
    )

    assert row["Fit Status"] == "best_fit"
    assert row["Outreach Status"] == "message_sent"


def test_selected_record_from_event_uses_clicked_row() -> None:
    records = [_record(company="Acme"), _record(company="Beta")]
    event = SimpleNamespace(selection=SimpleNamespace(rows=[1]))

    selected = inspection_app._selected_record_from_event(records, event)

    assert selected is not None
    assert selected["company"] == "Beta"


def test_selected_record_from_event_returns_none_without_selection() -> None:
    records = [_record(company="Acme"), _record(company="Beta")]
    event = SimpleNamespace(selection=SimpleNamespace(rows=[]))

    selected = inspection_app._selected_record_from_event(records, event)

    assert selected is None


def test_selected_record_from_event_returns_none_when_selection_is_out_of_range() -> None:
    records = [_record(company="Acme")]
    event = SimpleNamespace(selection=SimpleNamespace(rows=[9]))

    selected = inspection_app._selected_record_from_event(records, event)

    assert selected is None


def test_load_review_state_for_records_queries_unique_company_keys(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_load_review_state(
        company_keys: list[str],
        *,
        database_url: str,
    ) -> dict[str, dict[str, object]]:
        calls.append({"company_keys": company_keys, "database_url": database_url})
        return {"acme ai": {"fit_status": "best_fit"}}

    monkeypatch.setattr(inspection_app, "load_review_state", fake_load_review_state)

    loaded = inspection_app._load_review_state_for_records(
        [_record(company_key="acme ai"), _record(company_key="acme ai"), _record(company_key="beta ai")],
        database_url="postgres://test",
    )

    assert loaded == {"acme ai": {"fit_status": "best_fit"}}
    assert calls == [
        {"company_keys": ["acme ai", "beta ai"], "database_url": "postgres://test"}
    ]


def test_job_table_row_excludes_normalized_title() -> None:
    row = inspection_app._job_table_row(
        {
            "job_title_raw": "Senior AI Engineer",
            "job_title_normalized": "AI Engineer",
            "role_group": "AI Execution Role",
        }
    )

    assert row["Title"] == "Senior AI Engineer"
    assert "Normalized Title" not in row


def test_job_description_html_keeps_supported_html_and_removes_unsafe_blocks() -> None:
    html = inspection_app._job_description_html(
        "<h2>About</h2><p>Build AI.</p><script>alert('x')</script><style>body{}</style>"
    )

    assert '<div class="job-description-card">' in html
    assert "<h2>About</h2>" in html
    assert "<p>Build AI.</p>" in html
    assert "<script" not in html
    assert "<style" not in html


def test_job_description_html_escapes_plain_text() -> None:
    html = inspection_app._job_description_html("Build 5 < 10 AI & automation")

    assert "Build 5 &lt; 10 AI &amp; automation" in html


def test_job_description_html_returns_empty_for_missing_description() -> None:
    assert inspection_app._job_description_html(None) == ""


def test_url_link_html_opens_http_urls_in_new_tab() -> None:
    html = inspection_app._url_link_html("https://example.com/jobs?a=1&b=2")

    assert 'href="https://example.com/jobs?a=1&amp;b=2"' in html
    assert 'target="_blank"' in html
    assert 'rel="noopener noreferrer"' in html
    assert "example.com/jobs?a=1&amp;b=2" in html


def test_url_link_html_escapes_non_http_values_without_linking() -> None:
    html = inspection_app._url_link_html('javascript:alert("x")')

    assert html == "javascript:alert(&quot;x&quot;)"
    assert "<a " not in html


def test_render_job_description_calls_streamlit_html_without_extra_kwargs(monkeypatch) -> None:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_html(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))

    monkeypatch.setattr(inspection_app.st, "html", fake_html)

    inspection_app._render_job_description({"description": "<p>Build AI.</p>"})

    assert len(calls) == 1
    assert "<p>Build AI.</p>" in str(calls[0][0][0])
    assert calls[0][1] == {}
