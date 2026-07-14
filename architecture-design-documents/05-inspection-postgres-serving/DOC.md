# Inspection Postgres Serving

## Status

Draft

## Context

`uv run ai-hiring-radar inspect` currently loads processed JSONL files at runtime through `src/ai_hiring_radar/inspection.py`. For larger collection dates, this means Streamlit reads and joins company records, job candidates, job-description extracts, and company enrichment extracts in memory before rendering.

The inspection UI is company-centric. Operators filter one collection date, inspect companies, review embedded jobs, contacts, enrichment facts, and evidence URLs, then update manual review state. The UI does not currently need independent job-level pages, analytics tables, or a fully normalized warehouse.

The first backend improvement should therefore move the company inspection read model out of runtime JSONL loading and into Postgres, without overbuilding a complete relational data model.

## Goals

1. Add a Postgres-backed serving store for the inspection UI.
2. Keep JSONL as the pipeline/staging output for now.
3. Import one collection date at a time into Postgres.
4. Store compact company inspection snapshots keyed by `collection_date` and `company_key`.
5. Preserve the current company-centric inspection data shape.
6. Exclude full job descriptions from Postgres for now.
7. Make Streamlit load from Postgres when available.
8. Keep JSONL fallback for local development and unsynced dates.
9. Preserve existing `company_review_state` behavior.

## Non-Goals

1. No TypeScript frontend yet.
2. No FastAPI/API layer yet.
3. No full relational warehouse for jobs, extracts, enrichments, contacts, or URLs.
4. No direct pipeline-to-Postgres writes yet.
5. No auth, roles, tenant separation, or RLS.
6. No full job descriptions in Postgres.
7. No removal of JSONL artifacts.
8. No independent job review workflow.

## Requirements

Functional requirements:

1. Add a CLI command:

```bash
uv run ai-hiring-radar sync-inspection-db --date YYYY-MM-DD
```

2. The sync command loads the same inspection data currently used by Streamlit.
3. The sync command stores one snapshot row per company for the selected date.
4. Re-syncing a date replaces generated snapshot rows for that date.
5. Re-syncing a date must not delete or modify `company_review_state`.
6. Streamlit should prefer DB snapshots when a DB URL is configured and the date exists in DB.
7. Streamlit should fall back to JSONL when DB is unavailable, unconfigured, or unsynced.
8. Streamlit should keep the current UI behavior for the first migration.
9. Snapshot payloads must exclude full job descriptions and raw nested source records.

Non-functional requirements:

1. Sync for a collection date should be transactional.
2. Queries should be optimized for selected-date company filtering.
3. Search should avoid scanning large JSON payloads.
4. DB schema should stay simple enough to maintain manually in Supabase.
5. The design should allow a future TypeScript frontend or API layer to reuse the same snapshots.

## Current State

Relevant modules:

| File | Current Role |
|---|---|
| `src/ai_hiring_radar/inspection.py` | Builds company inspection records from JSONL. |
| `src/ai_hiring_radar/inspection_app.py` | Streamlit UI. |
| `src/ai_hiring_radar/review_state.py` | Existing Postgres persistence for manual review state. |
| `src/ai_hiring_radar/storage_json.py` | JSON/JSONL helpers. |
| `src/ai_hiring_radar/cli.py` | Typer CLI commands. |

Current runtime flow:

```text
processed JSONL files
  -> load_company_inspection_data(collection_date)
  -> in-memory company inspection records
  -> load company_review_state from Postgres
  -> merge review state
  -> Streamlit filters/table/detail
```

Current data files:

| File | Role |
|---|---|
| `companies_YYYY-MM-DD.jsonl` | Company-level aggregate. |
| `job_candidates_YYYY-MM-DD.jsonl` | Job candidate records, may include descriptions. |
| `job_description_extracts_YYYY-MM-DD.jsonl` | Structured JD extraction. |
| `company_enrichment_extracts_YYYY-MM-DD.jsonl` | Company enrichment. |
| `inspection_companies_YYYY-MM-DD.jsonl` | Compact deployment artifact. |

## Proposed Design

Introduce Postgres as a runtime serving store for the inspection UI.

Selected architecture:

```text
processed JSONL files
  -> sync-inspection-db --date YYYY-MM-DD
  -> load existing inspection view model
  -> compact and sanitize records
  -> store inspection_company_snapshots in Postgres

Streamlit
  -> resolve selected collection date
  -> try loading inspection_company_snapshots from Postgres
  -> fall back to JSONL loader if needed
  -> merge company_review_state
  -> render current UI
```

This keeps the DB schema focused on what the frontend needs: a company-centric read model with indexed filter/search columns and compact JSONB detail payloads.

## Data Model

### Existing Table: `company_review_state`

`company_review_state` remains unchanged. It stores manual review state by `company_key`:

| Column | Purpose |
|---|---|
| `company_key` | Stable company review key. |
| `company` | Most recently seen company display name. |
| `fit_status` | Manual fit status. |
| `outreach_status` | Manual outreach status. |
| `notes` | General Notes; retains the original manual notes storage contract. |
| `communication_history` | Editable free-text Communication History. |
| `inspected_at` | First reviewed timestamp. |
| `last_seen_collection_date` | Most recent collection date from a save. |
| `created_at` | Row creation time. |
| `last_updated_at` | Last update time. |
| `last_updated_by` | Free-text reviewer name. |

### New Table: `inspection_collections`

Purpose: track which dates have been synced.

| Column | Type | Notes |
|---|---|---|
| `collection_date` | `date primary key` | Imported collection date. |
| `source_kind` | `text not null` | Usually `jsonl`. |
| `snapshot_count` | `integer not null` | Number of company snapshots. |
| `job_count` | `integer not null` | Total compact jobs across snapshots. |
| `sync_summary` | `jsonb not null default '{}'` | Counts, skipped rows, and source paths. |
| `synced_at` | `timestamptz not null default now()` | Last successful sync time. |

### New Table: `inspection_company_snapshots`

Purpose: one compact company inspection record per collection date and company.

| Column | Type | Notes |
|---|---|---|
| `collection_date` | `date not null` | FK to `inspection_collections`. |
| `company_key` | `text not null` | Same key used by review state. |
| `company` | `text not null` | Display name. |
| `countries` | `text[] not null default '{}'` | Filter column. |
| `sources` | `text[] not null default '{}'` | Filter column. |
| `workplace_modes` | `text[] not null default '{}'` | Filter column. |
| `ai_team_contexts` | `text[] not null default '{}'` | Filter column. |
| `delivery_contexts` | `text[] not null default '{}'` | Filter column. |
| `role_classification` | `text` | Filter column. |
| `company_type` | `text` | Filter column. |
| `company_size` | `text` | Filter/sort column. |
| `ai_tech_forward_signal` | `text` | Filter column. |
| `job_count` | `integer not null default 0` | Sort/filter column. |
| `job_description_extract_count` | `integer not null default 0` | Summary metric. |
| `has_contacts` | `boolean not null default false` | Filter column. |
| `has_job_description_extracts` | `boolean not null default false` | Filter column. |
| `has_company_enrichment` | `boolean not null default false` | Filter column. |
| `search_text` | `text not null default ''` | Search source text, excluding job descriptions. |
| `search_vector` | `tsvector generated always` | Indexed full-text search vector. |
| `summary_payload` | `jsonb not null` | Compact table/list data. |
| `detail_payload` | `jsonb not null` | Compact company detail data. |
| `created_at` | `timestamptz not null default now()` | Insert time. |
| `updated_at` | `timestamptz not null default now()` | Update time. |

Primary key:

```sql
primary key (collection_date, company_key)
```

Foreign key:

```sql
foreign key (collection_date)
references public.inspection_collections (collection_date)
on delete cascade
```

### Payload Rules

`detail_payload` should contain the compact inspection record shape currently used by the app.

| Data | Include |
|---|---|
| Company fields | Yes |
| Compact jobs | Yes |
| Contacts | Yes |
| Enrichment facts | Yes |
| Evidence URLs | Yes |
| Source/platform metadata | Yes |
| Counts and flags | Yes |
| Full job descriptions | No |
| `description` / `description_plain` | No |
| Raw candidate records | No |
| Raw JD extraction records | No |
| Raw enrichment records | No |
| Raw LLM responses | No |

### Indexes

Suggested indexes:

```sql
create index if not exists inspection_company_snapshots_collection_date_idx
  on public.inspection_company_snapshots (collection_date);

create index if not exists inspection_company_snapshots_company_key_idx
  on public.inspection_company_snapshots (company_key);

create index if not exists inspection_company_snapshots_company_type_idx
  on public.inspection_company_snapshots (company_type);

create index if not exists inspection_company_snapshots_company_size_idx
  on public.inspection_company_snapshots (company_size);

create index if not exists inspection_company_snapshots_ai_signal_idx
  on public.inspection_company_snapshots (ai_tech_forward_signal);

create index if not exists inspection_company_snapshots_has_contacts_idx
  on public.inspection_company_snapshots (has_contacts);

create index if not exists inspection_company_snapshots_countries_gin_idx
  on public.inspection_company_snapshots using gin (countries);

create index if not exists inspection_company_snapshots_sources_gin_idx
  on public.inspection_company_snapshots using gin (sources);

create index if not exists inspection_company_snapshots_workplace_modes_gin_idx
  on public.inspection_company_snapshots using gin (workplace_modes);

create index if not exists inspection_company_snapshots_ai_team_contexts_gin_idx
  on public.inspection_company_snapshots using gin (ai_team_contexts);

create index if not exists inspection_company_snapshots_delivery_contexts_gin_idx
  on public.inspection_company_snapshots using gin (delivery_contexts);

create index if not exists inspection_company_snapshots_search_idx
  on public.inspection_company_snapshots using gin (search_vector);
```

## Interfaces

### Config

Add a new DB URL setting:

```text
AI_HIRING_RADAR_DATABASE_URL=postgresql://...
```

Streamlit secrets can also support:

```toml
[connections.supabase_inspection]
url = "postgresql://..."
```

For simplicity, this design uses a single URL for sync, app reads, and `company_review_state` reads/writes.

### CLI

New command:

```bash
uv run ai-hiring-radar sync-inspection-db --date YYYY-MM-DD
```

Expected output:

```text
Inspection DB sync complete: 708 company snapshot(s), 4009 compact job(s).
Collection date: 2026-07-03
Source: data/processed
Database: configured
```

### Python Module

New module:

```text
src/ai_hiring_radar/inspection_db.py
```

Expected public functions:

```python
def sync_inspection_database(
    collection_date: str,
    *,
    database_url: str,
    data_dir: Path = DEFAULT_DATA_DIR,
) -> InspectionDatabaseSyncResult:
    ...
```

```python
def load_company_inspection_data_from_database(
    collection_date: str,
    *,
    database_url: str,
) -> CompanyInspectionDataset | None:
    ...
```

```python
def list_synced_collection_dates(
    *,
    database_url: str,
) -> list[str]:
    ...
```

Possible dataclass:

```python
@dataclass(frozen=True)
class InspectionDatabaseSyncResult:
    collection_date: str
    snapshot_count: int
    job_count: int
    database_url_configured: bool
```

### Streamlit App

Modify `inspection_app.py` so `_load_dataset(collection_date)` tries DB first when configured.

Expected logic:

```text
if inspection DB URL exists:
    try DB load
    if DB rows found:
        return DB dataset
    else:
        warn and fall back to JSONL
else:
    use JSONL
```

## Execution Flow

### Sync Flow

```text
sync-inspection-db --date YYYY-MM-DD
  -> parse date
  -> resolve AI_HIRING_RADAR_DATABASE_URL
  -> call load_company_inspection_data(date)
  -> compact each company record
  -> strip full descriptions and raw payloads
  -> build filter/search columns
  -> begin transaction
  -> delete inspection_collections row for date, cascading old snapshots
  -> insert inspection_collections row
  -> insert inspection_company_snapshots rows
  -> commit
  -> print counts
```

### Streamlit Flow

```text
inspect --date YYYY-MM-DD
  -> Streamlit starts
  -> resolve collection date
  -> resolve DB URL
  -> query inspection_company_snapshots for date
  -> if found, build CompanyInspectionDataset from detail_payload rows
  -> if not found, load JSONL as today
  -> load company_review_state
  -> merge review state
  -> render filters/table/detail
```

## Error Handling

| Case | Behavior |
|---|---|
| DB URL missing during sync | CLI exits with clear error. |
| DB URL missing during Streamlit load | Use JSONL fallback. |
| Date not synced | Use JSONL fallback and show warning. |
| DB connection failure | Use JSONL fallback and show warning. |
| Sync fails mid-run | Transaction rolls back. |
| JSONL missing required companies file during sync | CLI exits with existing loader error. |
| Malformed JSONL rows | Existing skip counts are reflected in sync summary. |
| Full descriptions present | Sanitizer strips them before DB insert. |
| Review state exists for date/company | Preserved and merged at render time. |

## Observability

Sync should report:

| Metric | Source |
|---|---|
| Collection date | CLI input. |
| Snapshot count | Inserted rows. |
| Job count | Sum of compact jobs. |
| Missing optional files | Existing loader. |
| Skipped malformed rows | Existing loader counts. |
| Sync timestamp | `inspection_collections.synced_at`. |

Streamlit should show:

| Indicator | Purpose |
|---|---|
| Data source: `database` or `jsonl` | Makes fallback visible. |
| DB fallback warning | Explains why JSONL was used. |
| Synced date | Confirms selected DB data. |
| Existing summary metrics | Preserve current UX. |

## Testing

Unit tests:

| Test | Purpose |
|---|---|
| `test_compact_snapshot_strips_descriptions` | Ensures no full descriptions enter DB payload. |
| `test_build_snapshot_columns_from_record` | Verifies filter/search columns. |
| `test_sync_replaces_existing_date_rows` | Verifies replace-date semantics. |
| `test_sync_preserves_review_state` | Ensures `company_review_state` remains untouched. |
| `test_load_database_snapshots_returns_dataset` | Verifies DB rows become `CompanyInspectionDataset`. |
| `test_streamlit_load_dataset_falls_back_to_jsonl` | Verifies fallback behavior. |
| `test_cli_sync_inspection_db_parses_date` | Verifies CLI wiring. |

Acceptance stories:

**US-1:** As an operator, I sync a processed collection date into Postgres, so that inspection data can load without reading JSONL at render time.

Acceptance test: `tests/test_inspection_db_acceptance.py::test_sync_inspection_date_populates_snapshots`

Status: stub

**US-2:** As an operator, I open the inspection UI for a synced date, so that Streamlit loads company snapshots from Postgres.

Acceptance test: `tests/test_inspection_db_acceptance.py::test_inspection_ui_loads_database_snapshots`

Status: stub

**US-3:** As an operator, I open the inspection UI without a configured or synced database, so that the existing JSONL flow still works.

Acceptance test: `tests/test_inspection_db_acceptance.py::test_inspection_ui_falls_back_to_jsonl`

Status: stub

**US-4:** As an operator, I re-sync a date, so that generated snapshots are refreshed while manual review state remains intact.

Acceptance test: `tests/test_inspection_db_acceptance.py::test_resync_replaces_snapshots_but_preserves_review_state`

Status: stub

## Rollout

1. Add `setup.sql` under `architecture-design-documents/05-inspection-postgres-serving/`.
2. Run SQL in Supabase.
3. Add `AI_HIRING_RADAR_DATABASE_URL` locally.
4. Run `uv run ai-hiring-radar sync-inspection-db --date YYYY-MM-DD`.
5. Launch `uv run ai-hiring-radar inspect --date YYYY-MM-DD`.
6. Confirm Streamlit reports DB source.
7. Compare speed and UX against JSONL fallback.
8. Do the vibe check before any frontend rewrite.

## Task Breakdown

Task 1: Design doc and SQL setup.

Create `DOC.md` and `setup.sql`.

Task 2: DB config resolution.

Add config support for `AI_HIRING_RADAR_DATABASE_URL`.

Task 3: Snapshot builder and sanitizer.

Build compact snapshots from existing inspection records and strip descriptions/raw payloads.

Task 4: DB sync service.

Add `inspection_db.py` with transactional replace-date sync.

Task 5: CLI command.

Add `sync-inspection-db`.

Task 6: DB loader.

Load snapshots back into `CompanyInspectionDataset`.

Task 7: Streamlit integration.

Prefer DB loader with JSONL fallback and visible data-source status.

Task 8: Tests.

Add unit and acceptance coverage.

Task 9: Docs.

Update README and `.env.example`.

## Decisions Made

1. Use a company snapshot table instead of a fully relational schema because the inspection UI is company-centric.
2. Keep JSONL as pipeline/staging output because collection/processing already works and direct DB writes are not needed yet.
3. Exclude full descriptions from DB because they are large and not needed for the first performance fix.
4. Keep JSONL fallback to avoid blocking local development and reduce rollout risk.
5. Use manual `setup.sql` because the repo does not currently use Alembic.
6. Use one DB URL for now because this is an internal admin-only tool.
7. Preserve `company_review_state` as a separate manual-state table.

## Upgrade Paths

### Future API/Frontend

The snapshot table can later back a small API and TypeScript frontend:

```text
inspection_company_snapshots
  -> FastAPI endpoints
  -> TypeScript frontend
```

### Future Full Relational Backend

If job-level analytics or independent job pages become necessary, add normalized tables:

```text
jobs
job_description_extracts
company_enrichments
contacts
```

### Future Full Descriptions

If full job descriptions become necessary, add a separate storage path:

```text
job_descriptions table
or object storage-backed detail retrieval
```

### Future Pipeline Direct Writes

The pipeline can later write directly to Postgres:

```text
process/extract/enrich commands
  -> write directly to Postgres
  -> optional JSONL export
```

## Open Questions

None for this phase.
