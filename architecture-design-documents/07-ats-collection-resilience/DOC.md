# Design Document: ATS Collection Resilience

| Field | Value |
|-------|-------|
| **Status** | Draft |
| **Author** | OpenCode |
| **Created** | 2026-07-10 |
| **Last Updated** | 2026-07-10 |
| **Epic** | [ATS Collection Resilience](https://app.notion.com/p/39961e68244081f2a341e056e456780e) |
| **Related Issues** | - |

---

## 1. Context

The ATS collection commands currently combine two different responsibilities: optional Serper-backed board discovery and provider-specific raw ATS collection. When collection fails partway through a large run, the operator has no scalable way to continue from the already discovered board set without either rerunning discovery or manually passing many repeated `--board-url` values.

The Workable run on 2026-07-10 exposed the issue clearly. Discovery wrote `data/raw/ats_discovery/2026-07-10/workable/boards.jsonl` with 517 boards. Collection then wrote 150 raw board files before Workable started returning `429 Too Many Requests` for the remaining boards. The correct recovery action is not to run discovery again; it is to reuse the existing discovery `boards.jsonl`, skip raw files already written for the same provider/date/slug, and collect only the missing boards with more conservative request behavior.

The same operational risk exists across all ATS providers because every provider has a similar collection loop and writes stable raw file names under `data/raw/ats/<date>/<provider>/<slug>.json`. Some clients already have ad hoc request spacing, but retry/backoff and resume semantics are not shared.

---

## 2. Goals

1. Allow every `collect-*` command to run in collection-only mode from a previous board list, without calling Serper and without requiring a Serper API key.
2. Make every ATS collection command resumable by skipping existing valid raw files for the same provider, collection date, and platform company slug.
3. Add shared transient HTTP retry/backoff and request pacing for all ATS clients.
4. Preserve existing raw file layout and downstream processing compatibility.
5. Keep provider-specific collection behavior local to provider modules while sharing the generic resilience mechanics.

---

## 3. Non-Goals

1. Do not change Serper discovery retry, quota handling, or discovery query generation.
2. Do not fix provider-specific board parser false positives in this feature.
3. Do not add enriched HTTP error metadata to manifests beyond the resume/pacing fields required by this design.
4. Do not introduce a database, queue, checkpoint table, or persistent scheduler.
5. Do not add concurrency. Collection remains sequential.

---

## 4. Requirements

### 4.1 Functional Requirements

1. Each `collect-*` command accepts `--boards-file PATH`.
2. `--boards-file` supports both discovery JSONL files and plain text files with one board URL or slug per line.
3. If `--board-url` or `--boards-file` is provided, the command skips discovery and does not read `SERPER_API_KEY`.
4. `--board-url` and `--boards-file` may be combined; the resulting boards are normalized and deduplicated by provider slug.
5. Each `collect-*` command accepts `--collection-date YYYY-MM-DD`; when omitted, it uses today, matching current behavior.
6. Each `collect-*` command accepts `--resume / --no-resume`; default is `--resume`.
7. Resume skips a board when the expected raw file exists and is valid for the same provider and slug.
8. Resume includes skipped files in `result_files` so downstream processing sees a complete available raw file set.
9. Each ATS client uses shared request pacing with default `--request-delay 0.5` seconds.
10. Each ATS client retries transient HTTP failures with default `--max-retries 3`.

### 4.2 Non-Functional Requirements

1. No new runtime dependency is introduced.
2. Tests must not actually sleep; delay/backoff uses an injectable sleeper.
3. Existing provider-specific tests continue to pass.
4. Existing raw files remain readable by `process_collection`.
5. The implementation is small enough to land in independent tasks without breaking the current collection commands.

---

## 5. Current State

### 5.1 Provider Collection Shape

Each provider module defines a board dataclass, client class, collection result dataclass, and collection function:

| Provider | Client | Collection Function |
|----------|--------|---------------------|
| Ashby | `AshbyClient` | `collect_ashby_boards` |
| Greenhouse | `GreenhouseClient` | `collect_greenhouse_boards` |
| Lever | `LeverClient` | `collect_lever_boards` |
| Personio | `PersonioClient` | `collect_personio_boards` |
| Recruitee | `RecruiteeClient` | `collect_recruitee_boards` |
| SmartRecruiters | `SmartRecruitersClient` | `collect_smartrecruiters_boards` |
| Teamtailor | `TeamtailorClient` | `collect_teamtailor_boards` |
| Workable | `WorkableClient` | `collect_workable_boards` |

All collection result dataclasses currently expose:

```python
manifest_path: Path
board_count: int
result_files: list[str]
errors: list[dict[str, Any]]
```

### 5.2 Current CLI Flow

Current `collect-*` command behavior is:

```text
collect-<provider>
  -> if --board-url values are present:
       normalize those boards
       skip discovery
  -> else:
       generate discovery queries
       require Serper API key
       discover boards
  -> instantiate provider client
  -> collect_<provider>_boards(board_values, client=client)
  -> print manifest path
```

### 5.3 Current Storage

Raw ATS storage already has stable provider/date/slug paths:

```text
data/raw/ats/<collection-date>/<provider>/<stable-slug>.json
```

The path is produced by `raw_ats_dir()` and `stable_board_filename()` in `src/ai_hiring_radar/storage_json.py`. This existing path convention is enough to support resume without adding a new checkpoint file.

Discovery writes reusable board lists:

```text
data/raw/ats_discovery/<collection-date>/<provider>/boards.jsonl
```

Each JSONL line contains at least `board_url` and `platform_company_slug`.

---

## 6. Proposed Design

### 6.1 Summary

Add three shared capabilities across all ATS providers:

1. **Collection-only board input:** `--boards-file` lets operators reuse discovery outputs or plain text board lists.
2. **Resume by raw file existence:** `--resume` skips valid raw files that already exist for the target provider/date/slug.
3. **Shared resilient HTTP requests:** all ATS clients use common request pacing and transient retry/backoff.

### 6.2 New Shared Modules

Add a shared ATS collection helper module, for example:

```text
src/ai_hiring_radar/sources/collection_resilience.py
```

This module owns generic collection mechanics:

```python
DEFAULT_ATS_REQUEST_DELAY_SECONDS = 0.5
DEFAULT_ATS_MAX_RETRIES = 3
TRANSIENT_HTTP_STATUS_CODES = {429, 500, 502, 503, 504}

@dataclass(frozen=True)
class AtsHttpConfig:
    request_delay_seconds: float = DEFAULT_ATS_REQUEST_DELAY_SECONDS
    max_retries: int = DEFAULT_ATS_MAX_RETRIES
    backoff_base_seconds: float = 1.0
    backoff_max_seconds: float = 60.0

class ResilientAtsHttpClient:
    def request(...): ...
    def get(...): ...
    def post(...): ...
```

The same module can also own resume and board-file loading helpers if keeping the footprint small is preferable:

```python
def raw_ats_response_path(...): ...
def is_valid_raw_ats_response_file(...): ...
def read_board_values_file(path: Path) -> list[str]: ...
```

If the module becomes too broad during implementation, split board input helpers into `src/ai_hiring_radar/sources/board_inputs.py`. The design does not require that split up front.

### 6.3 Client Integration

Each provider client constructor accepts:

```python
request_delay_seconds: float = DEFAULT_ATS_REQUEST_DELAY_SECONDS
max_retries: int = DEFAULT_ATS_MAX_RETRIES
sleeper: Callable[[float], None] = time.sleep
```

The client wraps its existing `httpx.Client` with `ResilientAtsHttpClient` or calls the shared helper for each request.

Provider-specific behavior remains unchanged. Examples:

1. Workable still calls account, jobs, and selected job detail endpoints.
2. Ashby still calls board GraphQL and selected job detail GraphQL.
3. Recruitee still calls offers and selected offer detail endpoints.
4. Lever still attempts global and EU endpoints with the existing 404 fallback behavior.
5. SmartRecruiters still paginates until `totalFound` is exhausted.

### 6.4 Resume Semantics

Each `collect_<provider>_boards()` accepts:

```python
collection_date: str | None = None
resume: bool = False
```

The collection date is normalized through the existing `format_date()` semantics. When `resume=True`, the collector computes the expected raw path before making network calls:

```text
data/raw/ats/<collection-date>/<provider>/<stable-slug>.json
```

If the file exists and is valid, collection skips network calls for that board and appends the path to `result_files` and `resumed_files`.

A valid resumable raw file is a readable JSON object with:

1. `record_type == "raw_ats_response"`
2. `platform` matching the provider
3. `platform_company_slug` matching the normalized board slug

If the file is missing, invalid JSON, not an object, or mismatched, the collector fetches the board and writes a fresh raw file.

### 6.5 Manifest Semantics

`result_files` remains backward compatible and contains every raw file available for downstream processing, including resumed and newly written files.

Add these manifest fields:

```json
{
  "collection_date": "2026-07-10",
  "resume": true,
  "result_files": ["... all available files ..."],
  "written_files": ["... files written during this run ..."],
  "resumed_files": ["... files skipped because they already existed ..."],
  "errors": []
}
```

Provider collection result dataclasses add the same two lists:

```python
written_files: list[str]
resumed_files: list[str]
```

`successful_count` remains `len(result_files)` to preserve current user-facing meaning: available raw board files.

### 6.6 Collection-Only Inputs

Every `collect-*` command accepts:

```text
--boards-file PATH
```

Supported file formats:

1. Discovery JSONL, where each line is a JSON object and `board_url` is preferred over `platform_company_slug`.
2. Plain text, where each non-empty line is a board URL or slug.

If `--board-url` and `--boards-file` are both provided, combine them and dedupe after provider normalization.

If no explicit board input is provided, the command keeps the current behavior and runs discovery.

---

## 7. Data Model

No database model changes are required.

### 7.1 Collection Result Dataclasses

Each provider collection result dataclass changes from:

```python
result_files: list[str]
errors: list[dict[str, Any]]
```

to:

```python
result_files: list[str]
written_files: list[str]
resumed_files: list[str]
errors: list[dict[str, Any]]
```

### 7.2 Collection Manifests

Existing manifest readers are expected to tolerate extra fields because manifests are JSON objects. `result_files` keeps its existing meaning, so downstream processing is unaffected.

New fields are additive:

| Field | Type | Meaning |
|-------|------|---------|
| `collection_date` | string | Normalized date used for raw output paths. |
| `resume` | bool | Whether resume skipping was enabled. |
| `written_files` | list[string] | Files created or overwritten during this run. |
| `resumed_files` | list[string] | Existing valid files reused during this run. |

### 7.3 Board Input Files

No new persisted board file format is introduced. Existing discovery `boards.jsonl` becomes an accepted CLI input. Plain text board lists are accepted for operator convenience.

---

## 8. Interfaces

### 8.1 CLI

Every `collect-*` command adds:

```text
--boards-file PATH
--collection-date YYYY-MM-DD
--resume / --no-resume      # default: --resume
--request-delay FLOAT       # default: 0.5
--max-retries INT           # default: 3
```

Example recovery command:

```bash
uv run ai-hiring-radar collect-workable \
  --boards-file data/raw/ats_discovery/2026-07-10/workable/boards.jsonl \
  --collection-date 2026-07-10 \
  --resume \
  --request-delay 0.5 \
  --max-retries 3
```

Expected recovery behavior for the 2026-07-10 Workable run:

```text
read boards.jsonl -> 517 boards
find 150 existing valid raw files
skip those 150 files
fetch the 367 missing boards with request pacing and retry/backoff
write a manifest with result_files = 150 resumed + newly written files
```

### 8.2 Provider Collection Functions

Each collection function adds keyword-only parameters:

```python
collection_date: str | None = None
resume: bool = False
```

The default remains current behavior for internal callers: use today and refetch unless CLI passes `resume=True`.

### 8.3 Provider Clients

Each provider client constructor adds keyword-only parameters:

```python
request_delay_seconds: float = 0.5
max_retries: int = 3
sleeper: Callable[[float], None] = time.sleep
```

Tests can pass `request_delay_seconds=0` or `sleeper=list.append`.

---

## 9. Execution Flow

### 9.1 Current Flow

```text
collect-workable
  -> no --board-url provided
  -> build discovery queries
  -> require Serper API key
  -> discover_workable_boards(...)
  -> board_values from discovery result
  -> WorkableClient()
  -> collect_workable_boards(board_values, client=client)
      -> for every board, fetch regardless of existing raw file
      -> write data/raw/ats/<today>/workable/<slug>.json
      -> record errors and continue
```

### 9.2 Proposed Discovery Plus Collection Flow

```text
collect-workable
  -> no --board-url and no --boards-file
  -> build discovery queries
  -> require Serper API key
  -> discover_workable_boards(...)
  -> board_values from discovery result
  -> WorkableClient(request_delay_seconds=0.5, max_retries=3)
  -> collect_workable_boards(
       board_values,
       collection_date=<today>,
       resume=True,
     )
      -> skip existing valid raw files if rerun on same date
      -> fetch missing boards with resilient HTTP helper
      -> write manifest with written/resumed split
```

### 9.3 Proposed Collection-Only Recovery Flow

```text
collect-workable --boards-file data/raw/ats_discovery/2026-07-10/workable/boards.jsonl --collection-date 2026-07-10
  -> read board values from boards file
  -> do not build discovery queries
  -> do not require Serper API key
  -> WorkableClient(request_delay_seconds=0.5, max_retries=3)
  -> collect_workable_boards(..., collection_date="2026-07-10", resume=True)
      -> for each normalized board slug:
          -> expected raw path exists and valid: add to resumed_files, skip network
          -> otherwise: fetch, write, add to written_files
      -> write manifest
```

---

## 10. Error Handling

### 10.1 Retryable HTTP Failures

Retry these HTTP status codes:

```python
{429, 500, 502, 503, 504}
```

On `429` or `503`, if `Retry-After` is present, sleep for that duration before retrying. Otherwise use capped exponential backoff:

```text
retry 1: 1 second
retry 2: 2 seconds
retry 3: 4 seconds
cap: 60 seconds
```

`--max-retries 3` means up to three retries after the first failed attempt.

### 10.2 Non-Retryable HTTP Failures

Do not retry `400`, `401`, `403`, `404`, or other non-transient statuses. Existing provider collection behavior remains: record the board-level error and continue to the next board.

### 10.3 Request Delay

Request delay is applied between HTTP requests on the same provider client instance. It is not applied before the first request. Backoff sleeps for retry attempts are separate from the steady request delay.

### 10.4 Resume Validation Failures

If a candidate resume file is unreadable, invalid JSON, not a JSON object, or does not match provider/slug, it is ignored for resume purposes and collection fetches the board normally. This avoids treating corrupt partial files as successful data.

### 10.5 Board File Failures

If `--boards-file` does not exist or cannot be parsed as either supported format, the command exits with a clear CLI error before making network calls.

---

## 11. Observability

CLI output changes from:

```text
Workable collection complete: 150/517 raw board file(s) written; 367 error(s).
```

to:

```text
Workable collection complete: 517/517 raw board file(s) available; 367 written, 150 resumed; 0 error(s).
```

If errors remain:

```text
Workable collection complete: 480/517 raw board file(s) available; 330 written, 150 resumed; 37 error(s).
```

The manifest records `written_files` and `resumed_files`, making it clear whether a run did new network work or reused previous raw files.

---

## 12. Testing

### 12.1 Unit Tests

Add tests for the shared HTTP helper:

1. Retries `429` and succeeds.
2. Honors `Retry-After` without real sleeping.
3. Retries `500`, `502`, `503`, and `504`.
4. Does not retry `404`.
5. Applies steady request delay between successful requests.

### 12.2 Collection Resume Tests

Add representative tests, then provider-specific coverage where needed:

1. Existing valid raw file is skipped when `resume=True`.
2. Existing invalid raw file is refetched when `resume=True`.
3. Existing valid raw file is refetched when `resume=False`.
4. `result_files`, `written_files`, and `resumed_files` are reflected in the manifest.

### 12.3 CLI Tests

Add CLI tests for:

1. `--boards-file` JSONL dry run prints normalized board URLs.
2. `--boards-file` plain text dry run prints normalized board URLs.
3. `--boards-file` skips discovery and does not require Serper.
4. `--collection-date` is passed to collection functions.
5. `--request-delay`, `--max-retries`, and `--resume/--no-resume` are passed to clients/collectors.

### 12.4 Manual Verification

Use a small Workable rerun with the existing discovery file:

```bash
uv run ai-hiring-radar collect-workable \
  --boards-file data/raw/ats_discovery/2026-07-10/workable/boards.jsonl \
  --collection-date 2026-07-10 \
  --resume \
  --request-delay 0.5 \
  --max-retries 3
```

Expected: existing raw files are resumed and only missing boards are fetched.

---

## 13. User Stories

**US-1:** As an operator, I rerun collection from a previous discovery `boards.jsonl`, so that I can recover from provider rate limits without spending Serper credits again.
**Acceptance test:** `tests/test_cli.py::test_collect_boards_file_skips_discovery`

---

**US-2:** As an operator, I rerun collection for the same provider/date with `--resume`, so that existing valid raw files are skipped and only missing boards are fetched.
**Acceptance test:** `tests/test_workable.py::test_collect_workable_boards_resumes_existing_raw_file`

---

**US-3:** As an operator, I pass a plain text board list, so that I can collect from manually curated board URLs without JSONL formatting.
**Acceptance test:** `tests/test_cli.py::test_collect_boards_file_supports_plain_text`

---

**US-4:** As the system, when an ATS provider returns a transient `429` or `5xx`, the client retries with delay/backoff before recording a board error.
**Acceptance test:** `tests/test_collection_resilience.py::test_resilient_http_retries_transient_status`

---

**US-5:** As the system, when a resume candidate file is corrupt or mismatched, collection refetches it instead of silently treating it as successful.
**Acceptance test:** `tests/test_workable.py::test_collect_workable_boards_refetches_invalid_resume_file`

---

## 14. Decisions Made

1. **Use shared HTTP helper:** Retry/backoff and request pacing belong in one shared source helper, not copied into each provider.
2. **Retry transient statuses only:** Retry `429`, `500`, `502`, `503`, and `504`; do not retry `400`, `401`, `403`, or `404`.
3. **Default delay is 0.5 seconds:** This is the default `--request-delay` for every ATS client.
4. **Default max retries is 3:** `--max-retries 3` means up to three retries after the first failed attempt.
5. **Resume is default-on in CLI:** Operators can force refresh with `--no-resume`.
6. **Resume is path and content based:** A raw file is resumable only when it exists at the expected provider/date/slug path and contains matching raw ATS metadata.
7. **`--boards-file` supports JSONL and plain text:** Discovery outputs and manual board lists are both first-class collection inputs.
8. **No discovery when explicit board input exists:** Any `--board-url` or `--boards-file` input means collection-only mode.
9. **Keep `result_files` backward compatible:** It means all available raw files, including resumed files.
10. **Do not add parser fixes or error metadata in this feature:** Those are intentionally deferred.

---

## 15. Rollout

This is a code-only rollout with no migration.

1. Land shared helpers and tests first without changing CLI behavior.
2. Migrate clients to shared HTTP behavior with equivalent default or more conservative pacing.
3. Add resume support to collection functions while preserving existing defaults for internal callers.
4. Add CLI options with `--resume` default-on.
5. Verify Workable recovery with the 2026-07-10 discovery file.

Existing raw and processed files remain compatible. Existing commands without new options still work, but same-day collection reruns from CLI will skip existing valid raw files unless `--no-resume` is passed.

---

## 16. Task Breakdown

### Task 1: Add Shared Collection Resilience Helpers

Files:

```text
src/ai_hiring_radar/sources/collection_resilience.py
tests/test_collection_resilience.py
```

Scope:

1. Add default constants, retry config, resilient HTTP request helper, raw resume path/validation helper, and board-file reader.
2. Cover retry, `Retry-After`, delay, non-retryable status, resume validation, and board-file parsing in tests.

Dependencies: none.

### Task 2: Migrate ATS Clients To Shared HTTP Helper

Files:

```text
src/ai_hiring_radar/sources/{ashby,greenhouse,lever,personio,recruitee,smartrecruiters,teamtailor,workable}.py
tests/test_{ashby,greenhouse,lever,personio,recruitee,smartrecruiters,teamtailor,workable}.py
```

Scope:

1. Add `request_delay_seconds`, `max_retries`, and `sleeper` constructor args.
2. Replace direct `httpx.Client.get/post` calls with shared helper calls.
3. Preserve provider-specific request order and validation.

Dependencies: Task 1.

### Task 3: Add Resume And Collection Date To Provider Collectors

Files:

```text
src/ai_hiring_radar/sources/{ashby,greenhouse,lever,personio,recruitee,smartrecruiters,teamtailor,workable}.py
tests/test_{ashby,greenhouse,lever,personio,recruitee,smartrecruiters,teamtailor,workable}.py
```

Scope:

1. Add `collection_date` and `resume` kwargs to each collector.
2. Add `written_files` and `resumed_files` to result dataclasses and manifests.
3. Preserve `result_files` semantics.

Dependencies: Task 1.

### Task 4: Add Collection-Only CLI Inputs And Options

Files:

```text
src/ai_hiring_radar/cli.py
tests/test_cli.py
```

Scope:

1. Add `--boards-file`, `--collection-date`, `--resume/--no-resume`, `--request-delay`, and `--max-retries` to every `collect-*` command.
2. Combine and dedupe `--board-url` and `--boards-file` inputs.
3. Skip discovery and Serper key checks when explicit board input exists.
4. Update CLI output to show available/written/resumed/error counts.

Dependencies: Tasks 2 and 3.

### Task 5: Verify Workable Recovery And Update Operational Notes

Files:

```text
architecture-design-documents/07-ats-collection-resilience/DOC.md
```

Scope:

1. Run relevant tests.
2. Manually verify collection-only Workable recovery against the existing 2026-07-10 board file if network access and rate limits allow.
3. Record any final rollout notes in the design doc changelog or implementation summary.

Dependencies: Task 4.

---

## 17. Notion Tracking

| Type | Name | URL |
|------|------|-----|
| Epic | ATS Collection Resilience | https://app.notion.com/p/39961e68244081f2a341e056e456780e |
| Task 1 | Add shared ATS collection resilience helpers | https://app.notion.com/p/39961e682440813da4fad480061810ce |
| Task 2 | Migrate ATS clients to shared HTTP helper | https://app.notion.com/p/39961e6824408117ac2dc32001dd7670 |
| Task 3 | Add resume and collection date to ATS collectors | https://app.notion.com/p/39961e68244081be9093f388520c550f |
| Task 4 | Add collection-only CLI inputs and options | https://app.notion.com/p/39961e682440817abb4aca1cd2f9d0a9 |
| Task 5 | Verify Workable recovery and update operational notes | https://app.notion.com/p/39961e682440811db6c6fdf016adabe1 |

Dependency graph:

```text
Task 1
  -> Task 2
  -> Task 3
Task 2 + Task 3
  -> Task 4
Task 4
  -> Task 5
```

---

## 18. Open Questions

None. Defaults and scope are locked for this design.

---

## 19. Changelog

2026-07-10 - OpenCode - Added Notion epic and linked task tracking.
