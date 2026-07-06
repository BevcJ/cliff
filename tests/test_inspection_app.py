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
        "countries": [],
        "role_classifications": [],
        "sources": [],
        "ai_tech_forward_signals": [],
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


def test_latest_collection_date_returns_latest_companies_file(tmp_path) -> None:
    write_processed_jsonl("companies_2026-07-01.jsonl", [_record()], data_dir=tmp_path)
    write_processed_jsonl("companies_2026-07-03.jsonl", [_record()], data_dir=tmp_path)
    write_processed_jsonl("companies_2026-07-02.jsonl", [_record()], data_dir=tmp_path)
    write_processed_jsonl("job_candidates_2026-07-04.jsonl", [_record()], data_dir=tmp_path)

    assert inspection_app._latest_collection_date(data_dir=tmp_path) == "2026-07-03"


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


def test_selected_record_from_event_uses_clicked_row() -> None:
    records = [_record(company="Acme"), _record(company="Beta")]
    event = SimpleNamespace(selection=SimpleNamespace(rows=[1]))

    selected = inspection_app._selected_record_from_event(records, event)

    assert selected is not None
    assert selected["company"] == "Beta"


def test_selected_record_from_event_defaults_to_first_record() -> None:
    records = [_record(company="Acme"), _record(company="Beta")]
    event = SimpleNamespace(selection=SimpleNamespace(rows=[]))

    selected = inspection_app._selected_record_from_event(records, event)

    assert selected is not None
    assert selected["company"] == "Acme"


def test_selected_record_from_event_falls_back_when_selection_is_out_of_range() -> None:
    records = [_record(company="Acme")]
    event = SimpleNamespace(selection=SimpleNamespace(rows=[9]))

    selected = inspection_app._selected_record_from_event(records, event)

    assert selected is not None
    assert selected["company"] == "Acme"
