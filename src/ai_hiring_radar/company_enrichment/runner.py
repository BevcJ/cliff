from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from tqdm import tqdm

from ai_hiring_radar.company_enrichment.contracts import (
    CompanyEnrichment,
    CompanyEnrichmentExtractor,
    CompanyEnrichmentRunIssue,
    CompanyEnrichmentRunResult,
)
from ai_hiring_radar.company_enrichment.inputs import (
    build_enrichment_input,
    company_record_key,
    group_candidate_records_by_company,
)
from ai_hiring_radar.company_enrichment.records import build_enrichment_record
from ai_hiring_radar.company_enrichment.quality import (
    CONTACT_QUALITY_RETRY_UNRESOLVED_WARNING,
    has_high_value_contact,
    is_contact_quality_retry_reason,
    needs_quality_retry,
    prepare_enrichment_for_record,
)
from ai_hiring_radar.company_enrichment.text import clean_scalar
from ai_hiring_radar.job_description_extraction.dates import utc_now_iso
from ai_hiring_radar.llm_usage import (
    LLMCostEstimate,
    LLMCallResult,
    LLMUsage,
    add_usage,
    estimate_llm_cost,
)
from ai_hiring_radar.storage_json import (
    DEFAULT_DATA_DIR,
    append_jsonl,
    format_date,
    processed_dir,
    read_jsonl,
    read_processed_jsonl,
    slugify,
    write_jsonl,
)


def run_company_enrichment(
    collection_date: str,
    *,
    extractor: CompanyEnrichmentExtractor | None,
    model: str,
    data_dir: Path = DEFAULT_DATA_DIR,
    limit: int | None = None,
    country_names: list[str] | None = None,
    dry_run: bool = False,
    clock: Callable[[], str] = utc_now_iso,
    show_progress: bool = True,
    restart: bool = False,
) -> CompanyEnrichmentRunResult:
    normalized_date = format_date(collection_date)
    company_input_filename = f"companies_{normalized_date}.jsonl"
    candidate_input_filename = f"job_candidates_{normalized_date}.jsonl"
    output_filename = f"company_enrichment_extracts_{normalized_date}.jsonl"

    raw_company_records = read_processed_jsonl(company_input_filename, data_dir=data_dir)
    filtered_company_records = _filter_company_records_by_country(
        raw_company_records,
        country_names=country_names,
    )
    records_to_process = (
        filtered_company_records[:limit]
        if limit is not None
        else filtered_company_records
    )
    raw_candidate_records = _read_candidate_records_if_present(
        candidate_input_filename,
        data_dir=data_dir,
    )
    candidates_by_company = group_candidate_records_by_company(raw_candidate_records)
    output_path = processed_dir(data_dir=data_dir) / output_filename

    if not dry_run and extractor is None:
        raise ValueError("extractor is required unless dry_run is true.")

    completed_company_keys = _prepare_output_file(
        output_path,
        dry_run=dry_run,
        restart=restart,
    )
    pending_records, already_processed_count = _pending_records(
        records_to_process,
        completed_company_keys=completed_company_keys,
    )

    run_state = _run_enrichment_batch(
        records_to_process=pending_records,
        candidates_by_company=candidates_by_company,
        extractor=extractor,
        model=model,
        dry_run=dry_run,
        clock=clock,
        output_path=None if dry_run else output_path,
        completed_company_keys=completed_company_keys,
        already_processed_count=already_processed_count,
        show_progress=show_progress,
    )

    processed_root = processed_dir(data_dir=data_dir)
    return CompanyEnrichmentRunResult(
        collection_date=normalized_date,
        model=model,
        company_input_path=processed_root / company_input_filename,
        candidate_input_path=processed_root / candidate_input_filename,
        output_path=processed_root / output_filename,
        companies_read=len(records_to_process),
        processable_count=run_state.processable_count,
        enriched_count=len(run_state.records),
        skipped_count=run_state.skipped_count,
        validation_error_count=run_state.validation_error_count,
        llm_error_count=run_state.llm_error_count,
        already_processed_count=run_state.already_processed_count,
        llm_usage=run_state.llm_usage,
        llm_estimated_cost_usd=run_state.llm_estimated_cost_usd,
        llm_pricing_missing_models=tuple(sorted(run_state.llm_pricing_missing_models)),
        quality_error_count=run_state.quality_error_count,
        dry_run=dry_run,
        validation_error_samples=tuple(run_state.validation_error_samples),
        llm_error_samples=tuple(run_state.llm_error_samples),
        quality_error_samples=tuple(run_state.quality_error_samples),
    )


def _filter_company_records_by_country(
    records: list[Any],
    *,
    country_names: list[str] | None,
) -> list[Any]:
    if not country_names:
        return records

    selected_countries = {
        country.casefold()
        for country in (clean_scalar(country_name) for country_name in country_names)
        if country is not None
    }
    if not selected_countries:
        return records

    return [
        record
        for record in records
        if isinstance(record, dict)
        and _company_record_matches_country(record, selected_countries)
    ]


def _company_record_matches_country(
    record: dict[str, Any],
    selected_countries: set[str],
) -> bool:
    raw_countries = record.get("countries")
    if isinstance(raw_countries, (list, tuple, set)):
        countries = [clean_scalar(country) for country in raw_countries]
    else:
        countries = [clean_scalar(raw_countries)]

    return any(
        country.casefold() in selected_countries
        for country in countries
        if country is not None
    )


class _RunState:
    def __init__(
        self,
        *,
        output_path: Path | None,
        completed_company_keys: set[str],
        already_processed_count: int,
    ) -> None:
        self.records: list[dict[str, Any]] = []
        self.output_path = output_path
        self.completed_company_keys = completed_company_keys
        self.already_processed_count = already_processed_count
        self.processable_count = 0
        self.skipped_count = 0
        self.validation_error_count = 0
        self.llm_error_count = 0
        self.quality_error_count = 0
        self.llm_usage = LLMUsage()
        self.llm_estimated_cost_usd: float | None = 0.0
        self.llm_pricing_missing_models: set[str] = set()
        self.validation_error_samples: list[CompanyEnrichmentRunIssue] = []
        self.llm_error_samples: list[CompanyEnrichmentRunIssue] = []
        self.quality_error_samples: list[CompanyEnrichmentRunIssue] = []


@dataclass(frozen=True)
class _EnrichmentCallResult:
    enrichment: CompanyEnrichment
    usage: LLMUsage | None
    cost: LLMCostEstimate | None


def _read_candidate_records_if_present(
    filename: str,
    *,
    data_dir: Path,
) -> list[Any]:
    candidate_path = processed_dir(data_dir=data_dir) / filename
    if not candidate_path.exists():
        return []
    return read_processed_jsonl(filename, data_dir=data_dir)


def _run_enrichment_batch(
    *,
    records_to_process: list[Any],
    candidates_by_company: dict[str, list[dict[str, Any]]],
    extractor: CompanyEnrichmentExtractor | None,
    model: str,
    dry_run: bool,
    clock: Callable[[], str],
    output_path: Path | None,
    completed_company_keys: set[str],
    already_processed_count: int,
    show_progress: bool,
) -> _RunState:
    run_state = _RunState(
        output_path=output_path,
        completed_company_keys=completed_company_keys,
        already_processed_count=already_processed_count,
    )

    for raw_record in tqdm(
        records_to_process,
        total=len(records_to_process),
        desc="Enriching companies",
        unit="company",
        disable=not show_progress,
    ):
        _process_company(
            raw_record=raw_record,
            candidates_by_company=candidates_by_company,
            extractor=extractor,
            model=model,
            dry_run=dry_run,
            clock=clock,
            run_state=run_state,
        )

    return run_state


def _process_company(
    *,
    raw_record: Any,
    candidates_by_company: dict[str, list[dict[str, Any]]],
    extractor: CompanyEnrichmentExtractor | None,
    model: str,
    dry_run: bool,
    clock: Callable[[], str],
    run_state: _RunState,
) -> None:
    if not isinstance(raw_record, dict):
        run_state.skipped_count += 1
        return

    resume_key = _company_resume_key(raw_record)
    if resume_key is not None and resume_key in run_state.completed_company_keys:
        run_state.already_processed_count += 1
        return

    company_key = company_record_key(raw_record)
    enrichment_input = build_enrichment_input(
        raw_record,
        candidates_by_company.get(company_key, []),
    )
    if enrichment_input is None:
        run_state.skipped_count += 1
        return

    run_state.processable_count += 1
    if dry_run:
        return

    company = clean_scalar(raw_record.get("company"))
    enrichment_result = _extract_company(
        extractor,
        enrichment_input,
        run_state,
        model=model,
        company=company,
    )
    if enrichment_result is None:
        return

    enrichment_result, retry_warning = _retry_if_needed(
        extractor=extractor,
        enrichment_input=enrichment_input,
        enrichment_result=enrichment_result,
        run_state=run_state,
        model=model,
        company=company,
    )

    prepared = prepare_enrichment_for_record(
        company_record=raw_record,
        enrichment=enrichment_result.enrichment,
    )
    quality_warnings = tuple(
        warning
        for warning in (retry_warning, *prepared.quality_warnings)
        if warning is not None
    )
    if prepared.enrichment is None:
        run_state.quality_error_count += 1
        _append_sample(
            run_state.quality_error_samples,
            CompanyEnrichmentRunIssue(
                company=company,
                error_type="QualityError",
                message="; ".join(quality_warnings) or "No usable enrichment data.",
            ),
        )
        return

    _record_enrichment(
        run_state=run_state,
        record=build_enrichment_record(
            company_record=raw_record,
            enrichment=prepared.enrichment,
            model=model,
            enriched_at=clock(),
            quality_warnings=quality_warnings,
            llm_usage=enrichment_result.usage,
            llm_cost=enrichment_result.cost,
        ),
        company_key=resume_key,
    )


def _prepare_output_file(
    output_path: Path,
    *,
    dry_run: bool,
    restart: bool,
) -> set[str]:
    if dry_run:
        return set()
    if restart or not output_path.exists():
        write_jsonl(output_path, ())
        return set()
    return _completed_company_keys(read_jsonl(output_path))


def _completed_company_keys(records: list[Any]) -> set[str]:
    completed: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        company_key = clean_scalar(record.get("company_key"))
        if company_key is None:
            company_key = _company_resume_key(record)
        if company_key is not None:
            completed.add(company_key)
    return completed


def _pending_records(
    records_to_process: list[Any],
    *,
    completed_company_keys: set[str],
) -> tuple[list[Any], int]:
    pending: list[Any] = []
    already_processed_count = 0
    for raw_record in records_to_process:
        if not isinstance(raw_record, dict):
            pending.append(raw_record)
            continue
        company_key = _company_resume_key(raw_record)
        if company_key is not None and company_key in completed_company_keys:
            already_processed_count += 1
            continue
        pending.append(raw_record)
    return pending, already_processed_count


def _company_resume_key(company_record: dict[str, Any]) -> str | None:
    company = clean_scalar(company_record.get("company"))
    if company is None:
        return None
    return slugify(company)


def _record_enrichment(
    *,
    run_state: _RunState,
    record: dict[str, Any],
    company_key: str | None,
) -> None:
    run_state.records.append(record)
    if run_state.output_path is not None:
        append_jsonl(run_state.output_path, record)
    if company_key is not None:
        run_state.completed_company_keys.add(company_key)


def _retry_if_needed(
    *,
    extractor: CompanyEnrichmentExtractor | None,
    enrichment_input: dict[str, Any],
    enrichment_result: _EnrichmentCallResult,
    run_state: _RunState,
    model: str,
    company: str | None,
) -> tuple[_EnrichmentCallResult, str | None]:
    retry_reason = needs_quality_retry(enrichment_result.enrichment)
    if retry_reason is None:
        return enrichment_result, None

    retry_input = _build_quality_retry_input(
        enrichment_input,
        retry_reason,
        enrichment=enrichment_result.enrichment,
    )
    retry_result = _extract_company(
        extractor,
        retry_input,
        run_state,
        model=model,
        company=company,
    )
    if retry_result is None:
        return enrichment_result, "Quality retry failed; salvaged initial model result."
    combined_result = _combine_company_call_results(
        initial_result=enrichment_result,
        retry_result=retry_result,
        model=model,
        contact_retry=is_contact_quality_retry_reason(retry_reason),
    )
    if is_contact_quality_retry_reason(retry_reason) and not has_high_value_contact(
        combined_result.enrichment
    ):
        return combined_result, CONTACT_QUALITY_RETRY_UNRESOLVED_WARNING
    return combined_result, None


def _build_quality_retry_input(
    enrichment_input: dict[str, Any],
    retry_reason: str,
    *,
    enrichment: CompanyEnrichment,
) -> dict[str, Any]:
    retry_input = dict(enrichment_input)
    retry_details: dict[str, Any] = {
        "reason": retry_reason,
        "instructions": _quality_retry_instructions(retry_reason),
    }
    if is_contact_quality_retry_reason(retry_reason):
        retry_details["previous_contacts"] = _contact_retry_leads(enrichment)
    retry_input["quality_retry"] = {
        **retry_details,
    }
    return retry_input


def _quality_retry_instructions(retry_reason: str) -> str:
    if is_contact_quality_retry_reason(retry_reason):
        return (
            "The previous output did not include a named contact with a LinkedIn "
            "person profile or non-generic public work email. Use previous_contacts "
            "as leads. For every named lead, run targeted web searches such as "
            "\"{name}\" \"{company}\" LinkedIn, \"{name}\" \"{title}\" "
            "\"{company}\" LinkedIn, and site:linkedin.com/in \"{name}\" "
            "\"{company}\". Return LinkedIn person profile URLs when found. Search "
            "also for CTO, VP Engineering, Head of AI, Head of Data Science, ML lead, "
            "data engineering lead, technical founder, and technical hiring contacts. "
            "Preserve useful company facts from the prior result if you cannot improve "
            "them. Do not stop at about/team pages that only provide names and titles."
        )
    return (
        "The previous output relied too much on ATS/job-board sources. Search "
        "again for official company website, LinkedIn company page, reputable "
        "business/funding profiles, registries, or news. If non-ATS sources "
        "cannot be found, leave core company facts null, but keep ATS-supported "
        "AI hiring signals when useful."
    )


def _contact_retry_leads(enrichment: CompanyEnrichment) -> list[dict[str, Any]]:
    leads: list[dict[str, Any]] = []
    for contact in enrichment.model_dump(mode="json").get("contacts", []):
        if not isinstance(contact, dict):
            continue
        lead = {
            key: value
            for key, value in {
                "name": clean_scalar(contact.get("name")),
                "title": clean_scalar(contact.get("title")),
                "role": clean_scalar(contact.get("role")),
                "source_urls": contact.get("source_urls") or [],
            }.items()
            if value
        }
        if lead:
            leads.append(lead)
    return leads


def _extract_company(
    extractor: CompanyEnrichmentExtractor | None,
    enrichment_input: dict[str, Any],
    run_state: _RunState,
    *,
    model: str,
    company: str | None,
) -> _EnrichmentCallResult | None:
    try:
        assert extractor is not None
        raw_result = extractor(enrichment_input)
        raw_enrichment, usage = _unwrap_llm_call_result(raw_result)
        cost = _record_llm_usage(
            run_state=run_state,
            model=model,
            usage=usage,
            web_search_tool_calls=usage.tool_calls if usage else 0,
        )
        enrichment = CompanyEnrichment.model_validate(raw_enrichment)
        return _EnrichmentCallResult(enrichment=enrichment, usage=usage, cost=cost)
    except ValidationError as exc:
        run_state.validation_error_count += 1
        _append_sample(
            run_state.validation_error_samples,
            CompanyEnrichmentRunIssue(
                company=company,
                error_type=type(exc).__name__,
                message=_compact_error_message(exc),
            ),
        )
        return None
    except Exception as exc:  # noqa: BLE001 - one bad model call must not fail the batch.
        run_state.llm_error_count += 1
        _append_sample(
            run_state.llm_error_samples,
            CompanyEnrichmentRunIssue(
                company=company,
                error_type=type(exc).__name__,
                message=_compact_error_message(exc),
            ),
        )
        return None


def _append_sample(
    samples: list[CompanyEnrichmentRunIssue],
    issue: CompanyEnrichmentRunIssue,
    *,
    max_samples: int = 5,
) -> None:
    if len(samples) < max_samples:
        samples.append(issue)


def _compact_error_message(exc: Exception) -> str:
    return " ".join(str(exc).split())[:500]


def _unwrap_llm_call_result(raw_result: Any) -> tuple[Any, LLMUsage | None]:
    if isinstance(raw_result, LLMCallResult):
        return raw_result.output, raw_result.usage
    return raw_result, None


def _record_llm_usage(
    *,
    run_state: _RunState,
    model: str,
    usage: LLMUsage | None,
    web_search_tool_calls: int,
) -> LLMCostEstimate | None:
    if usage is None:
        return None

    run_state.llm_usage = add_usage(run_state.llm_usage, usage)
    cost = estimate_llm_cost(
        model=model,
        usage=usage,
        web_search_tool_calls=web_search_tool_calls,
    )
    if cost is None:
        return None
    if not cost.has_complete_pricing:
        run_state.llm_estimated_cost_usd = None
        run_state.llm_pricing_missing_models.add(model)
        return cost
    if run_state.llm_estimated_cost_usd is not None:
        run_state.llm_estimated_cost_usd += cost.total_cost_usd or 0.0
    return cost


def _combine_company_call_results(
    *,
    initial_result: _EnrichmentCallResult,
    retry_result: _EnrichmentCallResult,
    model: str,
    contact_retry: bool = False,
) -> _EnrichmentCallResult:
    enrichment = (
        _merge_contact_retry_enrichment(
            initial_result.enrichment,
            retry_result.enrichment,
        )
        if contact_retry
        else retry_result.enrichment
    )
    if initial_result.usage is None and retry_result.usage is None:
        return _EnrichmentCallResult(
            enrichment=enrichment,
            usage=None,
            cost=None,
        )

    combined_usage = add_usage(initial_result.usage, retry_result.usage)
    combined_cost = estimate_llm_cost(
        model=model,
        usage=combined_usage,
        web_search_tool_calls=combined_usage.tool_calls,
    )
    return _EnrichmentCallResult(
        enrichment=enrichment,
        usage=combined_usage,
        cost=combined_cost,
    )


def _merge_contact_retry_enrichment(
    initial_enrichment: CompanyEnrichment,
    retry_enrichment: CompanyEnrichment,
) -> CompanyEnrichment:
    merged = initial_enrichment.model_dump(mode="json")
    retry_dump = retry_enrichment.model_dump(mode="json")

    for field in (
        "company_description",
        "industry",
        "company_size",
        "founded_year",
        "company_type",
        "funding_summary",
        "ai_tech_forward_signal",
        "ai_tech_forward_reason",
    ):
        if merged.get(field) is None and retry_dump.get(field) is not None:
            merged[field] = retry_dump[field]

    for source_field in (
        "company_description_source_urls",
        "industry_source_urls",
        "company_size_source_urls",
        "founded_year_source_urls",
        "company_type_source_urls",
        "funding_summary_source_urls",
        "ai_tech_forward_source_urls",
        "source_urls",
    ):
        merged[source_field] = _unique_values(
            [*merged.get(source_field, []), *retry_dump.get(source_field, [])]
        )

    merged["contacts"] = _merge_contacts(
        retry_dump.get("contacts", []),
        merged.get("contacts", []),
    )
    return CompanyEnrichment.model_validate(merged)


def _merge_contacts(*contact_groups: list[Any]) -> list[dict[str, Any]]:
    contacts: list[dict[str, Any]] = []
    seen: set[str] = set()
    seen_names: set[str] = set()
    for group in contact_groups:
        for contact in group:
            if not isinstance(contact, dict):
                continue
            key = _contact_dedupe_key(contact)
            name = clean_scalar(contact.get("name"))
            name_key = name.casefold() if name is not None else None
            if name_key is not None and name_key in seen_names:
                continue
            if key in seen:
                continue
            seen.add(key)
            if name_key is not None:
                seen_names.add(name_key)
            contacts.append(contact)
    return contacts


def _contact_dedupe_key(contact: dict[str, Any]) -> str:
    for field in ("linkedin_url", "email"):
        value = clean_scalar(contact.get(field))
        if value is not None:
            return f"{field}:{value.casefold()}"
    values = [
        clean_scalar(contact.get(field)) or ""
        for field in ("name", "title", "role")
    ]
    return "lead:" + "|".join(value.casefold() for value in values)


def _unique_values(values: list[Any]) -> list[Any]:
    unique: list[Any] = []
    for value in values:
        if value not in unique:
            unique.append(value)
    return unique
