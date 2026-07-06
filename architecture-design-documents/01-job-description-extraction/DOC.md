# Job Description Extraction

## Status

Accepted

## Context

The Notion page `Obogatitev hiring podatkov` defines a need to enrich hiring data so we can understand the actual need behind each company/job pair. This design is scoped only to retrieving and storing job description data, then processing available job data to extract the datapoints needed from job descriptions.

The existing project is a Python CLI application that discovers AI hiring signals, stores raw provider responses as JSON, normalizes them into `job_candidates_YYYY-MM-DD.jsonl`, aggregates company-level title-only records, and exports review files. Current company output is intentionally title-only, but several ATS normalizers already carry job descriptions through normalized candidate records.

This feature adds a separate, re-runnable extraction step. Operators can collect data, process candidates, and then run job description extraction independently. Prompt/model changes should not require re-fetching ATS data.

## Goals

1. Retrieve and store full job description data where the public ATS provider makes it available.
2. Add Ashby full job description retrieval if its public job board endpoint supports detail data.
3. Extract structured datapoints with an LLM using a Pydantic output model.
4. Allow the extraction model to be changed through configuration without changing extraction code.
5. Write extracted records to `data/processed/job_description_extracts_YYYY-MM-DD.jsonl`.
6. Extract only data that exists in available job data. Do not guess, infer from external knowledge, or estimate job age.
7. Keep the extraction output small: no full job description text, no evidence snippets, and no confidence scores in v1.

## Non-Goals

1. Company enrichment such as company description, size, age, type, funding, or AI/tech-forward signal.
2. Websearch enrichment for contacts.
3. LinkedIn page scraping.
4. Final company priority, offer recommendation, or outreach reason generation.
5. Database storage, migrations, server APIs, queues, or background workers.
6. Export/report redesign for company review files.
7. Job age estimation from first seen/last seen or collection history.

## Requirements

Functional requirements:

1. Extraction must be LLM-based.
2. Extraction must validate output with a Pydantic model.
3. Enum-valued fields must use explicit enum classes, not free-form strings.
4. Missing values must be stored as `null` or an empty list.
5. Extraction input may use all available normalized job data, not only the description text.
6. Contacts must be extracted only when present in the job data/job description.
7. Job age must not be estimated. Explicit `posted_at` or `updated_at` values may be stored when available from ATS payloads or text.
8. The stored extraction record must not include the full job description.
9. The extraction step must be runnable separately after `process`.

Non-functional requirements:

1. Preserve the current raw-first storage pattern.
2. Keep implementation in the existing CLI/file pipeline.
3. Keep model switching simple through one config value.
4. Make extraction deterministic at the application layer: same input record, prompt version, and model name should produce one persisted output record per run.
5. Make validation failures visible without failing the whole batch.

## Current State

Relevant existing modules:

1. `src/ai_hiring_radar/cli.py` owns the Typer CLI and synchronous orchestration.
2. `src/ai_hiring_radar/storage_json.py` owns raw, processed, and export file paths plus JSON/JSONL helpers.
3. `src/ai_hiring_radar/normalize.py` turns raw search and ATS responses into `job_candidate` records.
4. `src/ai_hiring_radar/sources/greenhouse.py` retrieves Greenhouse public job board data with `content=true`.
5. `src/ai_hiring_radar/sources/lever.py` retrieves Lever public postings with `mode=json`.
6. `src/ai_hiring_radar/sources/personio.py` retrieves Personio public XML feeds.
7. `src/ai_hiring_radar/sources/ashby.py` retrieves Ashby job board listings through an undocumented hosted GraphQL endpoint.

Current description support:

1. Greenhouse normalizes `content` into `description` and `updated_at` into `source_updated_at`.
2. Lever normalizes `description`, `descriptionBody`, `additional`, or `descriptionPlain` into `description`, stores `description_plain`, and stores `createdAt` in `source_created_at`.
3. Personio normalizes XML `jobDescriptions` into `description` and `job_description_sections`.
4. Ashby currently normalizes listing fields only and does not fetch full descriptions.

Current limitations:

1. `EvidenceQuality` only has title-only values.
2. Aggregation and export ignore descriptions.
3. There is no LLM dependency, LLM client abstraction, or structured extraction module.
4. There is no database or migration layer.
5. There is no retry/rate-limit abstraction beyond provider-specific collection behavior.

## Proposed Design

Add a separate job description extraction stage that reads processed `job_candidate` records, builds an extraction input from all available normalized job fields, calls a Pydantic AI agent configured with a Pydantic output model, validates the result, and writes one compact JSONL extraction record per successfully processed job candidate.

Use `pydantic-ai` for LLM extraction because the project already depends on Pydantic, Pydantic AI accepts Pydantic models as structured output types, and model switching can be done with a provider/model string such as `openai:gpt-5-mini` or another provider-supported model string.

The extraction stage remains separate from `process_collection` so operators can run it step by step:

1. `collect-*` retrieves public search/ATS data.
2. `process` normalizes raw data into candidates.
3. `extract-job-descriptions` extracts structured JD datapoints from processed candidates.

This design avoids storing full JD text in extraction outputs. Full text remains only in existing raw or normalized intermediate artifacts where providers already return it.

## Data Model

### Pydantic Output Model

The LLM output contract lives in a new module, proposed as `src/ai_hiring_radar/job_description_extraction.py`.

```python
from enum import StrEnum

from pydantic import BaseModel, Field


class WorkplaceMode(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"


class AiTeamContext(StrEnum):
    FIRST_AI_PERSON = "first_ai_person"
    EXISTING_AI_TEAM = "existing_ai_team"


class DeliveryContext(StrEnum):
    INTERNAL = "internal"
    EXTERNAL_CLIENTS = "external_clients"
    MIXED = "mixed"


class JDContactRole(StrEnum):
    HIRING_MANAGER = "hiring_manager"
    CTO = "cto"
    CEO_FOUNDER = "ceo_founder"
    HEAD_OF_AI_DATA_ENGINEERING = "head_of_ai_data_engineering"
    RECRUITER = "recruiter"
    OTHER = "other"


class JDContact(BaseModel):
    name: str | None = None
    role: JDContactRole | None = None
    title: str | None = None
    email: str | None = None
    linkedin_url: str | None = None


class JobDescriptionExtraction(BaseModel):
    workplace_mode: WorkplaceMode | None = Field(default=None)
    ai_team_context: AiTeamContext | None = Field(default=None)
    delivery_context: DeliveryContext | None = Field(default=None)
    contacts: list[JDContact] = Field(default_factory=list)
    posted_at: str | None = Field(default=None)
    updated_at: str | None = Field(default=None)
```

Field rules:

1. `workplace_mode` is populated only when available data states or strongly indicates remote, hybrid, or onsite work.
2. `ai_team_context` is populated only when the job data says this is the first AI person/hire or part of an existing AI/data/engineering team.
3. `delivery_context` is populated only when the job data indicates internal product/development, external client work, or mixed delivery.
4. `contacts` contains only people or contact details present in available job data.
5. `posted_at` and `updated_at` are copied or normalized only from explicit available source data. No age or first-seen estimate is calculated.

### Persisted Extraction Record

The persisted JSONL record wraps the validated LLM output with job metadata.

```json
{
  "record_type": "job_description_extract",
  "extraction_version": "v1",
  "prompt_version": "v1",
  "model": "openai:gpt-5-mini",
  "job_id": "...",
  "source": "lever",
  "platform": "lever",
  "platform_company_slug": "acme-ai",
  "platform_job_id": "job-ai-engineer",
  "company_normalized": "Acme Ai",
  "job_title_raw": "Senior AI Engineer",
  "job_url": "https://jobs.lever.co/acme-ai/job-ai-engineer",
  "workplace_mode": "hybrid",
  "ai_team_context": null,
  "delivery_context": "internal",
  "contacts": [],
  "posted_at": "2026-06-01T00:00:00Z",
  "updated_at": null,
  "extracted_at": "2026-07-02T10:00:00Z"
}
```

The record intentionally excludes:

1. Full job description text.
2. Evidence snippets.
3. Confidence scores.
4. LLM raw response text.

## Interfaces

### Dependency

Add `pydantic-ai` to `pyproject.toml` runtime dependencies.

### Configuration

Add settings in `src/ai_hiring_radar/config.py`:

1. `JOB_DESCRIPTION_EXTRACTION_MODEL`, defaulting to a small configured model string.
2. Provider API keys are read by the provider integration in `pydantic-ai` through its expected environment variables.

The extraction module receives the model string as an argument so tests can inject a fake extractor without calling a real model.

### CLI

Add a Typer command:

```bash
uv run ai-hiring-radar extract-job-descriptions --date YYYY-MM-DD
```

Expected behavior:

1. Reads `data/processed/job_candidates_YYYY-MM-DD.jsonl`.
2. Skips candidates with no useful description or ATS job data for extraction.
3. Calls the extractor for each processable candidate.
4. Writes `data/processed/job_description_extracts_YYYY-MM-DD.jsonl`.
5. Prints counts: candidates read, extracted, skipped, validation errors, LLM errors, output path.

Optional flags can be added if useful during implementation:

1. `--limit N` for small runs.
2. `--model MODEL` to override config for one run.
3. `--dry-run` to print planned candidate count without model calls.

### Storage

Add helper functions in `storage_json.py` only if needed for naming consistency:

1. `write_job_description_extracts(collection_date, records, data_dir=...)`.
2. Or use existing `write_processed_jsonl` directly from the extraction command.

## Execution Flow

1. Operator runs provider collection commands. Greenhouse, Lever, and Personio already retrieve descriptions through board feeds. Ashby collection is extended to try job detail retrieval.
2. Operator runs `process --date YYYY-MM-DD`.
3. `process_collection` writes normalized candidates, including available description and metadata fields.
4. Operator runs `extract-job-descriptions --date YYYY-MM-DD`.
5. The extraction command loads processed candidate records.
6. For each candidate, the command builds an extraction input from all available normalized fields, including title, description, description sections, location, employment type, team, department, ATS dates, job URL, and provider metadata.
7. The Pydantic AI agent receives the extraction prompt and the candidate input.
8. Pydantic validates the model output.
9. The command writes compact extraction records to JSONL.
10. Batch summary is printed to the console.

### Prompt Contract

The prompt must include these rules:

```text
Extract structured information from the provided job data.
Use all provided fields, not only the job description.
Return only information explicitly present in the provided job data.
Do not use external knowledge.
Do not infer from company name, industry assumptions, or general role stereotypes.
If a field is not present, return null or an empty list.
Do not estimate job age.
Contacts must only include people or contact details present in the provided job data.
```

### Ashby Retrieval

Ashby collection should be extended to try full JD retrieval for each listing returned by the current job board query.

Preferred implementation shape:

1. Keep the current board listing request.
2. Add an Ashby job detail request if a public hosted GraphQL operation or endpoint can be identified.
3. Store detail responses in the raw ATS wrapper alongside the listing response, for example under `job_detail_responses` keyed by `platform_job_id`.
4. Normalize Ashby descriptions into the same `description` field used by other providers.
5. If detail retrieval fails for a job, store a per-job error in the raw wrapper or manifest and continue collecting other jobs.

Ashby detail failures should not fail the whole board collection because the endpoint is undocumented and may vary.

## Error Handling

Candidate skip cases:

1. Missing `job_id`.
2. Missing useful extraction input.
3. Non-dict or malformed candidate record.

LLM/validation failure cases:

1. If a model call fails, record an error count and continue.
2. If Pydantic validation fails, record an error count and continue.
3. Failed candidates are not written to the successful extracts file in v1.
4. A later follow-up may add a separate error JSONL if batch debugging requires it.

Date handling:

1. Accept explicit source dates in ISO strings, timestamps, or provider-native strings.
2. Normalize obvious timestamps where implementation cost is low, especially Lever millisecond `createdAt`.
3. If a date cannot be parsed safely, pass it to the LLM as source context but leave the stored field `null` unless the model returns a valid value.
4. Do not calculate `days_live`.

Retries:

1. No custom retry framework in v1.
2. Provider SDK/client defaults may apply.
3. Failed records can be retried by re-running `extract-job-descriptions` after limiting or filtering support is added.

## Observability

Console output should include:

1. Collection date.
2. Input candidate path.
3. Output extract path.
4. Model string.
5. Candidates read.
6. Candidates skipped.
7. Successful extractions.
8. LLM errors.
9. Validation errors.

Persisted records include `extraction_version`, `prompt_version`, `model`, and `extracted_at` so extraction outputs can be compared across future prompt/model changes.

## Testing

Unit tests:

1. Pydantic model accepts valid enum values and rejects invalid values.
2. Empty/missing values become `None` or `[]`.
3. Extraction record builder does not include full description text.
4. Extraction input builder includes all relevant normalized candidate fields, not only `description`.
5. Date normalization handles Lever millisecond timestamps when implemented.

Command tests:

1. `extract-job-descriptions` reads candidate JSONL and writes extract JSONL.
2. Fake extractor returns deterministic `JobDescriptionExtraction` objects.
3. Skipped candidates and validation failures do not fail the whole command.

Provider tests:

1. Existing Greenhouse, Lever, and Personio tests continue to verify description preservation.
2. Ashby tests cover the new detail retrieval path if a public detail endpoint is identified.
3. Ashby tests cover per-job detail failure without failing board collection.

Manual verification:

1. Run `uv run pytest`.
2. Run a small extraction batch with `--limit` against a known processed date.
3. Inspect `data/processed/job_description_extracts_YYYY-MM-DD.jsonl` to verify no full JD text is persisted.

## Rollout

1. Add extraction code behind a new CLI command only. Existing `collect`, `process`, `export`, and `run` behavior remains unchanged.
2. Add dependency and config without requiring users to run extraction unless they set a model/API key and call the command.
3. Keep output in a new JSONL file to avoid changing existing company exports.
4. After review, a follow-up feature can merge extracted signals into company-level prioritization and exports.

## Task Breakdown

### Dependency Graph

Task 1 is the foundation for Tasks 2 and 3. Task 4 depends on Tasks 2 and 3. Task 5 is provider-specific and can land independently after Task 1, but should be completed before relying on Ashby extraction quality. Task 6 lands after Tasks 4 and 5.

### Task 1: Add Extraction Data Contracts

Scope:

1. Add `src/ai_hiring_radar/job_description_extraction.py`.
2. Define enum classes: `WorkplaceMode`, `AiTeamContext`, `DeliveryContext`, `JDContactRole`.
3. Define Pydantic models: `JDContact`, `JobDescriptionExtraction`.
4. Add prompt text or prompt builder with the locked no-guessing rules.
5. Add pure helper functions to build compact extraction records from a candidate and validated extraction output.
6. Ensure record builders do not persist full job description text.

Files likely changed:

1. `src/ai_hiring_radar/job_description_extraction.py`
2. `tests/test_job_description_extraction.py`

Verification:

1. Unit tests validate enum acceptance/rejection.
2. Unit tests validate missing values become `None` or `[]`.
3. Unit tests validate the persisted record shape excludes `description`, `description_plain`, and `job_description_sections`.

### Task 2: Add JSONL Extraction Runner With Injectable Extractor

Scope:

1. Add a runner that reads `job_candidates_YYYY-MM-DD.jsonl`.
2. Build extraction input from all useful normalized candidate data, not only `description`.
3. Skip malformed candidates and candidates without useful extraction input.
4. Accept an injectable extractor callable/protocol so tests do not call a real LLM.
5. Write `job_description_extracts_YYYY-MM-DD.jsonl`.
6. Return a result dataclass with counts and output path.

Files likely changed:

1. `src/ai_hiring_radar/job_description_extraction.py`
2. `src/ai_hiring_radar/storage_json.py` if a naming helper is useful
3. `tests/test_job_description_extraction.py`

Verification:

1. Unit tests use a fake extractor and verify output JSONL.
2. Unit tests verify skipped, successful, and failed records are counted correctly.
3. Unit tests verify extraction input includes title, location, team, department, dates, job URL, and provider metadata when present.

### Task 3: Add Pydantic AI Adapter And Config

Scope:

1. Add `pydantic-ai` dependency.
2. Add `JOB_DESCRIPTION_EXTRACTION_MODEL` config, defaulting to the chosen model string.
3. Add a real extractor adapter that creates a Pydantic AI `Agent` with `JobDescriptionExtraction` as `output_type`.
4. Keep model string injectable for CLI overrides and tests.
5. Avoid real network calls in tests.

Files likely changed:

1. `pyproject.toml`
2. `src/ai_hiring_radar/config.py`
3. `src/ai_hiring_radar/job_description_extraction.py`
4. `.env.example` if present
5. `tests/test_job_description_extraction.py`

Verification:

1. Tests verify config reads the model setting.
2. Tests verify adapter construction passes the configured model string.
3. Existing tests still pass without requiring provider API keys.

### Task 4: Add CLI Command

Scope:

1. Add `extract-job-descriptions --date YYYY-MM-DD` to `src/ai_hiring_radar/cli.py`.
2. Add optional `--limit`, `--model`, and `--dry-run` flags if they remain small.
3. Wire CLI command to the JSONL runner and Pydantic AI adapter.
4. Print collection date, model, input path, output path, read count, skipped count, success count, LLM error count, and validation error count.

Files likely changed:

1. `src/ai_hiring_radar/cli.py`
2. `tests/test_cli.py` or existing CLI-related tests if present
3. `tests/test_job_description_extraction.py` if CLI tests live there

Verification:

1. CLI test uses fake extraction path or monkeypatched runner.
2. Dry run does not call the model and does not write extracts.
3. Existing CLI commands keep working.

### Task 5: Add Ashby Full JD Retrieval Attempt

Scope:

1. Investigate Ashby public hosted GraphQL detail operation or public job detail endpoint.
2. Extend Ashby collection to request job detail data when possible.
3. Store detail responses in the raw Ashby wrapper alongside board listing data.
4. Normalize Ashby detail text into `description`.
5. Continue board collection when individual detail requests fail.

Files likely changed:

1. `src/ai_hiring_radar/sources/ashby.py`
2. `src/ai_hiring_radar/normalize.py`
3. `tests/test_ashby.py`

Verification:

1. Ashby tests cover successful detail retrieval and normalized `description`.
2. Ashby tests cover per-job detail failure while preserving listing collection.
3. Existing Ashby discovery and collection tests keep passing.

### Task 6: Documentation Update

Scope:

1. Update `README.md` with the new extraction command.
2. Document the required model config environment variable.
3. Document the step-by-step flow: collect, process, extract.
4. Document that output JSONL does not include full JD text.

Files likely changed:

1. `README.md`
2. `.env.example` if not already updated in Task 3

Verification:

1. Command examples are copy-pasteable.
2. Documentation matches actual CLI flags.

## Open Questions

None. Phase 1 decisions are locked.
