from __future__ import annotations

import argparse
from html import escape
import re
import os
import sys
from pathlib import Path
from typing import Any

import streamlit as st

from ai_hiring_radar.inspection import CompanyInspectionDataset, load_company_inspection_data
from ai_hiring_radar.storage_json import DEFAULT_DATA_DIR, processed_dir


PARETO_LOGO_URL = "https://www.pareto.si/wp-content/uploads/2023/03/logo_90.png"
COMPANIES_FILENAME_PATTERN = re.compile(r"companies_(\d{4}-\d{2}-\d{2})\.jsonl")
INSPECTION_ARTIFACT_FILENAME_PATTERN = re.compile(
    r"inspection_companies_(\d{4}-\d{2}-\d{2})\.jsonl"
)
HTML_TAG_PATTERN = re.compile(r"</?[a-zA-Z][^>]*>")
UNSAFE_HTML_TAG_PATTERN = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1>",
    flags=re.IGNORECASE | re.DOTALL,
)
WORKPLACE_MODE_OPTIONS = ["remote", "hybrid", "onsite"]
AI_TEAM_CONTEXT_OPTIONS = ["first_ai_person", "existing_ai_team"]
DELIVERY_CONTEXT_OPTIONS = ["internal", "external_clients", "mixed"]
COMPANY_TYPE_OPTIONS = [
    "product_company",
    "agency_consulting",
    "traditional_company",
    "ai_native",
    "other",
]
COMPANY_SIZE_OPTIONS = ["0-50", "51-100", "101-500", "501+"]
COMPANY_SIZE_ORDER = {value: index for index, value in enumerate(COMPANY_SIZE_OPTIONS)}
BOOLEAN_FILTER_OPTIONS = ["Any", "Yes", "No"]
MISSING_FILTER_OPTION = "(missing)"
SORT_FIELDS = {
    "JD Extracts": "job_description_extract_count",
    "Jobs": "job_count",
    "Company": "company",
    "Company Type": "company_type",
    "Company Size": "company_size",
    "AI Signal": "ai_tech_forward_signal",
    "Countries": "countries",
    "Sources": "sources",
}
FILTER_DEFAULTS = {
    "filter_workplace_modes": [],
    "filter_ai_team_contexts": [],
    "filter_delivery_contexts": [],
    "filter_company_types": [],
    "filter_company_sizes": [],
    "filter_countries": [],
    "filter_role_classifications": [],
    "filter_sources": [],
    "filter_ai_tech_forward_signals": [],
    "filter_has_contacts": "Any",
    "filter_has_job_description_extracts": "Any",
    "filter_has_company_enrichment": "Any",
    "filter_search": "",
}


def main() -> None:
    st.set_page_config(
        page_title="Company Inspection",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _apply_pareto_theme()
    _render_header()

    collection_date = _collection_date()
    if collection_date is None:
        st.error(
            "Pass a collection date with --date YYYY-MM-DD, use ?date=YYYY-MM-DD, "
            "or add data/processed/companies_YYYY-MM-DD.jsonl or "
            "data/processed/inspection_companies_YYYY-MM-DD.jsonl."
        )
        st.stop()
        return

    try:
        dataset = _load_dataset(collection_date)
    except FileNotFoundError as exc:
        st.error(str(exc))
        st.stop()
        return
    except ValueError as exc:
        st.error(f"Invalid date: {exc}")
        st.stop()
        return

    _render_missing_file_warnings(dataset)
    filters = _sidebar_filters(dataset.records)
    filtered_records = _apply_filters(dataset.records, filters)

    _render_summary(dataset, filtered_company_count=len(filtered_records))
    sort_field, descending = _sort_controls()
    sorted_records = _sort_records(filtered_records, sort_field, descending=descending)
    selected_record = _render_company_table(sorted_records)
    _render_company_detail(selected_record)


@st.cache_data(show_spinner="Loading processed inspection data")
def _load_dataset(collection_date: str) -> CompanyInspectionDataset:
    return load_company_inspection_data(collection_date)


def _apply_pareto_theme() -> None:
    st.markdown(
        """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Nunito+Sans:wght@400;700;800;900&display=swap');

            :root {
                --pareto-blue: #045fa0;
                --pareto-pink: #fb435f;
                --pareto-orange: #fa6e3d;
                --pareto-purple: #6a53a8;
                --pareto-ink: #172033;
                --pareto-muted: #657084;
                --pareto-bg: #f9fbfc;
                --pareto-card: #ffffff;
                --pareto-border: #e8eef4;
            }

            html, body, [class*="css"] {
                font-family: 'Nunito Sans', sans-serif;
            }

            .stApp {
                background:
                    radial-gradient(circle at 92% 3%, rgba(106, 83, 168, 0.08), transparent 24rem),
                    radial-gradient(circle at 8% 0%, rgba(251, 67, 95, 0.08), transparent 22rem),
                    var(--pareto-bg);
                color: var(--pareto-ink);
            }

            header[data-testid="stHeader"] {
                display: none;
            }

            #MainMenu, footer, div[data-testid="stToolbar"] {
                visibility: hidden;
                height: 0;
            }

            .block-container {
                max-width: 100% !important;
                padding-top: 0.35rem;
                padding-right: clamp(0.75rem, 1.4vw, 1.4rem);
                padding-bottom: 2rem;
                padding-left: clamp(0.75rem, 1.4vw, 1.4rem);
            }

            .pareto-header {
                display: flex;
                align-items: center;
                gap: 0.5rem;
                min-width: 0;
                padding: 0.38rem 0.62rem;
                margin-bottom: 0.45rem;
                border: 1px solid var(--pareto-border);
                border-radius: 12px;
                background: rgba(255, 255, 255, 0.94);
                box-shadow: 0 6px 16px rgba(4, 95, 160, 0.045);
            }

            .pareto-header img {
                flex: 0 0 auto;
                width: 28px;
                height: 28px;
                border-radius: 8px;
            }

            .pareto-eyebrow {
                display: inline-block;
                flex: 0 0 auto;
                margin: 0 0.2rem 0 0;
                color: var(--pareto-purple);
                font-size: 0.58rem;
                font-weight: 900;
                letter-spacing: 0.14em;
                text-transform: uppercase;
                white-space: nowrap;
            }

            .pareto-title {
                flex: 0 0 auto;
                margin: 0 !important;
                color: var(--pareto-ink);
                font-size: 1.28rem !important;
                line-height: 1 !important;
                font-weight: 900 !important;
                letter-spacing: -0.02em;
                white-space: nowrap;
            }

            .pareto-title span {
                color: var(--pareto-blue);
            }

            .pareto-subtitle {
                flex: 1 1 auto;
                min-width: 8rem;
                overflow: hidden;
                margin: 0 0 0 0.35rem;
                color: var(--pareto-muted);
                font-size: 0.76rem;
                line-height: 1.1;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            @media (max-width: 1180px) {
                .pareto-subtitle {
                    display: none;
                }

                .pareto-title {
                    font-size: 1.16rem !important;
                }
            }

            h2, h3, h4 {
                color: var(--pareto-ink);
                font-weight: 900 !important;
            }

            h2 {
                margin-top: 0.6rem !important;
                margin-bottom: 0.35rem !important;
                font-size: 1.55rem !important;
            }

            h3 {
                margin-top: 0.55rem !important;
                margin-bottom: 0.3rem !important;
            }

            div[data-testid="stMetric"] {
                padding: 0.5rem 0.65rem;
                border: 1px solid var(--pareto-border);
                border-radius: 12px;
                background: var(--pareto-card);
                box-shadow: 0 6px 16px rgba(23, 32, 51, 0.035);
            }

            div[data-testid="stMetricLabel"] p {
                color: var(--pareto-muted);
                font-weight: 800;
            }

            div[data-testid="stMetricValue"] {
                color: var(--pareto-blue);
                font-weight: 900;
                font-size: 1.9rem !important;
            }

            .pareto-metrics {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(112px, 1fr));
                gap: 0.55rem;
                margin: 0.35rem 0 0.75rem;
            }

            .pareto-metric-card {
                min-width: 0;
                padding: 0.5rem 0.62rem;
                border: 1px solid var(--pareto-border);
                border-radius: 12px;
                background: var(--pareto-card);
                box-shadow: 0 6px 16px rgba(23, 32, 51, 0.035);
            }

            .pareto-metric-label {
                overflow: hidden;
                margin: 0;
                color: var(--pareto-ink);
                font-size: 0.74rem;
                font-weight: 800;
                line-height: 1.15;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .pareto-metric-value {
                margin: 0.12rem 0 0;
                color: var(--pareto-blue);
                font-size: 1.55rem;
                font-weight: 900;
                line-height: 1;
                letter-spacing: -0.035em;
            }

            section[data-testid="stSidebar"] {
                width: 18.5rem !important;
                min-width: 18.5rem !important;
                max-width: 18.5rem !important;
                background: #ffffff;
                border-right: 1px solid var(--pareto-border);
            }

            section[data-testid="stSidebar"] > div {
                width: 18.5rem !important;
                padding-right: 0.85rem;
                padding-left: 0.85rem;
            }

            section[data-testid="stSidebar"] label,
            label[data-testid="stWidgetLabel"] p {
                color: var(--pareto-ink) !important;
                font-size: 0.88rem;
                font-weight: 800;
                line-height: 1.15;
            }

            section[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] {
                gap: 0.48rem;
            }

            section[data-testid="stSidebar"] div[data-testid="stWidgetLabel"] {
                margin-bottom: 0.1rem;
            }

            section[data-testid="stSidebar"] h2,
            section[data-testid="stSidebar"] h3 {
                color: var(--pareto-blue);
                font-size: 1.25rem !important;
                margin-bottom: 0.35rem !important;
            }

            div[data-baseweb="select"] > div,
            div[data-baseweb="input"] > div,
            div[data-baseweb="textarea"] textarea {
                min-height: 2.35rem !important;
                background: #ffffff !important;
                color: var(--pareto-ink) !important;
                border: 1px solid var(--pareto-border) !important;
                border-radius: 10px !important;
                box-shadow: 0 4px 12px rgba(23, 32, 51, 0.03);
            }

            div[data-baseweb="select"] > div:hover,
            div[data-baseweb="input"] > div:hover {
                border-color: rgba(4, 95, 160, 0.34) !important;
            }

            div[data-baseweb="select"] input,
            div[data-baseweb="input"] input {
                color: var(--pareto-ink) !important;
            }

            div[data-baseweb="select"] svg {
                color: var(--pareto-blue) !important;
            }

            div[data-baseweb="tag"] {
                background: rgba(4, 95, 160, 0.09) !important;
                color: var(--pareto-blue) !important;
                border-radius: 999px !important;
                font-weight: 800;
            }

            div[data-baseweb="popover"] ul,
            div[data-baseweb="popover"] div[role="listbox"] {
                background: #ffffff !important;
                color: var(--pareto-ink) !important;
                border: 1px solid var(--pareto-border) !important;
                border-radius: 14px !important;
                box-shadow: 0 16px 36px rgba(23, 32, 51, 0.12) !important;
            }

            div[data-baseweb="popover"] li,
            div[data-baseweb="popover"] div[role="option"] {
                color: var(--pareto-ink) !important;
            }

            .stButton > button {
                border: 0;
                border-radius: 999px;
                background: linear-gradient(90deg, var(--pareto-pink), var(--pareto-orange));
                color: #ffffff;
                font-weight: 900;
                padding: 0.38rem 0.78rem;
                box-shadow: 0 7px 18px rgba(251, 67, 95, 0.18);
            }

            .stButton > button:hover {
                color: #ffffff;
                filter: brightness(0.98);
                transform: translateY(-1px);
            }

            div[data-testid="stDataFrame"] {
                border: 1px solid var(--pareto-border);
                border-radius: 12px;
                overflow: hidden;
                background: var(--pareto-card);
                box-shadow: 0 6px 18px rgba(23, 32, 51, 0.035);
            }

            div[data-testid="stDataFrame"] * {
                color-scheme: light;
            }

            div[data-testid="stDataFrame"] [role="grid"],
            div[data-testid="stDataFrame"] canvas,
            div[data-testid="stDataFrame"] .glideDataEditor {
                background: #ffffff !important;
            }

            div[data-testid="stExpander"] {
                border: 1px solid var(--pareto-border);
                border-radius: 16px;
                background: rgba(255, 255, 255, 0.86);
            }

            .job-description-card {
                max-height: 460px;
                overflow: auto;
                padding: 1rem 1.1rem;
                border: 1px solid var(--pareto-border);
                border-radius: 16px;
                background: #ffffff;
                color: var(--pareto-ink);
                box-shadow: 0 8px 20px rgba(23, 32, 51, 0.04);
                font-size: 0.95rem;
                line-height: 1.62;
            }

            .job-description-card h1,
            .job-description-card h2,
            .job-description-card h3,
            .job-description-card h4 {
                margin: 1rem 0 0.45rem;
                color: var(--pareto-blue);
                font-weight: 900;
            }

            .job-description-card p,
            .job-description-card ul,
            .job-description-card ol {
                margin: 0 0 0.75rem;
            }

            .job-description-card ul,
            .job-description-card ol {
                padding-left: 1.35rem;
            }

            .job-description-card a {
                color: var(--pareto-blue);
            }

            a {
                color: var(--pareto-blue);
                font-weight: 700;
            }

            .pareto-url-list {
                margin: 0.1rem 0 0.7rem;
                padding-left: 1.15rem;
            }

            .pareto-url-list li {
                margin-bottom: 0.18rem;
                overflow-wrap: anywhere;
            }

            .stCaptionContainer, .stMarkdown p {
                color: var(--pareto-muted);
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_header() -> None:
    st.markdown(
        f"""
        <div class="pareto-header">
            <img src="{PARETO_LOGO_URL}" alt="Pareto AI logo" />
            <p class="pareto-eyebrow">Pareto AI</p>
            <h1 class="pareto-title">Company <span>Inspection</span></h1>
            <p class="pareto-subtitle">Compact hiring signal review for AI product and delivery opportunities.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _collection_date(argv: list[str] | None = None) -> str | None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--date")
    args, _ = parser.parse_known_args((argv or sys.argv)[1:])
    if args.date:
        return args.date

    query_date = st.query_params.get("date")
    if isinstance(query_date, str) and query_date:
        return query_date

    env_date = os.environ.get("AI_HIRING_RADAR_INSPECTION_DATE")
    if env_date:
        return env_date

    return _latest_collection_date()


def _latest_collection_date(*, data_dir: Path = DEFAULT_DATA_DIR) -> str | None:
    root = processed_dir(data_dir=data_dir)
    if not root.exists():
        return None

    dates: list[str] = []
    for path in root.glob("*.jsonl"):
        for pattern in (COMPANIES_FILENAME_PATTERN, INSPECTION_ARTIFACT_FILENAME_PATTERN):
            match = pattern.fullmatch(path.name)
            if match is not None:
                dates.append(match.group(1))
    return max(dates) if dates else None


def _sidebar_filters(records: list[dict[str, Any]]) -> dict[str, Any]:
    st.sidebar.header("Filters")
    if st.sidebar.button("Clear filters"):
        _clear_filter_state()

    with st.sidebar.form("inspection_filters"):
        filters = {
            "workplace_modes": st.multiselect(
                "Workplace mode",
                [*WORKPLACE_MODE_OPTIONS, MISSING_FILTER_OPTION],
                key="filter_workplace_modes",
            ),
            "ai_team_contexts": st.multiselect(
                "AI team context",
                [*AI_TEAM_CONTEXT_OPTIONS, MISSING_FILTER_OPTION],
                key="filter_ai_team_contexts",
            ),
            "delivery_contexts": st.multiselect(
                "Delivery context",
                [*DELIVERY_CONTEXT_OPTIONS, MISSING_FILTER_OPTION],
                key="filter_delivery_contexts",
            ),
            "company_types": st.multiselect(
                "Company type",
                [*COMPANY_TYPE_OPTIONS, MISSING_FILTER_OPTION],
                key="filter_company_types",
            ),
            "company_sizes": st.multiselect(
                "Company size",
                _company_size_options(records, include_missing=True),
                key="filter_company_sizes",
            ),
            "countries": st.multiselect(
                "Country",
                _list_options(records, "countries", include_missing=True),
                key="filter_countries",
            ),
            "role_classifications": st.multiselect(
                "Role classification",
                _options(records, "role_classification", include_missing=True),
                key="filter_role_classifications",
            ),
            "sources": st.multiselect(
                "Source/platform",
                _source_options(records, include_missing=True),
                key="filter_sources",
            ),
            "ai_tech_forward_signals": st.multiselect(
                "AI tech-forward signal",
                _options(records, "ai_tech_forward_signal", include_missing=True),
                key="filter_ai_tech_forward_signals",
            ),
            "has_contacts": st.selectbox(
                "Has contacts", BOOLEAN_FILTER_OPTIONS, key="filter_has_contacts"
            ),
            "has_job_description_extracts": st.selectbox(
                "Has job-description extracts",
                BOOLEAN_FILTER_OPTIONS,
                key="filter_has_job_description_extracts",
            ),
            "has_company_enrichment": st.selectbox(
                "Has company enrichment",
                BOOLEAN_FILTER_OPTIONS,
                key="filter_has_company_enrichment",
            ),
            "search": st.text_input(
                "Search company, titles, industry, description",
                key="filter_search",
            ).strip(),
        }
        st.form_submit_button("Apply filters")
    return filters


def _clear_filter_state() -> None:
    for key, value in FILTER_DEFAULTS.items():
        st.session_state[key] = list(value) if isinstance(value, list) else value


def _apply_filters(
    records: list[dict[str, Any]], filters: dict[str, Any]
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    search = str(filters.get("search") or "").casefold()
    for record in records:
        if not _matches_list_filter(record, "workplace_modes", filters["workplace_modes"]):
            continue
        if not _matches_list_filter(record, "ai_team_contexts", filters["ai_team_contexts"]):
            continue
        if not _matches_list_filter(record, "delivery_contexts", filters["delivery_contexts"]):
            continue
        if not _matches_scalar_filter(record, "company_type", filters["company_types"]):
            continue
        if not _matches_scalar_filter(record, "company_size", filters["company_sizes"]):
            continue
        if not _matches_list_filter(record, "countries", filters["countries"]):
            continue
        if not _matches_scalar_filter(
            record, "role_classification", filters["role_classifications"]
        ):
            continue
        if not _matches_values_filter(_record_sources(record), filters["sources"]):
            continue
        if not _matches_scalar_filter(
            record, "ai_tech_forward_signal", filters["ai_tech_forward_signals"]
        ):
            continue
        if not _matches_boolean_filter(record, "has_contacts", filters["has_contacts"]):
            continue
        if not _matches_boolean_filter(
            record,
            "has_job_description_extracts",
            filters["has_job_description_extracts"],
        ):
            continue
        if not _matches_boolean_filter(
            record, "has_company_enrichment", filters["has_company_enrichment"]
        ):
            continue
        if search and search not in _search_text(record):
            continue
        filtered.append(record)
    return filtered


def _render_summary(
    dataset: CompanyInspectionDataset,
    *,
    filtered_company_count: int,
) -> None:
    counts = dataset.counts
    total_jobs = sum(int(record.get("job_count") or 0) for record in dataset.records)

    st.caption(f"Collection date: {dataset.collection_date}")
    metrics = [
        ("Companies", counts.companies_loaded),
        ("Filtered", filtered_company_count),
        ("Jobs", total_jobs),
        ("JD extracts", counts.job_description_extracts_loaded),
        ("Enrichments", counts.company_enrichments_loaded),
        ("Missing optional", len(dataset.missing_optional_files)),
    ]
    metric_cards = "".join(_metric_card(label, value) for label, value in metrics)
    st.markdown(
        f'<div class="pareto-metrics">{metric_cards}</div>',
        unsafe_allow_html=True,
    )

    skipped = {
        "companies": counts.skipped_companies,
        "candidates": counts.skipped_candidates,
        "job_description_extracts": counts.skipped_job_description_extracts,
        "company_enrichments": counts.skipped_company_enrichments,
    }
    if any(skipped.values()):
        with st.expander("Skipped malformed rows", expanded=False):
            st.json(skipped)


def _render_missing_file_warnings(dataset: CompanyInspectionDataset) -> None:
    for path in dataset.missing_optional_files:
        st.warning(f"Optional file missing: {path.as_posix()}")


def _metric_card(label: str, value: object) -> str:
    return (
        '<div class="pareto-metric-card">'
        f'<p class="pareto-metric-label">{escape(label)}</p>'
        f'<p class="pareto-metric-value">{escape(_metric_value(value))}</p>'
        "</div>"
    )


def _metric_value(value: object) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value:,}"
    return str(value)


def _sort_controls() -> tuple[str, bool]:
    st.subheader("Companies")
    columns = st.columns([2, 1])
    sort_label = columns[0].selectbox(
        "Sort by",
        list(SORT_FIELDS),
        index=0,
        key="company_sort_field",
    )
    direction = columns[1].selectbox(
        "Direction",
        ["Descending", "Ascending"],
        index=0,
        key="company_sort_direction",
    )
    return SORT_FIELDS[sort_label], direction == "Descending"


def _render_company_table(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not records:
        st.info("No companies match the current filters.")
        return None

    event = st.dataframe(
        [_company_table_row(record) for record in records],
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config=_company_table_column_config(),
        column_order=_company_table_column_order(),
        height=360,
        row_height=30,
    )
    st.caption("Click a company row to inspect it below. Column headers can also sort the table.")
    return _selected_record_from_event(records, event)


def _render_company_detail(record: dict[str, Any] | None) -> None:
    st.subheader("Company Detail")
    if record is None:
        st.info("Select a company row to inspect details.")
        return

    _render_company_facts(record)
    _render_jobs(record)
    _render_contacts(record)
    _render_evidence(record)
    if st.checkbox(
        "Show raw inspection JSON",
        key=f"raw-company-{_widget_key_part(record.get('company_key'), record.get('company'))}",
    ):
        st.json(record)


def _render_company_facts(record: dict[str, Any]) -> None:
    st.markdown(f"### {_display(record.get('company'))}")
    summary = []
    for label, value in (
        ("Countries", _join(record.get("countries"))),
        ("Company type", record.get("company_type")),
        ("Size", record.get("company_size")),
        ("AI signal", record.get("ai_tech_forward_signal")),
    ):
        if value:
            summary.append(f"**{label}:** {value}")
    if summary:
        st.markdown(" | ".join(summary))

    columns = st.columns(4)
    columns[0].metric("Jobs", int(record.get("job_count") or 0))
    columns[1].metric("JD extracts", int(record.get("job_description_extract_count") or 0))
    columns[2].metric("Contacts", len(record.get("contacts") or []))
    columns[3].metric("Enriched", "Yes" if record.get("has_company_enrichment") else "No")

    st.markdown("#### Facts")
    left, right = st.columns(2)
    _write_fact(left, "Countries", _join(record.get("countries")))
    _write_fact(left, "Role classification", record.get("role_classification"))
    _write_fact(left, "Company type", record.get("company_type"))
    _write_fact(left, "Company size", record.get("company_size"))
    _write_fact(right, "Industry", record.get("industry"))
    _write_fact(right, "Founded", record.get("founded_year"))
    _write_fact(right, "AI tech-forward signal", record.get("ai_tech_forward_signal"))
    _write_fact(right, "Review status", record.get("review_status"))
    if record.get("company_description"):
        st.markdown("#### Description")
        st.write(record["company_description"])
    if record.get("ai_tech_forward_reason"):
        st.markdown("#### AI Tech-Forward Reason")
        st.write(record["ai_tech_forward_reason"])
    if record.get("why_interesting"):
        st.markdown("#### Why Interesting")
        st.write(record["why_interesting"])


def _write_fact(container: Any, label: str, value: object | None) -> None:
    rendered = _display(value)
    if rendered == "Unknown":
        rendered = "-"
    container.markdown(f"**{label}:** {rendered}")


def _render_jobs(record: dict[str, Any]) -> None:
    jobs = record.get("jobs") or []
    if not jobs:
        st.info("No job details are available for this company.")
        return

    st.dataframe(
        [_job_table_row(job) for job in jobs],
        use_container_width=True,
        hide_index=True,
    )
    selected_index = st.selectbox(
        "Inspect job",
        range(len(jobs)),
        format_func=lambda index: _job_option_label(jobs[index], index + 1),
        key=f"job-detail-{_widget_key_part(record.get('company_key'), record.get('company'))}",
    )
    _render_job_detail(record, jobs[int(selected_index)], int(selected_index) + 1)


def _render_job_detail(record: dict[str, Any], job: dict[str, Any], index: int) -> None:
    title = _display(job.get("job_title_raw") or job.get("job_id") or f"Job {index}")
    st.markdown(f"#### {title}")
    st.write(_job_table_row(job))
    _render_urls("Job URLs", [job.get("job_url"), job.get("source_url")])
    if job.get("contacts"):
        st.markdown("#### Job Contacts")
        st.dataframe(job["contacts"], use_container_width=True, hide_index=True)
    key_prefix = f"{_widget_key_part(record.get('company_key'), record.get('company'))}-{index}"
    if job.get("description"):
        if st.checkbox(
            "Show full job description",
            key=f"description-{key_prefix}",
        ):
            st.markdown("#### Description")
            _render_job_description(job)
        else:
            st.caption("Full job description is hidden by default for performance.")
    elif job.get("has_description"):
        st.caption("Full job description is not included in compact deployment data.")
    if st.checkbox(
        "Show raw job JSON",
        key=f"raw-job-{key_prefix}",
    ):
        st.json(job)


def _render_contacts(record: dict[str, Any]) -> None:
    contacts = record.get("contacts") or []
    if not contacts:
        st.info("No contacts available for this company.")
        return
    st.dataframe(contacts, use_container_width=True, hide_index=True)


def _render_evidence(record: dict[str, Any]) -> None:
    _render_urls("Evidence URLs", record.get("evidence_urls") or [])
    _render_urls("Company Source URLs", record.get("company_source_urls") or [])


def _render_urls(label: str, values: list[Any]) -> None:
    urls = _unique_strings(values)
    if not urls:
        return
    st.markdown(f"#### {label}")
    items = "".join(f"<li>{_url_link_html(url)}</li>" for url in urls)
    st.markdown(f'<ul class="pareto-url-list">{items}</ul>', unsafe_allow_html=True)


def _url_link_html(value: object) -> str:
    url = str(value or "").strip()
    if not url:
        return ""
    if not _is_http_url(url):
        return escape(url)
    safe_url = escape(url, quote=True)
    return (
        f'<a href="{safe_url}" target="_blank" rel="noopener noreferrer">'
        f"{escape(_url_label(url))}</a>"
    )


def _is_http_url(value: str) -> bool:
    return value.startswith(("http://", "https://"))


def _url_label(url: str) -> str:
    label = re.sub(r"^https?://", "", url).rstrip("/")
    if len(label) <= 96:
        return label
    return f"{label[:93]}..."


def _company_table_row(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "Company": record.get("company"),
        "Countries": _join(record.get("countries")),
        "Role Classification": record.get("role_classification"),
        "Jobs": record.get("job_count"),
        "JD Extracts": record.get("job_description_extract_count"),
        "Workplace Modes": _join(record.get("workplace_modes")),
        "AI Team Contexts": _join(record.get("ai_team_contexts")),
        "Delivery Contexts": _join(record.get("delivery_contexts")),
        "Company Type": record.get("company_type"),
        "Company Size": record.get("company_size"),
        "AI Signal": record.get("ai_tech_forward_signal"),
        "Sources": _join(_record_sources(record)),
        "Has Contacts": bool(record.get("has_contacts")),
    }


def _job_table_row(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "Title": job.get("job_title_raw"),
        "Role Group": job.get("role_group"),
        "Platform": job.get("platform"),
        "Country": job.get("country"),
        "Location": job.get("location"),
        "Team": job.get("team"),
        "Department": job.get("department"),
        "Employment Type": job.get("employment_type"),
        "Workplace Mode": job.get("workplace_mode"),
        "AI Team Context": job.get("ai_team_context"),
        "Delivery Context": job.get("delivery_context"),
        "Posted At": job.get("posted_at"),
        "Updated At": job.get("updated_at"),
        "Has Description": bool(job.get("has_description")),
    }


def _render_job_description(job: dict[str, Any]) -> None:
    html = _job_description_html(job.get("description"))
    if html:
        st.html(html)


def _job_description_html(value: object | None) -> str:
    description = str(value or "").strip()
    if not description:
        return ""

    description = UNSAFE_HTML_TAG_PATTERN.sub("", description)
    if _looks_like_html(description):
        body = description
    else:
        body = f"<p>{escape(description).replace(chr(10), '<br>')}</p>"
    return f'<div class="job-description-card">{body}</div>'


def _looks_like_html(value: str) -> bool:
    return HTML_TAG_PATTERN.search(value) is not None


def _company_option_label(record: dict[str, Any]) -> str:
    company = _display(record.get("company"))
    job_count = int(record.get("job_count") or 0)
    return f"{company} ({job_count} job{'s' if job_count != 1 else ''})"


def _job_option_label(job: dict[str, Any], index: int) -> str:
    title = _display(job.get("job_title_raw") or job.get("job_id") or f"Job {index}")
    platform = _display(job.get("platform"))
    if platform == "Unknown":
        return title
    return f"{title} - {platform}"


def _widget_key_part(*values: object | None) -> str:
    cleaned = "-".join(_display(value) for value in values if _display(value) != "Unknown")
    key = re.sub(r"[^a-zA-Z0-9_-]+", "-", cleaned).strip("-").lower()
    return key or "unknown"


def _company_table_column_config() -> dict[str, Any]:
    return {
        "Company": st.column_config.TextColumn("Company", width=170),
        "Countries": st.column_config.TextColumn("Countries", width=112),
        "Role Classification": st.column_config.TextColumn("Role", width=145),
        "Jobs": st.column_config.NumberColumn("Jobs", width=54),
        "JD Extracts": st.column_config.NumberColumn("JDs", width=58),
        "Workplace Modes": st.column_config.TextColumn("Workplace", width=88),
        "AI Team Contexts": st.column_config.TextColumn("AI Team", width=96),
        "Delivery Contexts": st.column_config.TextColumn("Delivery", width=88),
        "Company Type": st.column_config.TextColumn("Type", width=112),
        "Company Size": st.column_config.TextColumn("Size", width=68),
        "AI Signal": st.column_config.TextColumn("AI Signal", width=82),
        "Sources": st.column_config.TextColumn("Sources", width=82),
        "Has Contacts": st.column_config.CheckboxColumn("Contacts", width=76),
    }


def _company_table_column_order() -> tuple[str, ...]:
    return (
        "Company",
        "Countries",
        "Role Classification",
        "Jobs",
        "JD Extracts",
        "Workplace Modes",
        "AI Team Contexts",
        "Delivery Contexts",
        "Company Type",
        "Company Size",
        "AI Signal",
    )


def _selected_record_from_event(
    records: list[dict[str, Any]], event: Any
) -> dict[str, Any] | None:
    if not records:
        return None

    selected_rows = getattr(getattr(event, "selection", None), "rows", [])
    if selected_rows:
        selected_index = int(selected_rows[0])
        if 0 <= selected_index < len(records):
            return records[selected_index]
    return None


def _sort_records(
    records: list[dict[str, Any]], sort_field: str, *, descending: bool
) -> list[dict[str, Any]]:
    records_by_company = sorted(records, key=lambda record: _sort_value(record, "company"))
    return sorted(
        records_by_company,
        key=lambda record: _sort_value(record, sort_field),
        reverse=descending,
    )


def _sort_value(record: dict[str, Any], field: str) -> int | str | tuple[int, str]:
    if field in {"job_count", "job_description_extract_count"}:
        value = record.get(field)
        return value if isinstance(value, int) else 0
    if field == "company_size":
        return _company_size_sort_value(record.get(field))
    if field == "countries":
        return _join(record.get("countries")).casefold()
    if field == "sources":
        return _join(_record_sources(record)).casefold()
    value = record.get(field)
    if value is None:
        return ""
    return str(value).casefold()


def _company_size_sort_value(value: object | None) -> tuple[int, str]:
    if isinstance(value, str):
        cleaned = " ".join(value.split()).strip()
        if cleaned in COMPANY_SIZE_ORDER:
            return (COMPANY_SIZE_ORDER[cleaned], "")
        if cleaned:
            return (len(COMPANY_SIZE_OPTIONS), cleaned.casefold())
    return (len(COMPANY_SIZE_OPTIONS) + 1, "")


def _matches_list_filter(
    record: dict[str, Any], field: str, selected_values: list[str]
) -> bool:
    return _matches_values_filter(_unique_strings(record.get(field)), selected_values)


def _matches_values_filter(values: list[str], selected_values: list[str]) -> bool:
    if not selected_values:
        return True

    if not values and MISSING_FILTER_OPTION in selected_values:
        return True
    return _has_overlap(values, _selected_real_values(selected_values))


def _matches_scalar_filter(
    record: dict[str, Any], field: str, selected_values: list[str]
) -> bool:
    if not selected_values:
        return True

    value = record.get(field)
    if isinstance(value, str) and value.strip():
        return value in _selected_real_values(selected_values)
    return MISSING_FILTER_OPTION in selected_values


def _matches_boolean_filter(record: dict[str, Any], field: str, selected_value: str) -> bool:
    if selected_value == "Any":
        return True
    value = bool(record.get(field))
    return value is (selected_value == "Yes")


def _has_overlap(values: list[str], selected_values: list[str]) -> bool:
    return bool(set(values).intersection(selected_values))


def _selected_real_values(selected_values: list[str]) -> list[str]:
    return [value for value in selected_values if value != MISSING_FILTER_OPTION]


def _options(
    records: list[dict[str, Any]], field: str, *, include_missing: bool = False
) -> list[str]:
    values: list[str] = []
    has_missing = False
    for record in records:
        value = record.get(field)
        if isinstance(value, str) and value.strip():
            cleaned = " ".join(value.split()).strip()
            if cleaned not in values:
                values.append(cleaned)
            continue
        has_missing = True
    options = sorted(values)
    if include_missing and has_missing:
        options.append(MISSING_FILTER_OPTION)
    return options


def _company_size_options(
    records: list[dict[str, Any]], *, include_missing: bool = False
) -> list[str]:
    values = _options(records, "company_size", include_missing=False)
    ordered = [value for value in COMPANY_SIZE_OPTIONS if value in values]
    ordered.extend(value for value in values if value not in COMPANY_SIZE_ORDER)
    if include_missing and any(not record.get("company_size") for record in records):
        ordered.append(MISSING_FILTER_OPTION)
    return ordered


def _list_options(
    records: list[dict[str, Any]], field: str, *, include_missing: bool = False
) -> list[str]:
    values: list[str] = []
    has_missing = False
    for record in records:
        record_values = _unique_strings(record.get(field))
        if not record_values:
            has_missing = True
        for value in record_values:
            if value not in values:
                values.append(value)
    options = sorted(values)
    if include_missing and has_missing:
        options.append(MISSING_FILTER_OPTION)
    return options


def _source_options(
    records: list[dict[str, Any]], *, include_missing: bool = False
) -> list[str]:
    values: list[str] = []
    has_missing = False
    for record in records:
        sources = _record_sources(record)
        if not sources:
            has_missing = True
        for source in sources:
            if source not in values:
                values.append(source)
    options = sorted(values)
    if include_missing and has_missing:
        options.append(MISSING_FILTER_OPTION)
    return options


def _record_sources(record: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for source in _unique_strings(record.get("sources")):
        if source not in values:
            values.append(source)
    for job in record.get("jobs") or []:
        if not isinstance(job, dict):
            continue
        for source in _unique_strings([job.get("platform"), job.get("source")]):
            if source not in values:
                values.append(source)
    return values


def _search_text(record: dict[str, Any]) -> str:
    values: list[str] = [
        str(record.get("company") or ""),
        str(record.get("industry") or ""),
        str(record.get("company_description") or ""),
    ]
    values.extend(_unique_strings(record.get("ai_execution_titles")))
    values.extend(_unique_strings(record.get("ai_product_titles")))
    values.extend(_unique_strings(record.get("matched_search_terms")))
    for title_count in record.get("ai_role_title_counts") or []:
        if isinstance(title_count, dict):
            values.append(str(title_count.get("title") or ""))
    for job in record.get("jobs") or []:
        if isinstance(job, dict):
            values.append(str(job.get("job_title_raw") or ""))
            values.append(str(job.get("job_title_normalized") or ""))
    return " ".join(values).casefold()


def _join(values: object) -> str:
    return "; ".join(_unique_strings(values))


def _unique_strings(values: object) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        return []
    items: list[str] = []
    for value in values:
        if value is None:
            continue
        cleaned = " ".join(str(value).split()).strip()
        if cleaned and cleaned not in items:
            items.append(cleaned)
    return items


def _display(value: object | None) -> str:
    cleaned = " ".join(str(value or "").split()).strip()
    return cleaned or "Unknown"


if __name__ == "__main__":
    main()
