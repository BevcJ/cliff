# Company Inspection UI

## Status

Draft

## Context

The project now has four processed data layers for one collection date:

1. `companies_YYYY-MM-DD.jsonl` from the existing company aggregation step.
2. `job_candidates_YYYY-MM-DD.jsonl` from normalized and deduplicated job candidates.
3. `job_description_extracts_YYYY-MM-DD.jsonl` from structured job-description extraction.
4. `company_enrichment_extracts_YYYY-MM-DD.jsonl` from company web enrichment.

The current final review flow still exports title-only CSV and Markdown files through `src/ai_hiring_radar/export.py`. That flow is useful for static review, but it does not let an operator interactively filter enriched data or inspect why a company looks interesting.

The immediate need is a local read-only inspection frontend. Operators should be able to start from aggregated company-level data, filter by important enrichment signals, and then drill into company and job details. This is similar to export in that it prepares review-oriented output from processed JSONL files, but it is not a final sales report and should not replace existing title-only exports.

## Goals

1. Add a local Streamlit inspection UI for processed hiring data.
2. Keep existing JSONL files as canonical data sources.
3. Build company-level inspection view models in Python before rendering the UI.
4. Support required filters for workplace mode, AI team context, delivery context, company type, and company size.
5. Show an aggregate company table with useful filtering, sorting, and search.
6. Let operators select a company and inspect company facts, job signals, contacts, evidence URLs, and raw debug data.
7. Keep V1 read-only: no editing, notes, persisted review status changes, or CRM workflow.
8. Handle missing enrichment files gracefully so partial pipeline runs can still be inspected.

## Non-Goals

1. Final company prioritization, score generation, offer recommendation, or outreach reason generation.
2. Browser-side joining of source JSONL files.
3. Persisting a merged company intelligence JSONL file in V1.
4. Multi-user deployment, authentication, authorization, or hosted infrastructure.
5. Direct API server or database layer.
6. Editing `review_status`, saving notes, or marking companies as contacted.
7. Running collection, extraction, or enrichment from the UI.
8. Replacing existing title-only exports.

## Requirements

Functional requirements:

1. The UI must load data for a selected collection date.
2. The loader must read `companies_YYYY-MM-DD.jsonl` as the base company list.
3. The loader must read `job_candidates_YYYY-MM-DD.jsonl` when available and attach compact job details by company.
4. The loader must read `job_description_extracts_YYYY-MM-DD.jsonl` when available and attach structured job signals by `job_id`.
5. The loader must read `company_enrichment_extracts_YYYY-MM-DD.jsonl` when available and attach company facts by normalized company key.
6. The loader must aggregate structured job extraction values to company-level lists:
   - `workplace_modes`
   - `ai_team_contexts`
   - `delivery_contexts`
7. The UI must support filtering by:
   - workplace mode: `remote`, `hybrid`, `onsite`
   - AI team context: `first_ai_person`, `existing_ai_team`
   - delivery context: `internal`, `external_clients`, `mixed`
   - company type: `product_company`, `agency_consulting`, `traditional_company`, `ai_native`, `other`
   - company size as raw sourced text in V1
8. The UI should also support useful optional filters where data exists:
   - country
   - role classification
   - source/platform
   - AI tech-forward signal
   - has contacts
   - has job-description extracts
   - has company enrichment
   - free-text search over company, titles, industry, and description
9. The company detail view must show company-level enrichment fields and source URLs.
10. The company detail view must show job-level rows and extracted signals per job.
11. The company detail view must show contacts from both company enrichment and job-description extraction.
12. The UI may show full job descriptions only in per-job detail sections, never in aggregate company rows.

Non-functional requirements:

1. The frontend must not implement the canonical joining or aggregation logic.
2. The Python loader must be unit-testable without Streamlit.
3. Missing optional files must not prevent the UI from loading base company data.
4. The implementation should remain local-first and file-first.
5. The UI should run with one command from the existing CLI.
6. The implementation should be small and avoid introducing a full JavaScript frontend stack.

## Current State

Relevant existing modules:

1. `src/ai_hiring_radar/normalize.py` writes `job_candidates_YYYY-MM-DD.jsonl` and `companies_YYYY-MM-DD.jsonl`.
2. `src/ai_hiring_radar/aggregate.py` aggregates candidates into title-only company records.
3. `src/ai_hiring_radar/export.py` reads company records and writes title-only CSV/Markdown review files.
4. `src/ai_hiring_radar/job_description_extraction/*` writes job-level structured extraction records.
5. `src/ai_hiring_radar/company_enrichment/*` writes company-level structured enrichment records.
6. `src/ai_hiring_radar/storage_json.py` provides JSONL read/write helpers and processed/export directory paths.
7. `src/ai_hiring_radar/cli.py` owns the Typer CLI.

Current processed files:

1. `data/processed/companies_YYYY-MM-DD.jsonl`
2. `data/processed/job_candidates_YYYY-MM-DD.jsonl`
3. `data/processed/job_description_extracts_YYYY-MM-DD.jsonl`
4. `data/processed/company_enrichment_extracts_YYYY-MM-DD.jsonl`

Current limitations:

1. Existing exports only use `companies_YYYY-MM-DD.jsonl`.
2. There is no interactive filtering UI.
3. There is no shared inspection view model joining company, job, JD extraction, and company enrichment data.
4. The richer manually written `pareto_ai_outsourcing_prospects_*` reports are not generated by code.
5. Operators cannot easily filter by workplace mode, delivery context, AI team context, company type, or company size.

## Proposed Design

Add a local Streamlit UI backed by a pure Python inspection loader.

The inspection loader owns all joining and aggregation logic. It reads processed JSONL files for one collection date, normalizes company keys with the same project conventions used by aggregation, and returns a list of company-level view models. The Streamlit app receives these view models and only handles display, filtering, sorting, and drilldown rendering.

Selected architecture:

```text
processed JSONL files
  -> inspection loader / merger      # Python-owned canonical view model construction
  -> Streamlit app state             # UI filtering and selected company state
  -> aggregate table + detail panels # read-only inspection
```

This is intentionally similar to export, but the output target is interactive UI state instead of static CSV/Markdown files. The design avoids creating a merged persisted file in V1 so operators can inspect partial and rerun outputs without introducing another artifact to manage.

Implementation shape:

1. Add `src/ai_hiring_radar/inspection.py` for pure data loading, joining, aggregation, and view model construction.
2. Add `src/ai_hiring_radar/inspection_app.py` for the Streamlit UI.
3. Add `streamlit` as a runtime dependency.
4. Add `inspect --date YYYY-MM-DD` to the Typer CLI. The command launches Streamlit against `inspection_app.py` with the requested date.

## Data Model

### Company Inspection View Model

The inspection view model is not persisted in V1. It is built in memory by `inspection.py`.

Representative shape:

```json
{
  "company": "Ailylabs",
  "company_key": "ailylabs",
  "countries": ["Spain", "Mexico", "United States"],
  "role_classification": "AI Execution Role",
  "ai_execution_titles": ["Applied AI Engineer"],
  "ai_product_titles": [],
  "ai_role_title_counts": [
    {"title": "AI DI Engineering Manager", "count": 1}
  ],
  "matched_search_terms": ["title contains AI", "Applied AI Engineer"],
  "sources": ["personio"],
  "evidence_urls": ["https://ailylabs.jobs.personio.com"],
  "evidence_quality": ["title_only_ats_listing"],
  "needs_review": true,
  "review_status": "new",
  "why_interesting": "...",

  "workplace_modes": ["hybrid", "remote"],
  "ai_team_contexts": ["existing_ai_team"],
  "delivery_contexts": ["internal", "external_clients"],

  "company_description": "...",
  "industry": "...",
  "company_size": "101-500",
  "founded_year": 2018,
  "company_type": "ai_native",
  "funding_summary": null,
  "ai_tech_forward_signal": "strong",
  "ai_tech_forward_reason": "...",
  "company_source_urls": ["https://example.com/about"],

  "contacts": [],
  "company_contacts": [],
  "job_contacts": [],

  "job_count": 13,
  "job_description_extract_count": 4,
  "has_company_enrichment": true,
  "has_job_description_extracts": true,
  "has_contacts": false,

  "jobs": []
}
```

### Job Inspection View Model

Each company view model includes compact job view models.

Representative shape:

```json
{
  "job_id": "...",
  "job_title_raw": "AI DI Engineering Manager",
  "job_title_normalized": "AI Engineer",
  "job_url": "https://ailylabs.jobs.personio.com",
  "source_url": "https://ailylabs.jobs.personio.com",
  "platform": "personio",
  "source": "personio",
  "country": "Spain",
  "location": "Barcelona",
  "team": "Engineering",
  "department": "AI",
  "employment_type": "full-time",
  "workplace_mode": "hybrid",
  "ai_team_context": "existing_ai_team",
  "delivery_context": "external_clients",
  "contacts": [],
  "posted_at": null,
  "updated_at": null,
  "has_description": true,
  "description": "..."
}
```

Field rules:

1. Company-level list fields preserve unique non-null values in input order.
2. Job-level extraction values remain attached to their original jobs.
3. Full job description text is allowed only inside job detail state and should be collapsed by default in the UI.
4. Company enrichment fields are copied from `company_enrichment_extracts_YYYY-MM-DD.jsonl` when a matching company enrichment record exists.
5. Contact lists are deduped by email, then LinkedIn URL, then name/title/role.
6. `company_size` uses sourced sortable buckets: `0-50`, `51-100`, `101-500`, or `501+`.

## Interfaces

### Dependency

Add `streamlit` to `pyproject.toml` runtime dependencies.

### CLI

Add a Typer command:

```bash
uv run ai-hiring-radar inspect --date YYYY-MM-DD
```

Expected behavior:

1. Validates the date format.
2. Launches the Streamlit app with the collection date in app configuration or environment state.
3. The Streamlit app loads processed files for that date and renders the inspection UI.
4. If required base companies file is missing, the app shows a clear error.
5. If optional files are missing, the app shows warnings and disables/empties related filters.

### Python Loader

New public functions in `src/ai_hiring_radar/inspection.py`:

```python
def load_company_inspection_data(
    collection_date: str,
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
) -> CompanyInspectionDataset:
    ...
```

Suggested supporting dataclasses:

```python
@dataclass(frozen=True)
class InspectionInputPaths:
    companies_path: Path
    candidates_path: Path
    job_description_extracts_path: Path
    company_enrichment_extracts_path: Path


@dataclass(frozen=True)
class CompanyInspectionDataset:
    collection_date: str
    records: list[dict[str, Any]]
    paths: InspectionInputPaths
    missing_optional_files: list[Path]
```

### Streamlit App

New module:

```text
src/ai_hiring_radar/inspection_app.py
```

Responsibilities:

1. Read the requested collection date from CLI-passed configuration, query params, or environment variable.
2. Call `load_company_inspection_data`.
3. Render summary metrics.
4. Render sidebar filters.
5. Render filtered company table.
6. Render selected company details and job details.

## Execution Flow

1. Operator runs the existing pipeline steps as needed:
   - `process --date YYYY-MM-DD`
   - optionally `extract-job-descriptions --date YYYY-MM-DD`
   - optionally `enrich-companies --date YYYY-MM-DD`
2. Operator runs `uv run ai-hiring-radar inspect --date YYYY-MM-DD`.
3. The CLI launches Streamlit for `inspection_app.py`.
4. The Streamlit app calls `load_company_inspection_data`.
5. The loader reads `companies_YYYY-MM-DD.jsonl` as required input.
6. The loader reads candidates, JD extracts, and company enrichment files when present.
7. The loader groups candidates and company enrichment by normalized company key.
8. The loader indexes JD extracts by `job_id`.
9. The loader builds company inspection records:
   - starts from the base company record
   - attaches company enrichment fields
   - attaches compact job records
   - attaches JD extraction values to matching jobs
   - aggregates unique structured job signals to company-level filter lists
   - dedupes contacts and source URLs
10. The Streamlit app computes available filter options from the view models.
11. The operator filters the aggregate table.
12. The operator selects a company and inspects company details, jobs, contacts, evidence URLs, and optional raw JSON.

## Error Handling

Required file behavior:

1. Missing `companies_YYYY-MM-DD.jsonl` is a fatal load error because there is no base company list.
2. Non-dict rows in `companies_YYYY-MM-DD.jsonl` are skipped and counted.

Optional file behavior:

1. Missing `job_candidates_YYYY-MM-DD.jsonl` is non-fatal. The UI still shows company-level data without job details.
2. Missing `job_description_extracts_YYYY-MM-DD.jsonl` is non-fatal. JD-derived filters are empty.
3. Missing `company_enrichment_extracts_YYYY-MM-DD.jsonl` is non-fatal. Company enrichment filters are empty.
4. Malformed optional rows are skipped and counted.

Join behavior:

1. Companies are joined by normalized company key.
2. JD extracts are attached to jobs by `job_id`.
3. JD extracts with no matching candidate are still attached to the company-level job list when a valid `company_normalized` exists.
4. Duplicate company enrichment records for the same company use the last record in file order in V1.

UI behavior:

1. Empty filter result shows an empty table plus a readable message.
2. Missing optional files show warnings near the top of the app.
3. Long descriptions and raw JSON are collapsed by default.
4. External URLs render as clickable links when practical.

## Observability

The app should show a compact load summary:

1. Collection date.
2. Companies loaded.
3. Jobs loaded.
4. JD extracts loaded.
5. Company enrichments loaded.
6. Missing optional files.
7. Skipped malformed rows.
8. Current filtered company count.

The CLI command should print the selected collection date before launching Streamlit.

## Testing

Unit tests for `inspection.py`:

1. Loads base company records and returns company inspection records.
2. Aggregates unique `workplace_modes`, `ai_team_contexts`, and `delivery_contexts` from JD extracts.
3. Attaches company enrichment fields including `company_type`, `company_size`, `industry`, and `ai_tech_forward_signal`.
4. Joins candidates and JD extracts by `job_id`.
5. Handles missing optional files without failing.
6. Fails clearly when the required companies file is missing.
7. Dedupes contacts from company enrichment and JD extraction.
8. Exposes counts for loaded and skipped rows.

CLI tests:

1. `inspect --date YYYY-MM-DD` validates the date and calls the Streamlit launcher with the expected date.
2. Invalid dates fail with the existing CLI date validation behavior.

Manual verification:

1. Run `uv run pytest`.
2. Run `uv run ai-hiring-radar inspect --date 2026-06-17`.
3. Verify required filters are visible.
4. Verify selecting `remote`, `hybrid`, `existing_ai_team`, `internal`, `external_clients`, and company type filters changes the table as expected.
5. Verify company details show enrichment and job rows.

## Rollout

1. Add the Streamlit UI behind a new `inspect` command only.
2. Existing collection, processing, extraction, enrichment, and export commands remain unchanged.
3. The UI is read-only, so there is no migration or data backfill.
4. The implementation can be used immediately on existing processed dates.
5. Documentation should state that optional enrichment files are best-effort and that missing optional files only reduce available filters/details.

## Task Breakdown

### Dependency Graph

Task 1 is the foundation for Tasks 2 and 3. Task 4 depends on Tasks 1 and 3. Task 5 updates documentation after the CLI shape is final.

### Task 1: Add Inspection Loader And View Models

Scope:

1. Add `src/ai_hiring_radar/inspection.py`.
2. Add date-based path construction for inspection inputs.
3. Read required companies file and optional candidate/JD/company enrichment files.
4. Group records by normalized company key and `job_id`.
5. Build company and job inspection dictionaries.
6. Aggregate required filter fields:
   - `workplace_modes`
   - `ai_team_contexts`
   - `delivery_contexts`
   - `company_type`
   - `company_size`
7. Include load metadata and missing optional file information.

Files likely changed:

1. `src/ai_hiring_radar/inspection.py`
2. `tests/test_inspection.py`

Verification:

1. Unit tests verify joining and aggregation.
2. Unit tests verify missing optional files are non-fatal.
3. Unit tests verify missing required companies file fails.

### Task 2: Add Streamlit Dependency And App Shell

Scope:

1. Add `streamlit` to `pyproject.toml`.
2. Add `src/ai_hiring_radar/inspection_app.py`.
3. Render collection-date header, load summary, warnings, filter sidebar, aggregate table, and empty detail placeholder.
4. Keep all joining logic inside `inspection.py`.

Files likely changed:

1. `pyproject.toml`
2. `uv.lock`
3. `src/ai_hiring_radar/inspection_app.py`

Verification:

1. Manual run confirms the app starts.
2. Existing tests still pass.

### Task 3: Add Filters And Detail Views

Scope:

1. Add required filters for workplace mode, AI team context, delivery context, company type, and company size.
2. Add optional filters for country, role classification, source/platform, AI tech-forward signal, contacts, JD extracts, company enrichment, and text search.
3. Add selected-company detail view.
4. Add job detail table and expandable per-job details.
5. Add contact and evidence URL sections.
6. Add collapsed raw debug JSON section.

Files likely changed:

1. `src/ai_hiring_radar/inspection_app.py`
2. `tests/test_inspection.py` if filter helper functions are pure and testable

Verification:

1. Manual run confirms filters and detail panels work on an existing processed date.
2. Unit tests cover pure filter helpers if extracted from the app.

### Task 4: Add CLI Command

Scope:

1. Add `inspect --date YYYY-MM-DD` to `src/ai_hiring_radar/cli.py`.
2. Implement a small Streamlit launcher helper that can be monkeypatched in tests.
3. Pass the requested date to the app through environment variable or Streamlit query params.
4. Print the selected date before launching.

Files likely changed:

1. `src/ai_hiring_radar/cli.py`
2. `tests/test_cli.py`

Verification:

1. CLI tests monkeypatch the launcher and verify date propagation.
2. Invalid date uses existing CLI validation behavior.

### Task 5: Documentation Update

Scope:

1. Update `README.md` with the new command.
2. Document required and optional input files.
3. Document that V1 is read-only and local-only.
4. Document the required filters.

Files likely changed:

1. `README.md`

Verification:

1. Command examples are copy-pasteable.
2. Documentation matches actual CLI behavior.

## Open Questions

None. V1 decisions are locked:

1. Streamlit is the frontend technology.
2. The UI is local and read-only.
3. Existing JSONL files remain canonical.
4. The Python inspection loader owns joining and aggregation.
5. The frontend does not join source files itself.
6. No merged inspection JSONL is persisted in V1.
7. Required filters are workplace mode, AI team context, delivery context, company type, and company size.
