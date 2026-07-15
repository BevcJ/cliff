from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

from ai_hiring_radar import inspection_app
from ai_hiring_radar.inspection import (
    CompanyInspectionDataset,
    InspectionInputPaths,
    InspectionLoadCounts,
)
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
        "review_communication_history": "",
        "last_outreach_date": None,
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


def _dataset(**overrides):  # noqa: ANN001, ANN202 - compact test fixture helper.
    dataset = {
        "collection_date": "2026-07-02",
        "records": [_record()],
        "paths": InspectionInputPaths(
            companies_path=Path("data/processed/companies_2026-07-02.jsonl"),
            candidates_path=Path("data/processed/job_candidates_2026-07-02.jsonl"),
            job_description_extracts_path=Path(
                "data/processed/job_description_extracts_2026-07-02.jsonl"
            ),
            company_enrichment_extracts_path=Path(
                "data/processed/company_enrichment_extracts_2026-07-02.jsonl"
            ),
        ),
        "missing_optional_files": [],
        "counts": InspectionLoadCounts(
            companies_loaded=1,
            candidates_loaded=1,
            job_description_extracts_loaded=1,
            company_enrichments_loaded=1,
        ),
    }
    dataset.update(overrides)
    return CompanyInspectionDataset(**dataset)


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


def test_load_local_env_reads_env_file_without_overriding_existing_env(
    tmp_path,
    monkeypatch,
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "AI_HIRING_RADAR_DATABASE_URL=postgres://from-file\n"
        "EXISTING_VALUE=from-file\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("AI_HIRING_RADAR_DATABASE_URL", raising=False)
    monkeypatch.setenv("EXISTING_VALUE", "from-env")

    inspection_app._load_local_env(env_path)

    assert inspection_app.os.environ["AI_HIRING_RADAR_DATABASE_URL"] == "postgres://from-file"
    assert inspection_app.os.environ["EXISTING_VALUE"] == "from-env"


def test_inspection_database_url_loads_local_env_before_env_fallback(monkeypatch) -> None:
    monkeypatch.delenv("AI_HIRING_RADAR_DATABASE_URL", raising=False)
    monkeypatch.setattr(inspection_app, "_inspection_database_url_from_secrets", lambda: None)

    def fake_load_local_env() -> None:
        monkeypatch.setenv("AI_HIRING_RADAR_DATABASE_URL", "postgres://from-local-env")

    monkeypatch.setattr(inspection_app, "_load_local_env", fake_load_local_env)

    assert inspection_app._inspection_database_url() == "postgres://from-local-env"
    assert inspection_app._review_state_database_url() == "postgres://from-local-env"


def test_load_dataset_from_sources_uses_database_when_configured(monkeypatch) -> None:
    database_dataset = _dataset(data_source="database", synced_at="2026-07-02T10:30:00Z")

    monkeypatch.setattr(
        inspection_app,
        "_load_dataset_from_database",
        lambda collection_date, database_url: database_dataset,
    )
    monkeypatch.setattr(
        inspection_app,
        "_load_dataset_from_jsonl",
        lambda collection_date: (_ for _ in ()).throw(AssertionError("JSONL fallback used")),
    )

    dataset = inspection_app._load_dataset_from_sources(
        "2026-07-02",
        inspection_database_url="postgres://test",
    )

    assert dataset is database_dataset
    assert dataset.data_source == "database"


def test_load_dataset_from_sources_falls_back_when_database_unsynced(monkeypatch) -> None:
    monkeypatch.setattr(
        inspection_app,
        "_load_dataset_from_database",
        lambda collection_date, database_url: None,
    )
    monkeypatch.setattr(
        inspection_app,
        "_load_dataset_from_jsonl",
        lambda collection_date: _dataset(data_source="jsonl"),
    )

    dataset = inspection_app._load_dataset_from_sources(
        "2026-07-02",
        inspection_database_url="postgres://test",
    )

    assert dataset.data_source == "jsonl"
    assert "no snapshots" in str(dataset.fallback_warning)


def test_load_dataset_from_sources_falls_back_when_database_raises(monkeypatch) -> None:
    def fail_database(collection_date: str, database_url: str) -> None:
        raise RuntimeError("connection failed")

    monkeypatch.setattr(inspection_app, "_load_dataset_from_database", fail_database)
    monkeypatch.setattr(
        inspection_app,
        "_load_dataset_from_jsonl",
        lambda collection_date: _dataset(data_source="jsonl"),
    )

    dataset = inspection_app._load_dataset_from_sources(
        "2026-07-02",
        inspection_database_url="postgres://test",
    )

    assert dataset.data_source == "jsonl"
    assert "connection failed" in str(dataset.fallback_warning)


def test_load_dataset_from_sources_preserves_database_error_when_jsonl_missing(
    monkeypatch,
) -> None:
    def fail_database(collection_date: str, database_url: str) -> None:
        raise RuntimeError("connection failed")

    def fail_jsonl(collection_date: str) -> None:
        raise FileNotFoundError("missing companies file")

    monkeypatch.setattr(inspection_app, "_load_dataset_from_database", fail_database)
    monkeypatch.setattr(inspection_app, "_load_dataset_from_jsonl", fail_jsonl)

    try:
        inspection_app._load_dataset_from_sources(
            "2026-07-02",
            inspection_database_url="postgres://test",
        )
    except FileNotFoundError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")

    assert "connection failed" in message
    assert "missing companies file" in message


def test_latest_collection_date_includes_database_dates(tmp_path, monkeypatch) -> None:
    write_processed_jsonl("companies_2026-07-01.jsonl", [_record()], data_dir=tmp_path)
    monkeypatch.setattr(
        inspection_app,
        "list_synced_collection_dates",
        lambda *, database_url: ["2026-07-03"],
    )

    assert (
        inspection_app._latest_collection_date(
            data_dir=tmp_path,
            database_url="postgres://test",
        )
        == "2026-07-03"
    )


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


def test_shortlist_records_returns_suitable_not_started_companies_only() -> None:
    records = [
        _record(company="Best", fit_status="best_fit"),
        _record(company="Possible", fit_status="possible_fit"),
        _record(company="Sent", fit_status="best_fit", outreach_status="message_sent"),
        _record(
            company="Conversation",
            fit_status="possible_fit",
            outreach_status="active_conversation",
        ),
        _record(company="Closed", fit_status="best_fit", outreach_status="closed"),
        _record(
            company="Lost",
            fit_status="possible_fit",
            outreach_status="lost_no_response",
        ),
        _record(company="Rejected", fit_status="not_interesting"),
        _record(company="Unreviewed", fit_status="unreviewed"),
    ]

    shortlisted = inspection_app._shortlist_records(records)

    assert [record["company"] for record in shortlisted] == ["Best", "Possible"]


def test_outreach_records_returns_only_active_suitable_leads() -> None:
    records = [
        _record(company="Not started", fit_status="best_fit", outreach_status="not_started"),
        _record(company="Sent", fit_status="best_fit", outreach_status="message_sent"),
        _record(
            company="Follow-up",
            fit_status="possible_fit",
            outreach_status="follow_up_sent",
        ),
        _record(
            company="Conversation",
            fit_status="best_fit",
            outreach_status="active_conversation",
        ),
        _record(company="Closed", fit_status="best_fit", outreach_status="closed"),
        _record(
            company="Lost",
            fit_status="possible_fit",
            outreach_status="lost_client_rejection",
        ),
        _record(company="Rejected", fit_status="not_interesting", outreach_status="message_sent"),
    ]

    outreach = inspection_app._outreach_records(records)

    assert [record["company"] for record in outreach] == [
        "Sent",
        "Follow-up",
        "Conversation",
    ]


def test_closed_records_returns_closed_regardless_of_fit_status() -> None:
    records = [
        _record(company="Best", fit_status="best_fit", outreach_status="message_sent"),
        _record(company="Closed", fit_status="best_fit", outreach_status="closed"),
        _record(
            company="Closed rejected fit",
            fit_status="not_interesting",
            outreach_status="closed",
        ),
    ]

    closed = inspection_app._closed_records(records)

    assert [record["company"] for record in closed] == ["Closed", "Closed rejected fit"]


def test_rejected_records_includes_fit_rejections_and_outreach_losses() -> None:
    records = [
        _record(company="Rejected", fit_status="not_interesting"),
        _record(
            company="Client rejection",
            fit_status="best_fit",
            outreach_status="lost_client_rejection",
        ),
        _record(
            company="No response",
            fit_status="possible_fit",
            outreach_status="lost_no_response",
        ),
        _record(
            company="Closed wins",
            fit_status="not_interesting",
            outreach_status="closed",
        ),
    ]

    rejected = inspection_app._rejected_records(records)

    assert [record["company"] for record in rejected] == [
        "Rejected",
        "Client rejection",
        "No response",
    ]


def test_workflow_records_routes_to_selected_workflow() -> None:
    records = [
        _record(company="Unreviewed", fit_status="unreviewed", outreach_status="not_started"),
        _record(company="Best", fit_status="best_fit", outreach_status="not_started"),
        _record(company="Sent", fit_status="possible_fit", outreach_status="message_sent"),
        _record(company="Closed", fit_status="best_fit", outreach_status="closed"),
        _record(company="Rejected", fit_status="not_interesting"),
    ]

    assert [record["company"] for record in inspection_app._workflow_records(records, "Inspect")] == [
        "Unreviewed"
    ]
    assert [record["company"] for record in inspection_app._workflow_records(records, "Shortlist")] == [
        "Best"
    ]
    assert [record["company"] for record in inspection_app._workflow_records(records, "Outreach")] == [
        "Sent"
    ]
    assert [record["company"] for record in inspection_app._workflow_records(records, "Closed")] == [
        "Closed"
    ]
    assert [record["company"] for record in inspection_app._workflow_records(records, "Rejected")] == [
        "Rejected"
    ]


def test_workflow_records_moves_company_between_exclusive_stages() -> None:
    unreviewed = _record(
        company="Acme",
        fit_status="unreviewed",
        outreach_status="not_started",
    )
    shortlisted = {**unreviewed, "fit_status": "best_fit"}
    outreach = {**shortlisted, "outreach_status": "message_sent"}

    assert inspection_app._workflow_records([unreviewed], "Inspect") == [unreviewed]
    assert inspection_app._workflow_records([shortlisted], "Inspect") == []
    assert inspection_app._workflow_records([shortlisted], "Shortlist") == [shortlisted]
    assert inspection_app._workflow_records([outreach], "Shortlist") == []
    assert inspection_app._workflow_records([outreach], "Outreach") == [outreach]


def test_workflow_records_assigns_each_company_to_one_workflow_stage() -> None:
    records = [
        _record(company="Inspect", fit_status="unreviewed"),
        _record(company="Shortlist", fit_status="best_fit"),
        _record(company="Outreach", fit_status="possible_fit", outreach_status="follow_up_sent"),
        _record(company="Closed", fit_status="not_interesting", outreach_status="closed"),
        _record(company="Rejected fit", fit_status="not_interesting"),
        _record(company="Rejected lost", fit_status="best_fit", outreach_status="lost_no_response"),
    ]

    memberships = {
        record["company"]: [
            workflow_view
            for workflow_view in inspection_app.WORKFLOW_VIEW_OPTIONS
            if record in inspection_app._workflow_records(records, workflow_view)
        ]
        for record in records
    }

    assert memberships == {
        "Inspect": ["Inspect"],
        "Shortlist": ["Shortlist"],
        "Outreach": ["Outreach"],
        "Closed": ["Closed"],
        "Rejected fit": ["Rejected"],
        "Rejected lost": ["Rejected"],
    }


def test_company_table_column_order_hides_jd_extracts() -> None:
    column_order = inspection_app._company_table_column_order()

    assert "Jobs" in column_order
    assert "JD Extracts" not in column_order
    assert "Fit Status" in column_order
    assert "Outreach Status" in column_order
    assert column_order[:2] == ("Follow-up", "Company")
    assert "Last Outreach" in column_order


def test_company_table_row_includes_review_state_columns() -> None:
    row = inspection_app._company_table_row(
        _record(
            fit_status="best_fit",
            outreach_status="message_sent",
            last_outreach_date="2026-07-07",
        ),
        today=date(2026, 7, 10),
    )

    assert row["Fit Status"] == "best_fit"
    assert row["Outreach Status"] == "message_sent"
    assert row["Last Outreach"] == "2026-07-07"
    assert row["Follow-up"] == "🟢 Fresh"


def test_follow_up_indicator_uses_three_and_five_day_boundaries() -> None:
    today = date(2026, 7, 10)

    assert inspection_app._follow_up_indicator(
        _record(outreach_status="message_sent", last_outreach_date="2026-07-07"),
        today=today,
    ) == "🟢 Fresh"
    assert inspection_app._follow_up_indicator(
        _record(outreach_status="message_sent", last_outreach_date="2026-07-06"),
        today=today,
    ) == "🟡 Due soon"
    assert inspection_app._follow_up_indicator(
        _record(outreach_status="follow_up_sent", last_outreach_date="2026-07-05"),
        today=today,
    ) == "🟡 Due soon"
    assert inspection_app._follow_up_indicator(
        _record(outreach_status="follow_up_sent", last_outreach_date="2026-07-04"),
        today=today,
    ) == "🔴 Follow up"


def test_follow_up_indicator_flags_missing_dates_and_suppresses_inactive_statuses() -> None:
    today = date(2026, 7, 10)

    assert inspection_app._follow_up_indicator(
        _record(outreach_status="message_sent", last_outreach_date=None),
        today=today,
    ) == "🔴 Date missing"
    for outreach_status in (
        "not_started",
        "active_conversation",
        "closed",
        "lost_client_rejection",
        "lost_no_response",
    ):
        assert inspection_app._follow_up_indicator(
            _record(
                outreach_status=outreach_status,
                last_outreach_date="2026-07-01",
            ),
            today=today,
        ) == ""


def _column_def(options: dict[str, object], field: str) -> dict[str, object]:
    column_defs = options["columnDefs"]
    assert isinstance(column_defs, list)
    for column in column_defs:
        if isinstance(column, dict) and column.get("field") == field:
            return column
    raise AssertionError(f"Missing column definition for {field}")


def test_company_grid_row_includes_only_hidden_stable_keys() -> None:
    row = inspection_app._company_grid_row(
        _record(
            company="Acme",
            company_key="acme ai",
            review_notes="General note",
            review_communication_history="Sent email",
        ),
        0,
    )

    assert row["Grid Row Key"] == "acme ai"
    assert row["Company Key"] == "acme ai"
    assert "Review Notes" not in row
    assert "Communication History" not in row


def test_company_grid_options_makes_review_columns_editable_only_when_enabled() -> None:
    rows = inspection_app._company_grid_rows([_record()])

    editable_options = inspection_app._company_grid_options(rows, editable=True)
    readonly_options = inspection_app._company_grid_options(rows, editable=False)

    assert _column_def(editable_options, "Fit Status")["editable"] is True
    assert _column_def(editable_options, "Outreach Status")["editable"] is True
    assert _column_def(editable_options, "Outreach Status")["cellEditorParams"] == {
        "values": list(inspection_app.OUTREACH_STATUS_OPTIONS)
    }
    assert _column_def(editable_options, "Company").get("editable") is not True
    assert _column_def(editable_options, "Follow-up")["pinned"] == "left"
    assert _column_def(editable_options, "Company")["pinned"] == "left"
    last_outreach_column = _column_def(editable_options, "Last Outreach")
    assert last_outreach_column["editable"] is True
    assert last_outreach_column["cellDataType"] == "dateString"
    assert last_outreach_column["cellEditor"] == "agDateStringCellEditor"
    assert last_outreach_column["cellEditorParams"] == {"max": date.today().isoformat()}
    assert _column_def(readonly_options, "Fit Status")["editable"] is False
    assert _column_def(readonly_options, "Outreach Status")["editable"] is False
    assert _column_def(readonly_options, "Last Outreach")["editable"] is False
    assert _column_def(editable_options, "Grid Row Key")["hide"] is True


def test_render_company_table_uses_server_wins_sync(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_aggrid(dataframe, **kwargs):  # noqa: ANN001, ANN202
        captured.update(kwargs)
        return SimpleNamespace(data=dataframe.to_dict("records"), selected_rows=[])

    monkeypatch.setattr(inspection_app, "AgGrid", fake_aggrid)
    monkeypatch.setattr(inspection_app.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setitem(inspection_app.st.session_state, "selected_company_key", "")

    selected = inspection_app._render_company_table(
        [_record()],
        review_state_status=inspection_app.ReviewStateBackendStatus(database_url=None),
        reviewer_name="Jakob",
        collection_date="2026-07-07",
    )

    assert selected is not None
    assert captured["server_sync_strategy"] == "server_wins"


def test_table_review_changes_from_grid_data_detects_changed_status_values() -> None:
    records = [
        _record(company="Acme", company_key="acme ai"),
        _record(
            company="Beta",
            company_key="beta ai",
            fit_status="best_fit",
            outreach_status="message_sent",
            review_notes="Existing note.",
        ),
    ]
    grid_rows = inspection_app._company_grid_rows(records)
    grid_rows[0]["Fit Status"] = "possible_fit"
    grid_rows[1]["Outreach Status"] = "follow_up_sent"

    changes = inspection_app._table_review_changes_from_grid_data(records, grid_rows)

    assert changes == [
        {
            "grid_row_key": "acme ai",
            "company_key": "acme ai",
            "company": "Acme",
            "fit_status": "possible_fit",
            "outreach_status": "not_started",
            "last_outreach_date": None,
            "status_changed": True,
            "last_outreach_date_changed": False,
        },
        {
            "grid_row_key": "beta ai",
            "company_key": "beta ai",
            "company": "Beta",
            "fit_status": "best_fit",
            "outreach_status": "follow_up_sent",
            "last_outreach_date": None,
            "status_changed": True,
            "last_outreach_date_changed": False,
        },
    ]


def test_table_review_changes_from_grid_data_detects_last_outreach_set_and_clear() -> None:
    records = [
        _record(company="Acme", company_key="acme ai"),
        _record(
            company="Beta",
            company_key="beta ai",
            last_outreach_date="2026-07-07",
        ),
    ]
    grid_rows = inspection_app._company_grid_rows(records)
    grid_rows[0]["Last Outreach"] = "2026-07-06"
    grid_rows[1]["Last Outreach"] = ""

    changes = inspection_app._table_review_changes_from_grid_data(records, grid_rows)

    assert changes == [
        {
            "grid_row_key": "acme ai",
            "company_key": "acme ai",
            "company": "Acme",
            "fit_status": "unreviewed",
            "outreach_status": "not_started",
            "last_outreach_date": date(2026, 7, 6),
            "status_changed": False,
            "last_outreach_date_changed": True,
        },
        {
            "grid_row_key": "beta ai",
            "company_key": "beta ai",
            "company": "Beta",
            "fit_status": "unreviewed",
            "outreach_status": "not_started",
            "last_outreach_date": None,
            "status_changed": False,
            "last_outreach_date_changed": True,
        },
    ]


def test_table_review_changes_from_grid_data_ignores_unchanged_and_missing_keys() -> None:
    records = [_record(company="Acme", fit_status="best_fit")]
    grid_rows = inspection_app._company_grid_rows(records)
    grid_rows[0]["Company"] = "Changed in browser"

    assert inspection_app._table_review_changes_from_grid_data(records, grid_rows) == []

    missing_key_records = [_record(company="No Key", company_key="")]
    missing_key_rows = inspection_app._company_grid_rows(missing_key_records)
    missing_key_rows[0]["Fit Status"] = "possible_fit"

    assert inspection_app._table_review_changes_from_grid_data(missing_key_records, missing_key_rows) == []


def test_save_table_review_changes_calls_status_and_date_upserts(monkeypatch) -> None:
    status_calls: list[dict[str, object]] = []
    date_calls: list[dict[str, object]] = []

    def fake_status_upsert(payload: dict[str, object], *, database_url: str) -> dict[str, object]:
        status_calls.append({"payload": payload, "database_url": database_url})
        return payload

    def fake_date_upsert(payload: dict[str, object], *, database_url: str) -> dict[str, object]:
        date_calls.append({"payload": payload, "database_url": database_url})
        return payload

    monkeypatch.setattr(inspection_app, "upsert_review_statuses", fake_status_upsert)
    monkeypatch.setattr(inspection_app, "upsert_last_outreach_date", fake_date_upsert)

    inspection_app._save_table_review_changes(
        [
            {
                "company_key": "acme ai",
                "company": "Acme AI",
                "fit_status": "best_fit",
                "outreach_status": "message_sent",
                "last_outreach_date": date(2026, 7, 6),
                "status_changed": True,
                "last_outreach_date_changed": True,
            }
        ],
        database_url="postgres://test",
        reviewer_name="Jakob",
        collection_date="2026-07-07",
    )

    assert status_calls[0]["database_url"] == "postgres://test"
    payload = status_calls[0]["payload"]
    assert isinstance(payload, dict)
    assert payload["company_key"] == "acme ai"
    assert payload["fit_status"] == "best_fit"
    assert payload["outreach_status"] == "message_sent"
    assert payload["last_seen_collection_date"] == "2026-07-07"
    assert payload["last_updated_by"] == "Jakob"
    assert "notes" not in payload
    assert "communication_history" not in payload
    assert "last_outreach_date" not in payload
    date_payload = date_calls[0]["payload"]
    assert isinstance(date_payload, dict)
    assert date_payload["company_key"] == "acme ai"
    assert date_payload["last_outreach_date"] == date(2026, 7, 6)
    assert "fit_status" not in date_payload
    assert "outreach_status" not in date_payload


def test_render_review_form_saves_general_notes_and_communication_history(
    monkeypatch,
) -> None:
    text_areas: list[dict[str, object]] = []
    saved: list[dict[str, object]] = []

    class FakeForm:
        def __enter__(self) -> FakeForm:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    class FakeStreamlit:
        def __init__(self) -> None:
            self.session_state: dict[str, object] = {}
            self.rerun_called = False

        def markdown(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            return None

        def form(self, *args, **kwargs) -> FakeForm:  # noqa: ANN002, ANN003
            return FakeForm()

        def text_area(self, label, *, value, disabled, **kwargs):  # noqa: ANN001, ANN202
            text_areas.append({"label": label, "value": value, "disabled": disabled})
            return value

        def form_submit_button(self, *args, **kwargs) -> bool:  # noqa: ANN002, ANN003
            return True

        def error(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            raise AssertionError(args)

        def rerun(self) -> None:
            self.rerun_called = True

    fake_st = FakeStreamlit()
    monkeypatch.setattr(inspection_app, "st", fake_st)
    monkeypatch.setattr(
        inspection_app,
        "upsert_review_notes",
        lambda payload, *, database_url: saved.append(
            {"payload": payload, "database_url": database_url}
        ),
    )

    inspection_app._render_review_form(
        _record(
            fit_status="best_fit",
            outreach_status="message_sent",
            review_notes="Strong signal.",
            review_communication_history="Message sent to CTO.",
            last_outreach_date="2026-07-06",
        ),
        review_state_status=inspection_app.ReviewStateBackendStatus(
            database_url="postgres://test"
        ),
        reviewer_name="Jakob",
        collection_date="2026-07-07",
        scope="inspect",
    )

    assert text_areas == [
        {"label": "General Notes", "value": "Strong signal.", "disabled": False},
        {
            "label": "Communication History",
            "value": "Message sent to CTO.",
            "disabled": False,
        },
    ]
    assert saved[0]["database_url"] == "postgres://test"
    payload = saved[0]["payload"]
    assert isinstance(payload, dict)
    assert payload["notes"] == "Strong signal."
    assert payload["communication_history"] == "Message sent to CTO."
    assert "fit_status" not in payload
    assert "outreach_status" not in payload
    assert "last_outreach_date" not in payload
    assert fake_st.rerun_called is True


def test_selected_record_from_grid_result_uses_clicked_row(monkeypatch) -> None:
    records = [
        _record(company="Acme", company_key="acme ai"),
        _record(company="Beta", company_key="beta ai"),
    ]
    monkeypatch.setitem(inspection_app.st.session_state, "selected_company_key", "")
    result = SimpleNamespace(selected_rows=[{"Grid Row Key": "beta ai"}])

    selected = inspection_app._selected_record_from_grid_result(records, result)

    assert selected == records[1]
    assert inspection_app.st.session_state["selected_company_key"] == "beta ai"


def test_selected_record_from_grid_result_falls_back_to_persisted_selection(monkeypatch) -> None:
    records = [_record(company="Acme", company_key="acme ai"), _record(company="Beta", company_key="beta ai")]
    monkeypatch.setitem(inspection_app.st.session_state, "selected_company_key", "beta ai")
    result = SimpleNamespace(selected_rows=[])

    selected = inspection_app._selected_record_from_grid_result(
        records=records,
        grid_result=result,
    )

    assert selected == records[1]


def test_selected_record_from_grid_result_defaults_to_first_visible_row(monkeypatch) -> None:
    records = [_record(company="Acme", company_key="acme ai"), _record(company="Beta", company_key="beta ai")]
    monkeypatch.setitem(inspection_app.st.session_state, "selected_company_key", "missing")
    result = SimpleNamespace(selected_rows=[])

    selected = inspection_app._selected_record_from_grid_result(records, result)

    assert selected == records[0]


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
