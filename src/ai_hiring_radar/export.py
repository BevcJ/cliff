from __future__ import annotations

import csv
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any

from ai_hiring_radar.hashing import normalize_hash_part
from ai_hiring_radar.models import RoleGroup
from ai_hiring_radar.storage_json import (
    DEFAULT_DATA_DIR,
    format_date,
    read_processed_jsonl,
    write_export_text,
)


EXPORT_COLUMNS = [
    "Company",
    "Countries",
    "Role Classification",
    "AI Execution Titles",
    "AI Product Titles",
    "AI Role Title Counts",
    "Matched Search Terms",
    "Evidence URLs",
    "Sources",
    "Evidence Quality",
    "Needs Review",
    "Review Status",
    "Why Interesting",
]

FIELD_BY_COLUMN = {
    "Company": "company",
    "Countries": "countries",
    "Role Classification": "role_classification",
    "AI Execution Titles": "ai_execution_titles",
    "AI Product Titles": "ai_product_titles",
    "AI Role Title Counts": "ai_role_title_counts",
    "Matched Search Terms": "matched_search_terms",
    "Evidence URLs": "evidence_urls",
    "Sources": "sources",
    "Evidence Quality": "evidence_quality",
    "Needs Review": "needs_review",
    "Review Status": "review_status",
    "Why Interesting": "why_interesting",
}

MARKDOWN_ROLE_ORDER = [
    RoleGroup.BOTH_EXECUTION_AND_PRODUCT.value,
    RoleGroup.AI_PRODUCT.value,
    RoleGroup.AI_EXECUTION.value,
    RoleGroup.UNCLEAR.value,
]


@dataclass(frozen=True)
class ExportResult:
    csv_path: Path
    markdown_path: Path
    company_count: int


def _format_export_value(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(str(item) for item in value if item)
    if isinstance(value, bool):
        return str(value).lower()
    if value is None:
        return ""
    return str(value)


def _format_role_title_counts(value: Any) -> str:
    if not isinstance(value, list):
        return _format_export_value(value)

    parts: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        title = _format_export_value(item.get("title")).strip()
        if not title:
            continue
        count = item.get("count")
        if isinstance(count, int) and count > 0:
            parts.append(f"{title} ({count})")
        else:
            parts.append(title)
    return "; ".join(parts)


def _format_company_field(field: str, value: Any) -> str:
    if field == "ai_role_title_counts":
        return _format_role_title_counts(value)
    return _format_export_value(value)


def _company_row(record: dict[str, Any]) -> dict[str, str]:
    return {
        column: _format_company_field(
            FIELD_BY_COLUMN[column], record.get(FIELD_BY_COLUMN[column])
        )
        for column in EXPORT_COLUMNS
    }


def build_company_csv(records: list[dict[str, Any]]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=EXPORT_COLUMNS)
    writer.writeheader()
    for record in records:
        writer.writerow(_company_row(record))
    return output.getvalue()


def _markdown_escape(value: Any) -> str:
    return _format_export_value(value).replace("|", "\\|").replace("\n", "<br>")


def _record_titles(record: dict[str, Any]) -> str:
    titles: list[str] = []
    for field in ("ai_execution_titles", "ai_product_titles"):
        values = record.get(field)
        if isinstance(values, list):
            for value in values:
                if value and value not in titles:
                    titles.append(str(value))
    return "; ".join(titles)


def _record_title_counts(record: dict[str, Any]) -> str:
    return _format_role_title_counts(record.get("ai_role_title_counts"))


def build_company_markdown(records: list[dict[str, Any]], *, collection_date: str) -> str:
    lines = [f"# AI Hiring Radar Company Review - {collection_date}", ""]
    records_by_group = {
        group: [
            record
            for record in records
            if record.get("role_classification") == group
        ]
        for group in MARKDOWN_ROLE_ORDER
    }

    for group in MARKDOWN_ROLE_ORDER:
        group_records = sorted(
            records_by_group[group], key=lambda item: normalize_hash_part(item.get("company"))
        )
        lines.extend([f"## {group}", ""])
        if not group_records:
            lines.extend(["No companies.", ""])
            continue

        lines.append(
            "| Company | Countries | Titles | Role Title Counts | Matched Search Terms | Evidence URLs | Why Interesting |"
        )
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for record in group_records:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _markdown_escape(record.get("company")),
                        _markdown_escape(record.get("countries")),
                        _markdown_escape(_record_titles(record)),
                        _markdown_escape(_record_title_counts(record)),
                        _markdown_escape(record.get("matched_search_terms")),
                        _markdown_escape(record.get("evidence_urls")),
                        _markdown_escape(record.get("why_interesting")),
                    ]
                )
                + " |"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def load_company_records(
    collection_date: str,
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
) -> list[dict[str, Any]]:
    normalized_date = format_date(collection_date)
    records = read_processed_jsonl(
        f"companies_{normalized_date}.jsonl",
        data_dir=data_dir,
    )
    return [record for record in records if isinstance(record, dict)]


def export_company_review_files(
    collection_date: str,
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
) -> ExportResult:
    normalized_date = format_date(collection_date)
    records = load_company_records(normalized_date, data_dir=data_dir)

    csv_path = write_export_text(
        f"companies_title_only_{normalized_date}.csv",
        build_company_csv(records),
        data_dir=data_dir,
    )
    markdown_path = write_export_text(
        f"companies_title_only_{normalized_date}.md",
        build_company_markdown(records, collection_date=normalized_date),
        data_dir=data_dir,
    )

    return ExportResult(
        csv_path=csv_path,
        markdown_path=markdown_path,
        company_count=len(records),
    )
