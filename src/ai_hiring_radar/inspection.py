from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from ai_hiring_radar.hashing import normalize_hash_part
from ai_hiring_radar.storage_json import DEFAULT_DATA_DIR, format_date, processed_dir


@dataclass(frozen=True)
class InspectionInputPaths:
    companies_path: Path
    candidates_path: Path
    job_description_extracts_path: Path
    company_enrichment_extracts_path: Path


@dataclass(frozen=True)
class InspectionLoadCounts:
    companies_loaded: int
    candidates_loaded: int
    job_description_extracts_loaded: int
    company_enrichments_loaded: int
    skipped_companies: int = 0
    skipped_candidates: int = 0
    skipped_job_description_extracts: int = 0
    skipped_company_enrichments: int = 0


@dataclass(frozen=True)
class CompanyInspectionDataset:
    collection_date: str
    records: list[dict[str, Any]]
    paths: InspectionInputPaths
    missing_optional_files: list[Path]
    counts: InspectionLoadCounts


COMPANY_ENRICHMENT_FIELDS = (
    "company_description",
    "company_description_source_urls",
    "industry",
    "industry_source_urls",
    "company_size",
    "company_size_source_urls",
    "founded_year",
    "founded_year_source_urls",
    "company_type",
    "company_type_source_urls",
    "funding_summary",
    "funding_summary_source_urls",
    "ai_tech_forward_signal",
    "ai_tech_forward_reason",
    "ai_tech_forward_source_urls",
    "enriched_at",
)

ENRICHMENT_SOURCE_URL_FIELDS = (
    "company_description_source_urls",
    "industry_source_urls",
    "company_size_source_urls",
    "founded_year_source_urls",
    "company_type_source_urls",
    "funding_summary_source_urls",
    "ai_tech_forward_source_urls",
    "source_urls",
)


def load_company_inspection_data(
    collection_date: str,
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
) -> CompanyInspectionDataset:
    normalized_date = format_date(collection_date)
    paths = _inspection_input_paths(normalized_date, data_dir=data_dir)

    companies, skipped_companies = _read_required_dict_jsonl(paths.companies_path)
    missing_optional_files: list[Path] = []

    candidates, skipped_candidates = _read_optional_dict_jsonl(
        paths.candidates_path,
        missing_optional_files=missing_optional_files,
    )
    jd_extracts, skipped_jd_extracts = _read_optional_dict_jsonl(
        paths.job_description_extracts_path,
        missing_optional_files=missing_optional_files,
    )
    company_enrichments, skipped_company_enrichments = _read_optional_dict_jsonl(
        paths.company_enrichment_extracts_path,
        missing_optional_files=missing_optional_files,
    )

    records = _build_company_inspection_records(
        companies=companies,
        candidates=candidates,
        jd_extracts=jd_extracts,
        company_enrichments=company_enrichments,
    )

    return CompanyInspectionDataset(
        collection_date=normalized_date,
        records=records,
        paths=paths,
        missing_optional_files=missing_optional_files,
        counts=InspectionLoadCounts(
            companies_loaded=len(companies),
            candidates_loaded=len(candidates),
            job_description_extracts_loaded=len(jd_extracts),
            company_enrichments_loaded=len(company_enrichments),
            skipped_companies=skipped_companies,
            skipped_candidates=skipped_candidates,
            skipped_job_description_extracts=skipped_jd_extracts,
            skipped_company_enrichments=skipped_company_enrichments,
        ),
    )


def _inspection_input_paths(collection_date: str, *, data_dir: Path) -> InspectionInputPaths:
    root = processed_dir(data_dir=data_dir)
    return InspectionInputPaths(
        companies_path=root / f"companies_{collection_date}.jsonl",
        candidates_path=root / f"job_candidates_{collection_date}.jsonl",
        job_description_extracts_path=root
        / f"job_description_extracts_{collection_date}.jsonl",
        company_enrichment_extracts_path=root
        / f"company_enrichment_extracts_{collection_date}.jsonl",
    )


def _read_required_dict_jsonl(path: Path) -> tuple[list[dict[str, Any]], int]:
    if not path.exists():
        raise FileNotFoundError(f"Required companies file does not exist: {path}")
    return _read_dict_jsonl(path)


def _read_optional_dict_jsonl(
    path: Path,
    *,
    missing_optional_files: list[Path],
) -> tuple[list[dict[str, Any]], int]:
    if not path.exists():
        missing_optional_files.append(path)
        return [], 0
    return _read_dict_jsonl(path)


def _read_dict_jsonl(path: Path) -> tuple[list[dict[str, Any]], int]:
    records: list[dict[str, Any]] = []
    skipped = 0
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except JSONDecodeError:
                skipped += 1
                continue
            if not isinstance(payload, dict):
                skipped += 1
                continue
            records.append(payload)
    return records, skipped


def _build_company_inspection_records(
    *,
    companies: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    jd_extracts: list[dict[str, Any]],
    company_enrichments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates_by_company = _group_by_company(candidates, _candidate_company_key)
    jd_extracts_by_job_id = _index_by_clean_field(jd_extracts, "job_id")
    enrichments_by_company = _last_by_company(company_enrichments, _enrichment_company_key)

    records: list[dict[str, Any]] = []
    for company in companies:
        company_key = _company_record_key(company)
        company_candidates = candidates_by_company.get(company_key, [])
        jobs = _build_company_jobs(
            company_key=company_key,
            candidates=company_candidates,
            jd_extracts=jd_extracts,
            jd_extracts_by_job_id=jd_extracts_by_job_id,
        )
        enrichment = enrichments_by_company.get(company_key)
        records.append(
            _build_company_record(
                company=company,
                company_key=company_key,
                jobs=jobs,
                enrichment=enrichment,
            )
        )

    return records


def _build_company_jobs(
    *,
    company_key: str,
    candidates: list[dict[str, Any]],
    jd_extracts: list[dict[str, Any]],
    jd_extracts_by_job_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    attached_job_ids: set[str] = set()

    for candidate in candidates:
        job_id = _clean_scalar(candidate.get("job_id"))
        extract = jd_extracts_by_job_id.get(job_id or "")
        jobs.append(_build_job_record(candidate=candidate, jd_extract=extract))
        if job_id:
            attached_job_ids.add(job_id)

    for jd_extract in jd_extracts:
        job_id = _clean_scalar(jd_extract.get("job_id"))
        if job_id and job_id in attached_job_ids:
            continue
        if _jd_extract_company_key(jd_extract) != company_key:
            continue
        jobs.append(_build_job_record(candidate=None, jd_extract=jd_extract))
        if job_id:
            attached_job_ids.add(job_id)

    return jobs


def _build_company_record(
    *,
    company: dict[str, Any],
    company_key: str,
    jobs: list[dict[str, Any]],
    enrichment: dict[str, Any] | None,
) -> dict[str, Any]:
    record = dict(company)
    record["company_key"] = company_key
    _normalize_company_list_fields(record)

    for field in COMPANY_ENRICHMENT_FIELDS:
        record[field] = enrichment.get(field) if enrichment is not None else None
    record["company_source_urls"] = _company_source_urls(enrichment)

    record["workplace_modes"] = _unique_job_values(jobs, "workplace_mode")
    record["ai_team_contexts"] = _unique_job_values(jobs, "ai_team_context")
    record["delivery_contexts"] = _unique_job_values(jobs, "delivery_context")

    company_contacts = _clean_contacts(enrichment.get("contacts") if enrichment else None)
    job_contacts = _dedupe_contacts(
        contact for job in jobs for contact in job.get("contacts", [])
    )
    contacts = _dedupe_contacts([*company_contacts, *job_contacts])

    record["company_contacts"] = company_contacts
    record["job_contacts"] = job_contacts
    record["contacts"] = contacts

    job_description_extract_count = sum(
        1 for job in jobs if job.get("has_job_description_extract")
    )
    record["job_count"] = len(jobs)
    record["job_description_extract_count"] = job_description_extract_count
    record["has_company_enrichment"] = enrichment is not None
    record["has_job_description_extracts"] = job_description_extract_count > 0
    record["has_contacts"] = bool(contacts)
    record["jobs"] = jobs
    record["raw_company_record"] = company
    record["raw_company_enrichment_record"] = enrichment
    return record


def _build_job_record(
    *,
    candidate: dict[str, Any] | None,
    jd_extract: dict[str, Any] | None,
) -> dict[str, Any]:
    source = candidate if candidate is not None else jd_extract or {}
    description = _first_clean(source, "description_plain", "description")
    contacts = _clean_contacts(jd_extract.get("contacts") if jd_extract else None)

    return {
        "job_id": _first_clean(source, "job_id"),
        "job_title_raw": _first_clean(source, "job_title_raw"),
        "job_title_normalized": _first_clean(source, "job_title_normalized"),
        "role_group": _first_clean(source, "role_group"),
        "role_search_term": _first_clean(source, "role_search_term"),
        "job_url": _first_clean(source, "job_url", "source_url"),
        "source_url": _first_clean(source, "source_url", "job_url"),
        "platform": _first_clean(source, "platform", "source"),
        "source": _first_clean(source, "source"),
        "country": _candidate_country(candidate),
        "location": _first_clean(source, "location", "job_location_raw"),
        "team": _first_clean(source, "team"),
        "department": _first_clean(source, "department"),
        "employment_type": _first_clean(source, "employment_type"),
        "workplace_type": _first_clean(source, "workplace_type"),
        "workplace_mode": _first_clean(jd_extract or {}, "workplace_mode"),
        "ai_team_context": _first_clean(jd_extract or {}, "ai_team_context"),
        "delivery_context": _first_clean(jd_extract or {}, "delivery_context"),
        "contacts": contacts,
        "posted_at": _first_clean(jd_extract or {}, "posted_at"),
        "updated_at": _first_clean(jd_extract or {}, "updated_at"),
        "has_description": description is not None,
        "description": description,
        "has_job_description_extract": jd_extract is not None,
        "raw_candidate_record": candidate,
        "raw_job_description_extract": jd_extract,
    }


def _normalize_company_list_fields(record: dict[str, Any]) -> None:
    for field in (
        "countries",
        "ai_execution_titles",
        "ai_product_titles",
        "matched_search_terms",
        "evidence_urls",
        "sources",
        "evidence_quality",
    ):
        record[field] = _clean_sequence(record.get(field))


def _group_by_company(
    records: list[dict[str, Any]],
    key_func,
) -> dict[str, list[dict[str, Any]]]:  # noqa: ANN001 - tiny internal callback helper.
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        key = key_func(record)
        if key:
            grouped[key].append(record)
    return grouped


def _last_by_company(
    records: list[dict[str, Any]],
    key_func,
) -> dict[str, dict[str, Any]]:  # noqa: ANN001 - tiny internal callback helper.
    indexed: dict[str, dict[str, Any]] = {}
    for record in records:
        key = key_func(record)
        if key:
            indexed[key] = record
    return indexed


def _index_by_clean_field(
    records: list[dict[str, Any]], field: str
) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for record in records:
        value = _clean_scalar(record.get(field))
        if value:
            indexed[value] = record
    return indexed


def _company_record_key(record: dict[str, Any]) -> str:
    return normalize_hash_part(record.get("company"))


def _candidate_company_key(record: dict[str, Any]) -> str:
    return normalize_hash_part(_first_clean(record, "company_normalized", "company"))


def _jd_extract_company_key(record: dict[str, Any]) -> str:
    return normalize_hash_part(_first_clean(record, "company_normalized", "company"))


def _enrichment_company_key(record: dict[str, Any]) -> str:
    key = normalize_hash_part(_first_clean(record, "company", "company_normalized"))
    if key:
        return key
    company_key = _first_clean(record, "company_key")
    return normalize_hash_part(company_key.replace("-", " ") if company_key else None)


def _candidate_country(candidate: dict[str, Any] | None) -> str | None:
    if candidate is None:
        return None
    countries = _clean_sequence(candidate.get("job_countries"))
    if countries:
        return countries[0]
    return _first_clean(candidate, "country")


def _unique_job_values(jobs: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for job in jobs:
        _append_unique(values, job.get(field))
    return values


def _company_source_urls(enrichment: dict[str, Any] | None) -> list[str]:
    if enrichment is None:
        return []

    urls: list[str] = []
    for field in ENRICHMENT_SOURCE_URL_FIELDS:
        for url in _clean_sequence(enrichment.get(field)):
            _append_unique(urls, url)
    for contact in _clean_contacts(enrichment.get("contacts")):
        for url in _clean_sequence(contact.get("source_urls")):
            _append_unique(urls, url)
    return urls


def _clean_contacts(values: object | None) -> list[dict[str, Any]]:
    if not isinstance(values, (list, tuple)):
        return []

    contacts: list[dict[str, Any]] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        contact: dict[str, Any] = {}
        for field in ("name", "role", "title", "email", "linkedin_url"):
            cleaned = _clean_scalar(value.get(field))
            if cleaned is not None:
                contact[field] = cleaned
        source_urls = _clean_sequence(value.get("source_urls"))
        if source_urls:
            contact["source_urls"] = source_urls
        if contact:
            contacts.append(contact)
    return _dedupe_contacts(contacts)


def _dedupe_contacts(values) -> list[dict[str, Any]]:  # noqa: ANN001 - accepts iterables.
    contacts: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for value in values:
        if not isinstance(value, dict):
            continue
        key = _contact_key(value)
        if key is None or key in seen:
            continue
        seen.add(key)
        contacts.append(value)
    return contacts


def _contact_key(contact: dict[str, Any]) -> tuple[str, ...] | None:
    email = normalize_hash_part(contact.get("email"))
    if email:
        return ("email", email)

    linkedin_url = normalize_hash_part(contact.get("linkedin_url"))
    if linkedin_url:
        return ("linkedin_url", linkedin_url)

    name = normalize_hash_part(contact.get("name"))
    title = normalize_hash_part(contact.get("title"))
    role = normalize_hash_part(contact.get("role"))
    if name or title or role:
        return ("person", name, title, role)
    return None


def _clean_sequence(values: object | None) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        return []

    items: list[str] = []
    for value in values:
        _append_unique(items, value)
    return items


def _append_unique(values: list[str], value: object | None) -> None:
    cleaned = _clean_scalar(value)
    if cleaned is not None and cleaned not in values:
        values.append(cleaned)


def _first_clean(record: dict[str, Any], *fields: str) -> str | None:
    for field in fields:
        cleaned = _clean_scalar(record.get(field))
        if cleaned is not None:
            return cleaned
    return None


def _clean_scalar(value: object | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(str(value).split()).strip()
    return cleaned or None
