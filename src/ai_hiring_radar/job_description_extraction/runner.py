from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from tqdm import tqdm

from ai_hiring_radar.job_description_extraction.contracts import (
    JobDescriptionExtraction,
    JobDescriptionExtractionRunResult,
    JobDescriptionExtractor,
)
from ai_hiring_radar.job_description_extraction.dates import utc_now_iso
from ai_hiring_radar.job_description_extraction.inputs import build_extraction_input
from ai_hiring_radar.job_description_extraction.records import build_extraction_record
from ai_hiring_radar.job_description_extraction.text import clean_scalar
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
    write_jsonl,
)


def run_job_description_extraction(
    collection_date: str,
    *,
    extractor: JobDescriptionExtractor | None,
    model: str,
    data_dir: Path = DEFAULT_DATA_DIR,
    limit: int | None = None,
    dry_run: bool = False,
    clock: Callable[[], str] = utc_now_iso,
    show_progress: bool = True,
    restart: bool = False,
) -> JobDescriptionExtractionRunResult:
    normalized_date = format_date(collection_date)
    input_filename = f"job_candidates_{normalized_date}.jsonl"
    output_filename = f"job_description_extracts_{normalized_date}.jsonl"
    raw_records = read_processed_jsonl(input_filename, data_dir=data_dir)
    records_to_process = raw_records[:limit] if limit is not None else raw_records
    output_path = processed_dir(data_dir=data_dir) / output_filename

    if not dry_run and extractor is None:
        raise ValueError("extractor is required unless dry_run is true.")

    completed_job_ids = _prepare_output_file(
        output_path,
        dry_run=dry_run,
        restart=restart,
    )
    pending_records, already_processed_count = _pending_records(
        records_to_process,
        completed_job_ids=completed_job_ids,
    )

    run_state = _run_extraction_batch(
        records_to_process=pending_records,
        extractor=extractor,
        model=model,
        dry_run=dry_run,
        clock=clock,
        output_path=None if dry_run else output_path,
        completed_job_ids=completed_job_ids,
        already_processed_count=already_processed_count,
        show_progress=show_progress,
    )

    return JobDescriptionExtractionRunResult(
        collection_date=normalized_date,
        model=model,
        input_path=processed_dir(data_dir=data_dir) / input_filename,
        output_path=output_path,
        candidates_read=len(records_to_process),
        processable_count=run_state.processable_count,
        extracted_count=len(run_state.records),
        skipped_count=run_state.skipped_count,
        validation_error_count=run_state.validation_error_count,
        llm_error_count=run_state.llm_error_count,
        already_processed_count=run_state.already_processed_count,
        llm_usage=run_state.llm_usage,
        llm_estimated_cost_usd=run_state.llm_estimated_cost_usd,
        llm_pricing_missing_models=tuple(sorted(run_state.llm_pricing_missing_models)),
        dry_run=dry_run,
    )


class _RunState:
    def __init__(
        self,
        *,
        output_path: Path | None,
        completed_job_ids: set[str],
        already_processed_count: int,
    ) -> None:
        self.records: list[dict[str, Any]] = []
        self.output_path = output_path
        self.completed_job_ids = completed_job_ids
        self.already_processed_count = already_processed_count
        self.processable_count = 0
        self.skipped_count = 0
        self.validation_error_count = 0
        self.llm_error_count = 0
        self.llm_usage = LLMUsage()
        self.llm_estimated_cost_usd: float | None = 0.0
        self.llm_pricing_missing_models: set[str] = set()


@dataclass(frozen=True)
class _ExtractionCallResult:
    extraction: JobDescriptionExtraction
    usage: LLMUsage | None
    cost: LLMCostEstimate | None


def _run_extraction_batch(
    *,
    records_to_process: list[Any],
    extractor: JobDescriptionExtractor | None,
    model: str,
    dry_run: bool,
    clock: Callable[[], str],
    output_path: Path | None,
    completed_job_ids: set[str],
    already_processed_count: int,
    show_progress: bool,
) -> _RunState:
    run_state = _RunState(
        output_path=output_path,
        completed_job_ids=completed_job_ids,
        already_processed_count=already_processed_count,
    )

    for raw_record in tqdm(
        records_to_process,
        total=len(records_to_process),
        desc="Extracting job descriptions",
        unit="candidate",
        disable=not show_progress,
    ):
        _process_candidate(
            raw_record=raw_record,
            extractor=extractor,
            model=model,
            dry_run=dry_run,
            clock=clock,
            run_state=run_state,
        )

    return run_state


def _process_candidate(
    *,
    raw_record: Any,
    extractor: JobDescriptionExtractor | None,
    model: str,
    dry_run: bool,
    clock: Callable[[], str],
    run_state: _RunState,
) -> None:
    if not isinstance(raw_record, dict):
        run_state.skipped_count += 1
        return

    candidate_key = _candidate_resume_key(raw_record)
    if candidate_key is not None and candidate_key in run_state.completed_job_ids:
        run_state.already_processed_count += 1
        return

    extraction_input = build_extraction_input(raw_record)
    if extraction_input is None:
        run_state.skipped_count += 1
        return

    run_state.processable_count += 1
    if dry_run:
        return

    extraction_result = _extract_candidate(
        extractor,
        extraction_input,
        run_state,
        model=model,
    )
    if extraction_result is None:
        return

    _record_extraction(
        run_state=run_state,
        record=build_extraction_record(
            candidate=raw_record,
            extraction=extraction_result.extraction,
            model=model,
            extracted_at=clock(),
            llm_usage=extraction_result.usage,
            llm_cost=extraction_result.cost,
        ),
        candidate_key=candidate_key,
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
    return _completed_job_ids(read_jsonl(output_path))


def _completed_job_ids(records: list[Any]) -> set[str]:
    completed: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        job_id = clean_scalar(record.get("job_id"))
        if job_id is not None:
            completed.add(job_id)
    return completed


def _pending_records(
    records_to_process: list[Any],
    *,
    completed_job_ids: set[str],
) -> tuple[list[Any], int]:
    pending: list[Any] = []
    already_processed_count = 0
    for raw_record in records_to_process:
        if not isinstance(raw_record, dict):
            pending.append(raw_record)
            continue
        candidate_key = _candidate_resume_key(raw_record)
        if candidate_key is not None and candidate_key in completed_job_ids:
            already_processed_count += 1
            continue
        pending.append(raw_record)
    return pending, already_processed_count


def _candidate_resume_key(candidate: dict[str, Any]) -> str | None:
    return clean_scalar(candidate.get("job_id"))


def _record_extraction(
    *,
    run_state: _RunState,
    record: dict[str, Any],
    candidate_key: str | None,
) -> None:
    run_state.records.append(record)
    if run_state.output_path is not None:
        append_jsonl(run_state.output_path, record)
    if candidate_key is not None:
        run_state.completed_job_ids.add(candidate_key)


def _extract_candidate(
    extractor: JobDescriptionExtractor | None,
    extraction_input: dict[str, Any],
    run_state: _RunState,
    *,
    model: str,
) -> _ExtractionCallResult | None:
    try:
        assert extractor is not None
        raw_result = extractor(extraction_input)
        raw_extraction, usage = _unwrap_llm_call_result(raw_result)
        cost = _record_llm_usage(
            run_state=run_state,
            model=model,
            usage=usage,
            web_search_tool_calls=0,
        )
        extraction = JobDescriptionExtraction.model_validate(raw_extraction)
        return _ExtractionCallResult(extraction=extraction, usage=usage, cost=cost)
    except ValidationError:
        run_state.validation_error_count += 1
        return None
    except Exception:  # noqa: BLE001 - one bad model call must not fail the batch.
        run_state.llm_error_count += 1
        return None


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
