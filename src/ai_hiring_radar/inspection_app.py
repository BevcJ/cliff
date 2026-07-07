from __future__ import annotations

import argparse
from dataclasses import dataclass
from html import escape
import re
import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, DataReturnMode, GridOptionsBuilder

from ai_hiring_radar.inspection import CompanyInspectionDataset, load_company_inspection_data
from ai_hiring_radar.review_state import (
    FIT_STATUS_OPTIONS,
    OUTREACH_STATUS_OPTIONS,
    build_review_state_payload,
    load_review_state,
    merge_review_state,
    upsert_review_state,
)
from ai_hiring_radar.storage_json import DEFAULT_DATA_DIR, processed_dir


PARETO_LOGO_URL = "https://www.pareto.si/wp-content/uploads/2023/03/logo_90.png"
REVIEW_STATE_DATABASE_URL_ENV = "AI_HIRING_RADAR_REVIEW_STATE_DATABASE_URL"
REVIEW_STATE_CONNECTION_SECRET = "supabase_review_state"
WORKFLOW_VIEW_OPTIONS = ("Inspect", "Shortlist", "Outreach", "Rejected")
EDITABLE_REVIEW_TABLE_COLUMNS = ("Fit Status", "Outreach Status")
HIDDEN_GRID_COLUMNS = ("Grid Row Key", "Company Key", "Review Notes")
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
    "Fit Status": "fit_status",
    "Outreach Status": "outreach_status",
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
    "filter_min_jobs": None,
    "filter_max_jobs": None,
    "filter_countries": [],
    "filter_role_classifications": [],
    "filter_sources": [],
    "filter_ai_tech_forward_signals": [],
    "filter_fit_statuses": [],
    "filter_outreach_statuses": [],
    "filter_needs_action": "Any",
    "filter_has_contacts": "Any",
    "filter_has_job_description_extracts": "Any",
    "filter_has_company_enrichment": "Any",
    "filter_search": "",
}


@dataclass(frozen=True)
class ReviewStateBackendStatus:
    database_url: str | None
    rows_loaded: int = 0
    error: str | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.database_url) and self.error is None

    @property
    def read_only_reason(self) -> str:
        if not self.database_url:
            return "review-state database URL is not configured"
        if self.error:
            return self.error
        return "review-state persistence is unavailable"


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

    review_state_by_company_key: dict[str, dict[str, Any]] = {}
    review_state_error: str | None = None
    review_state_database_url = _review_state_database_url()
    if review_state_database_url:
        try:
            review_state_by_company_key = _load_review_state_for_records(
                dataset.records,
                database_url=review_state_database_url,
            )
        except Exception as exc:  # pragma: no cover - exact driver errors vary.
            review_state_error = str(exc)
    review_state_status = ReviewStateBackendStatus(
        database_url=review_state_database_url,
        rows_loaded=len(review_state_by_company_key),
        error=review_state_error,
    )
    records = merge_review_state(dataset.records, review_state_by_company_key)

    _render_missing_file_warnings(dataset)
    _render_pending_save_message()
    reviewer_name = _sidebar_reviewer_name()
    filters = _sidebar_filters(records)
    filtered_records = _apply_filters(records, filters)

    _render_summary(
        dataset,
        records=records,
        review_state_status=review_state_status,
        filtered_company_count=len(filtered_records),
    )
    _render_companies_workspace(
        filtered_records,
        review_state_status=review_state_status,
        reviewer_name=reviewer_name,
        collection_date=dataset.collection_date,
    )


@st.cache_data(show_spinner="Loading processed inspection data")
def _load_dataset(collection_date: str) -> CompanyInspectionDataset:
    return load_company_inspection_data(collection_date)


def _review_state_database_url() -> str | None:
    secret_url = _review_state_database_url_from_secrets()
    if secret_url:
        return secret_url
    env_url = os.environ.get(REVIEW_STATE_DATABASE_URL_ENV, "").strip()
    return env_url or None


def _review_state_database_url_from_secrets() -> str | None:
    try:
        secrets = st.secrets
        connections = _mapping_get(secrets, "connections")
        connection = _mapping_get(connections, REVIEW_STATE_CONNECTION_SECRET)
        url = _mapping_get(connection, "url")
    except Exception:
        return None
    return url.strip() if isinstance(url, str) and url.strip() else None


def _mapping_get(value: object | None, key: str) -> object | None:
    if value is None:
        return None
    get = getattr(value, "get", None)
    if callable(get):
        try:
            return get(key)
        except Exception:
            return None
    try:
        return value[key]  # type: ignore[index]
    except Exception:
        return None


def _load_review_state_for_records(
    records: list[dict[str, Any]],
    *,
    database_url: str,
) -> dict[str, dict[str, Any]]:
    return load_review_state(_record_company_keys(records), database_url=database_url)


def _record_company_keys(records: list[dict[str, Any]]) -> list[str]:
    keys: list[str] = []
    for record in records:
        company_key = " ".join(str(record.get("company_key") or "").split()).strip()
        if company_key and company_key not in keys:
            keys.append(company_key)
    return keys


def _render_pending_save_message() -> None:
    message = st.session_state.pop("review_state_save_message", None)
    if message:
        st.success(str(message))


def _sidebar_reviewer_name() -> str:
    st.sidebar.header("Review")
    return st.sidebar.text_input("Reviewer name", key="reviewer_name").strip()


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
            "min_jobs": st.number_input(
                "Min job posts",
                min_value=0,
                value=None,
                step=1,
                placeholder="Any",
                key="filter_min_jobs",
            ),
            "max_jobs": st.number_input(
                "Max job posts",
                min_value=0,
                value=None,
                step=1,
                placeholder="Any",
                key="filter_max_jobs",
                help="Use 9 for fewer than 10 job posts.",
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
            "fit_statuses": st.multiselect(
                "Fit status",
                list(FIT_STATUS_OPTIONS),
                key="filter_fit_statuses",
            ),
            "outreach_statuses": st.multiselect(
                "Outreach status",
                list(OUTREACH_STATUS_OPTIONS),
                key="filter_outreach_statuses",
            ),
            "needs_action": st.selectbox(
                "Needs action",
                BOOLEAN_FILTER_OPTIONS,
                key="filter_needs_action",
                help=(
                    "Suitable companies with outreach not started or follow-up needed."
                ),
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
        if not _matches_job_count_filter(
            record,
            filters.get("min_jobs"),
            filters.get("max_jobs"),
        ):
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
        if not _matches_scalar_filter(record, "fit_status", filters.get("fit_statuses", [])):
            continue
        if not _matches_scalar_filter(
            record,
            "outreach_status",
            filters.get("outreach_statuses", []),
        ):
            continue
        if not _matches_needs_action_filter(record, filters.get("needs_action", "Any")):
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
    records: list[dict[str, Any]],
    review_state_status: ReviewStateBackendStatus,
    filtered_company_count: int,
) -> None:
    counts = dataset.counts
    total_jobs = sum(int(record.get("job_count") or 0) for record in dataset.records)
    default_review_count = sum(1 for record in records if not record.get("has_review_state"))

    st.caption(f"Collection date: {dataset.collection_date}")
    metrics = [
        ("Companies", counts.companies_loaded),
        ("Filtered", filtered_company_count),
        ("Jobs", total_jobs),
        ("JD extracts", counts.job_description_extracts_loaded),
        ("Enrichments", counts.company_enrichments_loaded),
        ("Review rows", review_state_status.rows_loaded),
        ("Default state", default_review_count),
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
    _render_review_state_status(review_state_status, records)


def _render_review_state_status(
    review_state_status: ReviewStateBackendStatus,
    records: list[dict[str, Any]],
) -> None:
    if review_state_status.enabled:
        st.caption(
            "Review-state persistence enabled: "
            f"{review_state_status.rows_loaded} persisted row(s) loaded."
        )
    else:
        st.warning(
            "Review-state persistence is disabled; generated inspection data is read-only. "
            f"Reason: {review_state_status.read_only_reason}."
        )

    st.caption("Fit status: " + _format_counts(_count_by(records, "fit_status")))
    st.caption(
        "Outreach status: " + _format_counts(_count_by(records, "outreach_status"))
    )


def _count_by(records: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = str(record.get(field) or "").strip() or "(missing)"
        counts[value] = counts.get(value, 0) + 1
    return counts


def _format_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "none"
    return ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))


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


def _render_companies_workspace(
    records: list[dict[str, Any]],
    *,
    review_state_status: ReviewStateBackendStatus,
    reviewer_name: str,
    collection_date: str,
) -> None:
    st.subheader("Companies")
    workflow_view, sort_field, descending = _company_workspace_controls(records)
    visible_records = _workflow_records(records, workflow_view)
    sorted_records = _sort_records(visible_records, sort_field, descending=descending)
    scope = _widget_key_part(workflow_view)

    st.caption(f"{len(sorted_records)} company record(s)")
    selected_record = _render_company_table(
        sorted_records,
        key=f"{scope}-company-table",
        review_state_status=review_state_status,
        reviewer_name=reviewer_name,
        collection_date=collection_date,
    )
    _render_company_detail(
        selected_record,
        review_state_status=review_state_status,
        reviewer_name=reviewer_name,
        collection_date=collection_date,
        scope=scope,
    )


def _company_workspace_controls(records: list[dict[str, Any]]) -> tuple[str, str, bool]:
    workflow_column, sort_column, direction_column = st.columns([5.8, 1.45, 1.25])
    workflow_view = workflow_column.segmented_control(
        "Workflow",
        WORKFLOW_VIEW_OPTIONS,
        default="Inspect",
        format_func=lambda value: _workflow_label(str(value), records),
        key="company_workflow_view",
    )
    sort_label = sort_column.selectbox(
        "Sort",
        list(SORT_FIELDS),
        index=0,
        key="company_sort_field",
    )
    direction = direction_column.selectbox(
        "Dir",
        ["Descending", "Ascending"],
        index=0,
        key="company_sort_direction",
    )
    return str(workflow_view or "Inspect"), SORT_FIELDS[sort_label], direction == "Descending"


def _workflow_label(workflow_view: str, records: list[dict[str, Any]]) -> str:
    return f"{workflow_view} ({len(_workflow_records(records, workflow_view))})"


def _workflow_records(
    records: list[dict[str, Any]], workflow_view: str
) -> list[dict[str, Any]]:
    if workflow_view == "Shortlist":
        return _shortlist_records(records)
    if workflow_view == "Outreach":
        return _outreach_records(records)
    if workflow_view == "Rejected":
        return _rejected_records(records)
    return records


def _shortlist_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        record
        for record in records
        if record.get("fit_status") in {"best_fit", "possible_fit"}
    ]


def _outreach_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        record
        for record in _shortlist_records(records)
        if record.get("outreach_status") != "not_started"
    ]


def _rejected_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [record for record in records if record.get("fit_status") == "not_interesting"]


def _render_company_table(
    records: list[dict[str, Any]],
    *,
    key: str = "company-table",
    review_state_status: ReviewStateBackendStatus,
    reviewer_name: str,
    collection_date: str,
) -> dict[str, Any] | None:
    if not records:
        st.info("No companies match the current filters.")
        return None

    grid_rows = _company_grid_rows(records)
    grid_result = AgGrid(
        pd.DataFrame(grid_rows),
        gridOptions=_company_grid_options(
            grid_rows,
            editable=review_state_status.enabled,
        ),
        height=360,
        data_return_mode=DataReturnMode.AS_INPUT,
        update_on=["cellValueChanged", "selectionChanged"],
        allow_unsafe_jscode=False,
        theme="streamlit",
        key=key,
        show_search=False,
        show_download_button=False,
    )
    st.caption(
        "Click a company row to inspect it below. Edit Fit or Outreach directly in the table."
    )
    selected_record = _selected_record_from_grid_result(records, grid_result)
    changes = _status_changes_from_grid_data(
        records,
        _grid_data_rows(_grid_result_data(grid_result)),
    )
    if not changes:
        return selected_record
    if not review_state_status.database_url:
        st.error("Review-state database URL is not configured.")
        return selected_record

    try:
        _save_table_status_changes(
            changes,
            database_url=review_state_status.database_url,
            reviewer_name=reviewer_name,
            collection_date=collection_date,
        )
    except Exception as exc:
        st.error(f"Failed to save table edit: {exc}")
        return selected_record

    st.session_state["selected_company_key"] = changes[-1].get(
        "grid_row_key",
        changes[-1]["company_key"],
    )
    count_label = "status update" if len(changes) == 1 else "status updates"
    st.session_state["review_state_save_message"] = (
        f"Saved {len(changes)} {count_label}."
    )
    st.rerun()
    return selected_record


def _company_grid_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_company_grid_row(record, index) for index, record in enumerate(records)]


def _company_grid_row(record: dict[str, Any], index: int) -> dict[str, Any]:
    row = _company_table_row(record)
    row["Grid Row Key"] = _record_grid_key(record, index)
    row["Company Key"] = str(record.get("company_key") or "").strip()
    row["Review Notes"] = str(record.get("review_notes") or "")
    return row


def _record_grid_key(record: dict[str, Any], index: int) -> str:
    company_key = str(record.get("company_key") or "").strip()
    return company_key or f"__row_{index}"


def _company_grid_options(
    grid_rows: list[dict[str, Any]],
    *,
    editable: bool,
) -> dict[str, Any]:
    builder = GridOptionsBuilder.from_dataframe(pd.DataFrame(grid_rows))
    builder.configure_default_column(
        editable=False,
        filter=False,
        resizable=True,
        sortable=False,
    )
    builder.configure_selection(
        selection_mode="single",
        use_checkbox=False,
        pre_selected_rows=_pre_selected_grid_rows(grid_rows),
        suppressRowDeselection=True,
        suppressRowClickSelection=False,
    )
    for column in HIDDEN_GRID_COLUMNS:
        builder.configure_column(column, hide=True)
    builder.configure_column("Company", pinned="left", width=190)
    builder.configure_column(
        "Fit Status",
        editable=editable,
        cellEditor="agSelectCellEditor",
        cellEditorParams={"values": list(FIT_STATUS_OPTIONS)},
        singleClickEdit=True,
        width=130,
    )
    builder.configure_column(
        "Outreach Status",
        editable=editable,
        cellEditor="agSelectCellEditor",
        cellEditorParams={"values": list(OUTREACH_STATUS_OPTIONS)},
        singleClickEdit=True,
        width=150,
    )
    builder.configure_column("Jobs", type=["numericColumn"], width=72)
    options = builder.build()
    options["rowSelection"] = "single"
    options["suppressRowClickSelection"] = False
    return options


def _pre_selected_grid_rows(grid_rows: list[dict[str, Any]]) -> list[int]:
    selected_key = str(st.session_state.get("selected_company_key") or "")
    for index, row in enumerate(grid_rows):
        if row.get("Grid Row Key") == selected_key:
            return [index]
    return [0] if grid_rows else []


def _status_changes_from_grid_data(
    records: list[dict[str, Any]],
    grid_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    records_by_grid_key = {
        _record_grid_key(record, index): record for index, record in enumerate(records)
    }
    for row in grid_rows:
        grid_key = str(row.get("Grid Row Key") or "")
        record = records_by_grid_key.get(grid_key)
        if record is None:
            continue
        company_key = str(record.get("company_key") or "").strip()
        if not company_key:
            continue
        current_fit_status = str(record.get("fit_status") or "unreviewed")
        current_outreach_status = str(record.get("outreach_status") or "not_started")
        fit_status = str(row.get("Fit Status") or current_fit_status)
        outreach_status = str(row.get("Outreach Status") or current_outreach_status)
        if (
            fit_status == current_fit_status
            and outreach_status == current_outreach_status
        ):
            continue
        changes.append(
            {
                "grid_row_key": grid_key,
                "company_key": company_key,
                "company": str(record.get("company") or ""),
                "fit_status": fit_status,
                "outreach_status": outreach_status,
                "notes": str(record.get("review_notes") or ""),
            }
        )
    return changes


def _grid_result_data(grid_result: Any) -> Any:
    if isinstance(grid_result, dict):
        return grid_result.get("data")
    return getattr(grid_result, "data", None)


def _grid_data_rows(grid_data: Any) -> list[dict[str, Any]]:
    if isinstance(grid_data, pd.DataFrame):
        return grid_data.to_dict("records")
    if isinstance(grid_data, list):
        return [row for row in grid_data if isinstance(row, dict)]
    if isinstance(grid_data, dict):
        data = grid_data.get("data")
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
    return []


def _selected_record_from_grid_result(
    records: list[dict[str, Any]], grid_result: Any
) -> dict[str, Any] | None:
    selected_key = _selected_grid_row_key(grid_result)
    if selected_key is not None:
        st.session_state["selected_company_key"] = selected_key
        selected = _record_for_grid_key(records, selected_key)
        if selected is not None:
            return selected

    persisted_key = str(st.session_state.get("selected_company_key") or "")
    if persisted_key:
        selected = _record_for_grid_key(records, persisted_key)
        if selected is not None:
            return selected
    return records[0] if records else None


def _selected_grid_row_key(grid_result: Any) -> str | None:
    selected_rows = _grid_result_selected_rows(grid_result)
    rows = _grid_data_rows(selected_rows)
    if not rows and isinstance(selected_rows, list):
        rows = [row for row in selected_rows if isinstance(row, dict)]
    if not rows:
        return None
    row_key = str(rows[0].get("Grid Row Key") or "").strip()
    return row_key or None


def _grid_result_selected_rows(grid_result: Any) -> Any:
    if isinstance(grid_result, dict):
        return grid_result.get("selected_rows")
    return getattr(grid_result, "selected_rows", None)


def _record_for_grid_key(
    records: list[dict[str, Any]], grid_key: str
) -> dict[str, Any] | None:
    for index, record in enumerate(records):
        if _record_grid_key(record, index) == grid_key:
            return record
    return None


def _save_table_status_changes(
    changes: list[dict[str, Any]],
    *,
    database_url: str,
    reviewer_name: str,
    collection_date: str,
) -> None:
    for change in changes:
        payload = build_review_state_payload(
            company_key=str(change.get("company_key") or ""),
            company=str(change.get("company") or ""),
            fit_status=str(change.get("fit_status") or ""),
            outreach_status=str(change.get("outreach_status") or ""),
            notes=str(change.get("notes") or ""),
            collection_date=collection_date,
            reviewer_name=reviewer_name,
        )
        upsert_review_state(payload, database_url=database_url)


def _render_company_detail(
    record: dict[str, Any] | None,
    *,
    review_state_status: ReviewStateBackendStatus,
    reviewer_name: str,
    collection_date: str,
    scope: str,
) -> None:
    st.subheader("Company Detail")
    if record is None:
        st.info("Select a company row to inspect details.")
        return

    _render_company_facts(
        record,
        review_state_status=review_state_status,
        reviewer_name=reviewer_name,
        collection_date=collection_date,
        scope=scope,
    )
    _render_jobs(record, scope=scope)
    _render_contacts(record)
    _render_evidence(record)
    if st.checkbox(
        "Show raw inspection JSON",
        key=f"raw-company-{_widget_key_part(scope, record.get('company_key'), record.get('company'))}",
    ):
        st.json(record)


def _render_company_facts(
    record: dict[str, Any],
    *,
    review_state_status: ReviewStateBackendStatus,
    reviewer_name: str,
    collection_date: str,
    scope: str,
) -> None:
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

    _render_review_form(
        record,
        review_state_status=review_state_status,
        reviewer_name=reviewer_name,
        collection_date=collection_date,
        scope=scope,
    )

    st.markdown("#### Facts")
    left, right = st.columns(2)
    _write_fact(left, "Countries", _join(record.get("countries")))
    _write_fact(left, "Role classification", record.get("role_classification"))
    _write_fact(left, "Company type", record.get("company_type"))
    _write_fact(left, "Company size", record.get("company_size"))
    _write_fact(right, "Industry", record.get("industry"))
    _write_fact(right, "Founded", record.get("founded_year"))
    _write_fact(right, "AI tech-forward signal", record.get("ai_tech_forward_signal"))
    _write_fact(right, "Fit status", record.get("fit_status"))
    _write_fact(right, "Outreach status", record.get("outreach_status"))
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


def _render_review_form(
    record: dict[str, Any],
    *,
    review_state_status: ReviewStateBackendStatus,
    reviewer_name: str,
    collection_date: str,
    scope: str,
) -> None:
    st.markdown("#### Manual Review")
    review_metadata = _review_metadata(record)
    if review_metadata:
        st.caption(review_metadata)

    company_key = str(record.get("company_key") or "").strip()
    disabled_reason: str | None = None
    if not company_key:
        disabled_reason = "This record has no company_key, so review state cannot be saved."
    elif not review_state_status.enabled:
        disabled_reason = f"Read-only mode: {review_state_status.read_only_reason}."
    if disabled_reason:
        st.warning(disabled_reason)

    disabled = disabled_reason is not None
    form_key = f"review-state-{_widget_key_part(scope, company_key, record.get('company'))}"
    fit_options = list(FIT_STATUS_OPTIONS)
    outreach_options = list(OUTREACH_STATUS_OPTIONS)
    with st.form(form_key, border=False):
        status_columns = st.columns(2)
        fit_status = status_columns[0].selectbox(
            "Fit status",
            fit_options,
            index=_option_index(fit_options, record.get("fit_status")),
            disabled=disabled,
            key=f"{form_key}-fit-status",
        )
        outreach_status = status_columns[1].selectbox(
            "Outreach status",
            outreach_options,
            index=_option_index(outreach_options, record.get("outreach_status")),
            disabled=disabled,
            key=f"{form_key}-outreach-status",
        )
        notes = st.text_area(
            "Notes",
            value=str(record.get("review_notes") or ""),
            disabled=disabled,
            height=88,
            key=f"{form_key}-notes",
        )
        submitted = st.form_submit_button("Save notes/status", disabled=disabled)

    if not submitted:
        return

    if not review_state_status.database_url:
        st.error("Review-state database URL is not configured.")
        return

    try:
        payload = build_review_state_payload(
            company_key=company_key,
            company=str(record.get("company") or ""),
            fit_status=str(fit_status),
            outreach_status=str(outreach_status),
            notes=notes,
            collection_date=collection_date,
            reviewer_name=reviewer_name,
        )
        upsert_review_state(payload, database_url=review_state_status.database_url)
    except Exception as exc:
        st.error(f"Failed to save review state: {exc}")
        return

    st.session_state["review_state_save_message"] = (
        f"Saved review state for {_display(record.get('company'))}."
    )
    st.rerun()


def _review_metadata(record: dict[str, Any]) -> str:
    metadata: list[str] = []
    if record.get("inspected_at"):
        metadata.append(f"Inspected: {record['inspected_at']}")
    if record.get("last_reviewed_at"):
        metadata.append(f"Last saved: {record['last_reviewed_at']}")
    if record.get("last_reviewed_by"):
        metadata.append(f"By: {record['last_reviewed_by']}")
    return " | ".join(metadata)


def _option_index(options: list[Any], value: object | None) -> int:
    cleaned = str(value or "").strip()
    return options.index(cleaned) if cleaned in options else 0


def _write_fact(container: Any, label: str, value: object | None) -> None:
    rendered = _display(value)
    if rendered == "Unknown":
        rendered = "-"
    container.markdown(f"**{label}:** {rendered}")


def _render_jobs(record: dict[str, Any], *, scope: str) -> None:
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
        key=f"job-detail-{_widget_key_part(scope, record.get('company_key'), record.get('company'))}",
    )
    _render_job_detail(
        record,
        jobs[int(selected_index)],
        int(selected_index) + 1,
        scope=scope,
    )


def _render_job_detail(
    record: dict[str, Any],
    job: dict[str, Any],
    index: int,
    *,
    scope: str,
) -> None:
    title = _display(job.get("job_title_raw") or job.get("job_id") or f"Job {index}")
    st.markdown(f"#### {title}")
    st.write(_job_table_row(job))
    _render_urls("Job URLs", [job.get("job_url"), job.get("source_url")])
    if job.get("contacts"):
        st.markdown("#### Job Contacts")
        st.dataframe(job["contacts"], use_container_width=True, hide_index=True)
    key_prefix = (
        f"{_widget_key_part(scope, record.get('company_key'), record.get('company'))}-{index}"
    )
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
        "Fit Status": record.get("fit_status"),
        "Outreach Status": record.get("outreach_status"),
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
        "Fit Status": st.column_config.SelectboxColumn(
            "Fit",
            options=list(FIT_STATUS_OPTIONS),
            width=116,
        ),
        "Outreach Status": st.column_config.SelectboxColumn(
            "Outreach",
            options=list(OUTREACH_STATUS_OPTIONS),
            width=132,
        ),
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
        "Fit Status",
        "Outreach Status",
        "Countries",
        "Role Classification",
        "Jobs",
        "Workplace Modes",
        "AI Team Contexts",
        "Delivery Contexts",
        "Company Type",
        "Company Size",
        "AI Signal",
    )


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


def _matches_needs_action_filter(record: dict[str, Any], selected_value: str) -> bool:
    if selected_value == "Any":
        return True
    needs_action = _is_needs_action_record(record)
    return needs_action is (selected_value == "Yes")


def _is_needs_action_record(record: dict[str, Any]) -> bool:
    return record.get("fit_status") in {"best_fit", "possible_fit"} and record.get(
        "outreach_status"
    ) in {"not_started", "follow_up_needed"}


def _matches_job_count_filter(
    record: dict[str, Any], min_jobs: object | None, max_jobs: object | None
) -> bool:
    job_count = _integer_value(record.get("job_count")) or 0
    min_value = _integer_value(min_jobs)
    max_value = _integer_value(max_jobs)
    if min_value is not None and job_count < min_value:
        return False
    if max_value is not None and job_count > max_value:
        return False
    return True


def _integer_value(value: object | None) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


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
