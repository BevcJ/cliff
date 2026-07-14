# Company Review State

## Status

Draft

## Context

The current company inspection UI is a local-first Streamlit app for reviewing processed hiring-signal data. It joins generated JSONL files from collection, processing, job-description extraction, and company enrichment, then lets an operator filter and inspect company/job details. The UI is intentionally read-only today.

The next workflow need is manual review tracking. Operators inspect companies by hand and need to record whether a company is a good target, a possible target, or not interesting. They also need a lightweight communication status such as message sent or follow-up needed. This state must be visible across users because the app is now deployed on Streamlit Cloud.

Streamlit Community Cloud cannot use generated local files as reliable multi-user persistent storage. Streamlit documentation states files generated while the app is running are not guaranteed to persist across sessions. `st.session_state` is also per user session and not durable shared state. Therefore shared review state needs an external persistent backend.

This design adds Supabase Postgres as the shared state store for current company review status only. Generated hiring data remains file/artifact-backed and read-only.

## Goals

1. Extend the existing Streamlit inspection UI instead of creating a separate app.
2. Let users mark company fit as `unreviewed`, `best_fit`, `possible_fit`, or `not_interesting`.
3. Let users mark outreach status as `not_started`, `message_sent`, `follow_up_needed`, `replied`, or `closed`.
4. Let users save separate free-text General Notes and Communication History per company.
5. Persist review state in Supabase Postgres so all Streamlit Cloud users see the same state.
6. Keep generated company, candidate, enrichment, and inspection artifact JSONL files read-only.
7. Add UI tabs for the review workflow: `Inspect`, `Shortlist`, `Outreach`, and `Rejected`.
8. Keep v1 simple: no authentication, no structured or append-only event history, no CRM sync, and no per-user ownership.
9. Provide a degraded read-only mode when Supabase is unavailable or not configured.

## Non-Goals

1. User authentication or authorization inside the app.
2. Supabase Auth integration.
3. Row-level multi-tenant isolation.
4. Structured or append-only audit/event history of every change.
5. CRM functionality such as accounts, contacts, tasks, reminders, or sequences.
6. Automatic outreach message generation.
7. Writing review state back into `companies_YYYY-MM-DD.jsonl` or `inspection_companies_YYYY-MM-DD.jsonl`.
8. Editing generated company facts, job facts, contacts, or enrichment fields.
9. Importing existing spreadsheet review state.
10. Multi-environment migration tooling beyond a documented SQL setup script for Supabase.

## Requirements

Functional requirements:

1. The app must continue loading generated inspection data exactly as today.
2. The app must query Supabase for review state keyed by `company_key`.
3. The app must merge review state into inspection records before rendering filters, tables, tabs, and detail panels.
4. Companies without persisted review state must default to:
   - `fit_status = "unreviewed"`
   - `outreach_status = "not_started"`
   - `notes = ""`
   - `communication_history = ""`
5. The main company table must show fit status and outreach status.
6. The sidebar must support filtering by fit status and outreach status.
7. The selected company detail panel must contain a save form for fit status, outreach status, General Notes, and Communication History.
8. Saving review state must use an atomic upsert by `company_key`.
9. Changing `fit_status` from `unreviewed` to any reviewed status must set `inspected_at` if it was previously empty.
10. Saving must update `last_seen_collection_date`, `last_updated_at`, and `last_updated_by`.
11. The app must include a sidebar `Reviewer name` text input and use it as `last_updated_by` when non-empty.
12. The app must expose a `Shortlist` tab with companies where `fit_status` is `best_fit` or `possible_fit`.
13. The app must expose an `Outreach` tab for suitable companies where outreach has started or follow-up is needed.
14. The app must expose a `Rejected` tab for companies where `fit_status` is `not_interesting`.
15. If Supabase is unavailable, missing, or misconfigured, generated inspection data must still render read-only with a visible warning and disabled save controls.

Non-functional requirements:

1. Review-state logic must be unit-testable without Streamlit.
2. The app must not create a new frontend stack.
3. The Supabase connection string must be read from Streamlit secrets or environment configuration and must not be committed.
4. The Supabase role used by the app should be least-privilege: `select`, `insert`, and `update` only on the review-state table.
5. The implementation should use the Supabase transaction pooler connection string for Streamlit Cloud.
6. The generated inspection data cache must not make review status stale after a save.
7. The review-state query should fetch all visible company keys in one batch, not one query per company.

## Current State

Relevant existing modules:

1. `src/ai_hiring_radar/inspection.py` loads generated processed files and builds company inspection records.
2. `src/ai_hiring_radar/inspection_app.py` renders the Streamlit inspection UI.
3. `src/ai_hiring_radar/aggregate.py` writes generated company records with `review_status = "new"`.
4. `src/ai_hiring_radar/storage_json.py` owns local JSON/JSONL paths and read/write helpers.
5. `streamlit_app.py` is the Streamlit Cloud entrypoint.
6. `README.md` documents local and Streamlit Cloud inspection deployment.

Current inspection data sources:

1. `data/processed/companies_YYYY-MM-DD.jsonl`
2. `data/processed/job_candidates_YYYY-MM-DD.jsonl`
3. `data/processed/job_description_extracts_YYYY-MM-DD.jsonl`
4. `data/processed/company_enrichment_extracts_YYYY-MM-DD.jsonl`
5. `data/processed/inspection_companies_YYYY-MM-DD.jsonl` for compact Streamlit Cloud deployment.

Current limitations:

1. The UI displays generated `review_status`, but users cannot edit it.
2. The app has no persistent manual state.
3. The deployed Streamlit app cannot rely on writing JSONL files for durable multi-user state.
4. There is no shortlist or outreach pipeline view.
5. There is no way to distinguish fit assessment from communication progress.

## Proposed Design

Add a small Supabase-backed review-state layer beside the existing generated inspection-data layer.

Selected architecture:

```text
generated JSONL / inspection artifact
  -> inspection loader                   # unchanged generated company/job/enrichment records
  -> generated inspection records

Supabase Postgres company_review_state
  -> review state loader                 # NEW shared current-state records by company_key
  -> review state map

generated inspection records + review state map
  -> merged Streamlit records            # NEW defaults + persisted fit/outreach/text fields
  -> tabs, filters, table, detail form
```

This separates generated facts from manual operator state. Generated data remains reproducible from pipeline outputs. Manual state remains durable across deployed Streamlit sessions and across regenerated inspection artifacts as long as `company_key` is stable.

Implementation shape:

1. Add `src/ai_hiring_radar/review_state.py` for review-state constants, data loading, merging, and upsert helpers.
2. Add Supabase Postgres connection configuration via Streamlit secrets and/or environment variable.
3. Modify `inspection_app.py` to load generated data as today, then load and merge review state separately.
4. Add review filters, table columns, tabs, and selected-company save form.
5. Add documentation and a Supabase SQL setup script or SQL block.

The app will use current-state persistence only. Later event history can be added without changing the table contract used by the UI.

## Data Model

### Supabase Table

The canonical v1 persisted state table is `company_review_state`.

```sql
create table company_review_state (
  company_key text primary key,
  company text not null,
  fit_status text not null default 'unreviewed',
  outreach_status text not null default 'not_started',
  notes text not null default '',
  communication_history text not null default '',
  inspected_at timestamptz,
  last_seen_collection_date date,
  created_at timestamptz not null default now(),
  last_updated_at timestamptz not null default now(),
  last_updated_by text,

  constraint company_review_state_fit_status_check
    check (fit_status in ('unreviewed', 'best_fit', 'possible_fit', 'not_interesting')),

  constraint company_review_state_outreach_status_check
    check (outreach_status in ('not_started', 'message_sent', 'follow_up_needed', 'replied', 'closed'))
);

create index company_review_state_fit_status_idx
  on company_review_state (fit_status);

create index company_review_state_outreach_status_idx
  on company_review_state (outreach_status);
```

Schema rationale:

1. `company_key` is the primary key because it is already the inspection join key and is stable across collection dates for the same normalized company name.
2. `company` stores the most recently seen display name for readability and admin debugging.
3. `fit_status` and `outreach_status` are separate because target suitability and communication progress are different dimensions.
4. `notes` remains the backing column for General Notes so existing content requires no migration or compatibility alias.
5. `communication_history` is a second editable text value and defaults to an empty string. It is not an append-only event log.
6. `inspected_at` captures the first manual review moment without requiring a separate event table.
7. `last_seen_collection_date` allows future stale-state cleanup and tells operators when a reviewed company last appeared in the generated pipeline.
8. `last_updated_by` is free text in v1 because authentication is explicitly out of scope.
9. Check constraints enforce valid states at the database boundary.
10. Status indexes support filter queries and future dashboard views.

### Python Review State Shape

Representative in-memory review state:

```python
{
    "company_key": "acme ai",
    "company": "Acme AI",
    "fit_status": "best_fit",
    "outreach_status": "message_sent",
    "notes": "Strong AI delivery signal; good CTO contact.",
    "communication_history": "2026-07-14: Sent a LinkedIn message to the CTO.",
    "inspected_at": "2026-07-07T10:30:00+00:00",
    "last_seen_collection_date": "2026-07-07",
    "last_updated_at": "2026-07-07T10:35:00+00:00",
    "last_updated_by": "Jakob",
}
```

### Merged Inspection Record Fields

Every rendered inspection record gains these fields after merging review state:

```python
{
    "fit_status": "unreviewed",
    "outreach_status": "not_started",
    "review_notes": "",
    "review_communication_history": "",
    "inspected_at": None,
    "last_reviewed_at": None,
    "last_reviewed_by": None,
    "has_review_state": False,
}
```

The generated `review_status` field remains untouched for backward compatibility with current generated exports, but new UI logic uses `fit_status` and `outreach_status`.

## Interfaces

### Supabase Configuration

Streamlit Cloud secrets should contain the Postgres pooler connection string.

```toml
[connections.supabase_review_state]
url = "postgres://app_user.PROJECT_REF:PASSWORD@aws-REGION.pooler.supabase.com:6543/postgres"
```

The implementation may also support an environment variable for local development:

```text
AI_HIRING_RADAR_REVIEW_STATE_DATABASE_URL=postgres://...
```

The app should prefer Streamlit secrets when available and fall back to the environment variable.

### Dependency

Add a Postgres client dependency. Preferred:

```toml
psycopg[binary]>=3.2.0
```

Rationale: the feature needs a small number of direct SQL operations. The Supabase Python client is not required for this v1 because only Postgres table reads and upserts are needed.

### Python Module

New module:

```text
src/ai_hiring_radar/review_state.py
```

Public constants:

```python
FIT_STATUS_OPTIONS = ("unreviewed", "best_fit", "possible_fit", "not_interesting")
OUTREACH_STATUS_OPTIONS = (
    "not_started",
    "message_sent",
    "follow_up_needed",
    "replied",
    "closed",
)
```

Suggested public functions:

```python
def default_review_state(company_key: str, company: str) -> dict[str, Any]:
    ...

def merge_review_state(
    records: list[dict[str, Any]],
    review_state_by_company_key: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    ...

def load_review_state(
    company_keys: list[str],
    *,
    database_url: str,
) -> dict[str, dict[str, Any]]:
    ...

def upsert_review_state(
    review_state: dict[str, Any],
    *,
    database_url: str,
) -> dict[str, Any]:
    ...

def upsert_review_statuses(
    review_state: dict[str, Any],
    *,
    database_url: str,
) -> dict[str, Any]:
    ...
```

### Streamlit App

Modified module:

```text
src/ai_hiring_radar/inspection_app.py
```

New responsibilities:

1. Resolve review-state database URL from secrets/env.
2. Query review state for loaded companies.
3. Merge review state into generated inspection records.
4. Render reviewer-name input.
5. Render review-state filters.
6. Render tabs.
7. Render save form in selected-company detail.
8. Disable save controls when review-state backend is unavailable.

## Execution Flow

Normal render flow:

1. User opens the deployed Streamlit app.
2. App resolves collection date exactly as today.
3. App calls `load_company_inspection_data(collection_date)` to load generated inspection records.
4. App extracts `company_key` values from generated records.
5. App resolves Supabase review-state connection string from Streamlit secrets or environment.
6. App calls `load_review_state(company_keys, database_url=...)` once.
7. App merges review state into generated records with defaults for missing rows.
8. App renders summary metrics, sidebar filters, and workflow tabs.
9. User selects a company.
10. App renders company details and review-state save form.
11. User changes fit/outreach/General Notes/Communication History and clicks save.
12. App calls `upsert_review_state(...)`.
13. App shows success message and reruns/refreshes merged state.

Upsert SQL shape:

```sql
insert into company_review_state (
  company_key,
  company,
  fit_status,
  outreach_status,
  notes,
  communication_history,
  inspected_at,
  last_seen_collection_date,
  last_updated_at,
  last_updated_by
) values (
  %(company_key)s,
  %(company)s,
  %(fit_status)s,
  %(outreach_status)s,
  %(notes)s,
  %(communication_history)s,
  %(inspected_at)s,
  %(last_seen_collection_date)s,
  now(),
  %(last_updated_by)s
)
on conflict (company_key) do update set
  company = excluded.company,
  fit_status = excluded.fit_status,
  outreach_status = excluded.outreach_status,
  notes = excluded.notes,
  communication_history = excluded.communication_history,
  inspected_at = coalesce(company_review_state.inspected_at, excluded.inspected_at),
  last_seen_collection_date = excluded.last_seen_collection_date,
  last_updated_at = now(),
  last_updated_by = excluded.last_updated_by
returning *;
```

Tab behavior:

1. `Inspect`: all merged records after global filters.
2. `Shortlist`: records where `fit_status in ('best_fit', 'possible_fit')`.
3. `Outreach`: records where `fit_status in ('best_fit', 'possible_fit')` and `outreach_status != 'not_started'`.
4. `Rejected`: records where `fit_status = 'not_interesting'`.

Needs-action behavior:

1. The sidebar `Needs action` filter includes suitable companies where `outreach_status in ('not_started', 'follow_up_needed')`.
2. `not_interesting` companies are excluded from `Needs action`.

## Error Handling

Supabase configuration errors:

1. If no database URL is configured, the app shows a warning: review state is disabled.
2. Generated inspection data still loads and renders.
3. Save controls are disabled or replaced with an explanation.

Supabase connection/query errors:

1. If loading review state fails, the app logs/shows a warning and renders generated data with default review state.
2. Save controls are disabled for that render to avoid implying persistence works.
3. The generated data cache is not invalidated by a failed review-state load.

Validation errors:

1. Invalid fit/outreach values are blocked in the UI by select boxes.
2. Database check constraints reject invalid values if a bug bypasses UI validation.
3. Upsert failures show a visible error message and keep the user's attempted form values in Streamlit widget state.

Concurrent edits:

1. V1 uses last-write-wins.
2. `last_updated_at` and `last_updated_by` make the latest edit visible.
3. No optimistic locking is implemented in v1.

Missing company keys:

1. Records without `company_key` cannot be persisted and should render read-only review controls.
2. This should be rare because `inspection.py` already computes `company_key`.

Supabase schema missing:

1. If the table does not exist, the app shows a setup-oriented error.
2. The UI remains read-only.

## Observability

The app should show or make visible:

1. Whether review-state persistence is enabled.
2. Count of review-state rows loaded for the current generated records.
3. Count of companies with default/unpersisted review state.
4. Count by `fit_status`.
5. Count by `outreach_status`.
6. Last reviewed timestamp and reviewer in the selected company detail panel when available.
7. Save success/failure messages.

Debugging aids:

1. Existing raw inspection JSON expander should include merged review-state fields.
2. Review-state backend errors should include concise exception text in the UI and enough context for local debugging.
3. README should document how to test the Supabase connection from Streamlit Cloud secrets.

## Testing

Unit tests for `review_state.py`:

1. `default_review_state` returns expected defaults.
2. `merge_review_state` overlays persisted state by `company_key`.
3. `merge_review_state` preserves generated inspection fields.
4. `merge_review_state` marks missing persisted rows as `has_review_state = False`.
5. Upsert payload construction sets `inspected_at` only when fit status is reviewed.
6. Invalid status values are rejected before SQL execution.

Unit tests for `inspection_app.py` pure helpers:

1. Fit status filter matches selected statuses.
2. Outreach status filter matches selected statuses.
3. Needs-action filter includes suitable `not_started` and `follow_up_needed` companies.
4. Shortlist tab helper returns `best_fit` and `possible_fit` only.
5. Outreach tab helper excludes `not_started`.
6. Rejected tab helper returns `not_interesting` only.
7. Company table rows include fit and outreach status.

Integration-style tests with monkeypatching:

1. App can render merged records when review-state loader succeeds.
2. App renders read-only mode when review-state loader raises.
3. Full save handler calls the review-state upsert with both text fields.
4. Inline grid edits call the status-only upsert and cannot overwrite either text field.

Manual verification:

1. Create Supabase table with SQL from this design.
2. Configure Streamlit secrets locally or in Streamlit Cloud.
3. Launch the app for a processed date.
4. Mark a company `best_fit` and `message_sent`, then save both General Notes and Communication History.
5. Refresh the app and confirm statuses and both text fields persist.
6. Change a status in the grid and confirm neither text field changes.
7. Open the app in another browser/session and confirm state is shared.
8. Disable/break the database URL and confirm the app remains read-only instead of failing to load generated data.

## Rollout

1. For a new deployment, create the Supabase `company_review_state` table with `setup.sql`.
2. For an existing deployment, apply `migrate_add_communication_history.sql` before deploying application code.
3. Create or configure a least-privilege Postgres user for the app.
4. Add the Supabase transaction-pooler connection string to Streamlit Cloud secrets.
5. Deploy code with review-state support.
6. Verify the app loads in read-write mode.
7. Ask operators to use `Reviewer name` before saving state.
8. Keep existing generated JSONL and compact inspection artifact deployment flow unchanged.

Compatibility:

1. Existing processed dates work immediately.
2. Existing compact inspection artifacts work immediately.
3. Companies without persisted review state display default values.
4. Existing CSV/Markdown exports remain unchanged in v1.
5. Existing `notes` values appear unchanged as General Notes; Communication History starts empty.

Rollback:

1. Removing or disabling the Supabase connection returns the app to read-only generated inspection mode.
2. Supabase state remains intact and can be re-enabled later.
3. No generated data migration rollback is required because generated files are not modified.

## Task Breakdown

### Dependency Graph

Task 1 is the database foundation. Task 2 adds the Python state boundary. Tasks 3 and 4 integrate the UI. Task 5 documents deployment. Tasks 3 and 4 depend on Task 2. Task 5 depends on the final configuration names.

### Task 1: Add Supabase Schema Documentation

Scope:

1. Add SQL setup documentation for `company_review_state`.
2. Include least-privilege role guidance.
3. Include Streamlit Cloud secret key names.

Files likely changed:

1. `README.md`
2. Optional new SQL file under `plan/` or `architecture-design-documents/04-company-review-state/`

Verification:

1. SQL can be pasted into Supabase SQL editor.
2. Table and indexes are created successfully.

### Task 2: Add Review State Module

Scope:

1. Add `src/ai_hiring_radar/review_state.py`.
2. Add status constants.
3. Add default/merge helpers.
4. Add database load/upsert helpers.
5. Add validation for allowed statuses.

Files likely changed:

1. `src/ai_hiring_radar/review_state.py`
2. `tests/test_review_state.py`
3. `pyproject.toml`
4. `uv.lock`

Verification:

1. Unit tests cover defaults, merge behavior, status validation, and payload construction.

### Task 3: Merge Review State In The Streamlit App

Scope:

1. Resolve database URL from Streamlit secrets/env.
2. Load generated inspection data as today.
3. Load review state for all company keys.
4. Merge review state into records.
5. Show read-only warning when persistence is unavailable.
6. Avoid caching review state inside generated inspection-data cache.

Files likely changed:

1. `src/ai_hiring_radar/inspection_app.py`
2. `tests/test_inspection_app.py`

Verification:

1. Unit tests verify read-write and read-only branches.
2. Existing inspection app tests still pass.

### Task 4: Add Review UI Controls And Tabs

Scope:

1. Add reviewer-name input.
2. Add fit/outreach filters.
3. Add fit/outreach table columns.
4. Add `Inspect`, `Shortlist`, `Outreach`, and `Rejected` tabs.
5. Add selected-company save form.
6. Add needs-action filtering.

Files likely changed:

1. `src/ai_hiring_radar/inspection_app.py`
2. `tests/test_inspection_app.py`

Verification:

1. Tests cover tab helper behavior and filters.
2. Manual run confirms save, refresh, and second-session visibility.

### Task 5: Documentation Update

Scope:

1. Document Supabase setup.
2. Document Streamlit Cloud secrets.
3. Document the review workflow and status meanings.
4. Document read-only fallback behavior.

Files likely changed:

1. `README.md`
2. `architecture-design-documents/04-company-review-state/DOC.md` if implementation details change during build.

Verification:

1. README setup steps are copy-pasteable.
2. Status values in README match code constants and SQL constraints.

## Open Questions

None. V1 decisions are locked:

1. Supabase Postgres is the shared state backend.
2. The feature is an extension of the existing Streamlit inspection UI.
3. Only current review state is persisted in v1.
4. Authentication is excluded from v1.
5. `Reviewer name` is optional free text.
6. Generated pipeline data remains read-only.
7. The app degrades to read-only generated inspection when Supabase is unavailable.
8. Last-write-wins is acceptable for concurrent full-form edits in v1; inline status edits do not rewrite either text field.
