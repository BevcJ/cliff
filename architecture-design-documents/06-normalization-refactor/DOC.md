# Design Document: ATS Normalization Refactor

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Author** | OpenCode |
| **Created** | 2026-07-10 |
| **Last Updated** | 2026-07-10 |
| **Epic** | AI Hiring Radar normalization maintainability |
| **Related Issues** | - |

---

## 1. Overview

### 1.1 Problem Statement

`src/ai_hiring_radar/normalize.py` has become a 2,000+ line mixed-responsibility module. It contains processing orchestration, raw file discovery, legacy LinkedIn/Serper search normalization, raw ATS dispatch, and provider-specific normalization logic for Ashby, Greenhouse, Lever, Personio, Recruitee, SmartRecruiters, Teamtailor, and Workable.

This shape is hard to maintain because every provider change requires editing the same central file. It also makes provider-specific behavior harder to review: a small Teamtailor change sits next to Recruitee detail merging, Ashby team handling, shared country inference glue, XML helpers, HTML cleanup, and the top-level processing pipeline.

The first split already happened for Workable in `src/ai_hiring_radar/normalizers/workable.py`, but it copied common helpers such as company cleanup, optional text cleaning, country-code normalization, role classification, and candidate record assembly. That creates a second maintenance problem: shared behavior can now diverge between Workable and the other providers.

There is also a legacy LinkedIn-safe search path still wired through the CLI and processing layer. The `collect` command collects raw Serper Google search files for LinkedIn job results, `normalize.py` can normalize those raw search results into `job_candidate` records, and `run` orchestrates that legacy collection path. This path is no longer part of the desired product direction. Serper remains useful, but only as a search client for ATS board discovery.

### 1.2 Proposed Solution

Replace the central `normalize.py` module with an ATS-only normalization architecture:

1. Move processing orchestration to `src/ai_hiring_radar/processing.py`.
2. Split each ATS provider normalizer into `src/ai_hiring_radar/normalizers/ats/<provider>/normalizer.py`.
3. Add `src/ai_hiring_radar/normalizers/ats/registry.py` as the single raw ATS dispatch point.
4. Extract shared normalization utilities into `src/ai_hiring_radar/normalizers/common/`.
5. Introduce a shared `build_ats_candidate(...)` builder for common `job_candidate` fields.
6. Remove the legacy LinkedIn-safe raw search normalization path.
7. Remove the CLI `collect` and `run` commands because they are LinkedIn-safe search commands.
8. Keep Serper as a generic client for ATS discovery commands only.
9. Remove `SourceMode.LINKEDIN_SAFE_SEARCH` while keeping `SourceName.SERPER_GOOGLE` for ATS discovery metadata.

The implementation must preserve ATS normalized candidate output exactly. Refactoring may delete the legacy LinkedIn/Serper candidate path, but it must not change ATS candidate fields, field values, list ordering, IDs, title filtering, country inference behavior, or aggregation results.

### 1.3 Terminology

| Term | Definition |
|------|------------|
| **ATS** | Applicant Tracking System public job board provider such as Ashby, Greenhouse, Lever, Personio, Recruitee, SmartRecruiters, Teamtailor, or Workable. |
| **Provider normalizer** | Provider-specific code that converts one raw ATS provider response into zero or more normalized `job_candidate` dictionaries. |
| **Processing pipeline** | The stage that reads raw ATS files for a collection date, normalizes candidates, deduplicates candidates, aggregates companies, and writes processed JSONL files. |
| **Shared candidate builder** | A common helper that assembles repeated ATS `job_candidate` base fields and rejects accidental duplicate provider-specific fields. |
| **Legacy LinkedIn path** | The old Serper Google search flow that queries `site:linkedin.com/jobs/view`, stores raw search files, and normalizes concrete LinkedIn job URLs into candidates. This path is removed by this feature. |
| **ATS discovery** | Serper-backed search that discovers public ATS board URLs. This remains in scope and is not the same as the removed LinkedIn candidate path. |

---

## 2. Architecture

### 2.1 Current Flow

Current provider collection and processing are coupled through `normalize.py`:

```text
collect-<provider>
  -> sources.<provider>.discover_<provider>_boards(...)  # optional Serper ATS discovery
  -> sources.<provider>.collect_<provider>_boards(...)
  -> writes data/raw/ats/YYYY-MM-DD/<provider>/*.json

collect                                      # legacy LinkedIn path
  -> query_builder.generate_search_queries(...)
  -> sources.serper_google.collect_searches(...)
  -> writes data/raw/searches/YYYY-MM-DD/serper_google/*.json

run                                          # legacy LinkedIn path
  -> collect_searches(...)
  -> normalize.process_collection(...)
  -> export_company_review_files(...)

process
  -> normalize.process_collection(...)
      -> normalize._raw_input_files(...)
          -> raw search files if present
          -> raw ATS files if present
      -> normalize.normalize_raw_search_file(...)       # legacy LinkedIn path
      -> normalize.normalize_raw_ats_file(...)
          -> if platform == greenhouse: normalize_greenhouse_job(...)
          -> if platform == lever: normalize_lever_posting(...)
          -> ...
          -> ashby fallback when platform is empty
      -> dedupe_job_candidates(...)
      -> aggregate_companies(...)
      -> write processed JSONL
```

Current module-level problems:

| Area | Current Location | Problem |
|------|------------------|---------|
| Processing orchestration | `normalize.py` | Mixed with provider internals. |
| LinkedIn search normalization | `normalize.py` | Legacy path still affects processing behavior. |
| ATS dispatch | `normalize.py` | Large platform `if` chain. |
| Provider normalization | `normalize.py` plus partial `normalizers/workable.py` | Most providers are central; Workable duplicates common helpers. |
| Search location helpers | `query_builder.py` | Reusable location depth helpers are mixed with LinkedIn query building. |
| Serper raw search collection | `sources/serper_google.py` | LinkedIn-specific raw collection helpers live beside the reusable Serper client. |

### 2.2 Proposed Flow

```text
collect-<provider>
  -> sources.<provider>.discover_<provider>_boards(...)  # unchanged, uses Serper for ATS discovery
  -> sources.<provider>.collect_<provider>_boards(...)   # unchanged raw ATS collection
  -> writes data/raw/ats/YYYY-MM-DD/<provider>/*.json

process
  -> processing.process_collection(...)                  # NEW owner
      -> processing.iter_raw_ats_response_files(...)     # ATS-only input discovery
      -> normalizers.ats.registry.normalize_raw_ats_file(...)
          -> common.raw.raw_ats_response_payload(...)
          -> provider normalize_response(...)
              -> provider-specific parsing
              -> common helpers for text/company/roles/countries/XML/HTML
              -> common.candidate.build_ats_candidate(...)
      -> dedupe_job_candidates(...)
      -> aggregate_companies(...)
      -> write processed JSONL
```

Removed flow:

```text
collect                                      # REMOVED
  -> no longer collects LinkedIn-safe raw search files

run                                          # REMOVED
  -> no replacement in this feature

process
  -> no longer reads data/raw/searches/...   # CHANGED
  -> no longer normalizes LinkedIn results   # CHANGED
```

Key differences:

| Difference | Effect |
|------------|--------|
| `normalize.py` is deleted | There is no central provider implementation file. |
| `processing.py` owns orchestration | Processing is readable without provider internals. |
| Registry owns ATS dispatch | Adding a provider requires a provider module plus one registry entry. |
| Common builder owns base candidate fields | Repeated ATS candidate dict construction is centralized. |
| LinkedIn-safe search is removed | Processing is ATS-only; Serper remains only for ATS discovery. |
| `query_builder.py` is deleted | Location helpers move to `search_locations.py`; LinkedIn query functions disappear. |

---

## 3. Database Design

### 3.1 New / Modified Tables

No schema changes. The application continues to use file-based raw and processed JSON/JSONL artifacts for this part of the pipeline.

### 3.2 Schema Summary

| Table | Change | Details |
|-------|--------|---------|
| None | No change | This feature does not introduce database tables, columns, migrations, or database-backed processing. |

### 3.3 Migration Strategy

No database migration is required. Existing raw ATS files remain readable. Existing raw LinkedIn search files are no longer processed by the application after this refactor.

---

## 4. Normalization Module Design

### 4.1 Target Package Structure

```text
src/ai_hiring_radar/
  processing.py
  search_locations.py

  normalizers/
    __init__.py

    common/
      __init__.py
      candidate.py
      company.py
      countries.py
      html.py
      raw.py
      roles.py
      text.py
      xml.py

    ats/
      __init__.py
      registry.py

      ashby/
        __init__.py
        normalizer.py
      greenhouse/
        __init__.py
        normalizer.py
      lever/
        __init__.py
        normalizer.py
      personio/
        __init__.py
        normalizer.py
      recruitee/
        __init__.py
        normalizer.py
      smartrecruiters/
        __init__.py
        normalizer.py
      teamtailor/
        __init__.py
        normalizer.py
      workable/
        __init__.py
        normalizer.py
```

### 4.2 Provider Normalizer Contract

Each provider normalizer exports a provider-level response normalizer:

```python
from pathlib import Path
from typing import Any


def normalize_response(
    *,
    metadata: dict[str, Any],
    response: Any,
    raw_file: Path,
) -> list[dict[str, Any]]:
    ...
```

Provider modules may also expose focused pure helpers for provider-specific parsing, such as `greenhouse_jobs(...)`, `teamtailor_items(...)`, or `recruitee_offer_detail(...)`, but the registry only calls `normalize_response(...)`.

Provider modules must not import from `ai_hiring_radar.processing` or the deleted `ai_hiring_radar.normalize`. They may import from:

| Import Area | Allowed Purpose |
|-------------|-----------------|
| `ai_hiring_radar.normalizers.common.*` | Shared normalization utilities and candidate assembly. |
| `ai_hiring_radar.classify` | Existing role classification and title normalization behavior. |
| `ai_hiring_radar.country_inference` | Existing country inference behavior. |
| `ai_hiring_radar.hashing` | Stable provider fallback IDs. |
| `ai_hiring_radar.models` | Source names, source modes, evidence quality. |

### 4.3 ATS Registry

`normalizers/ats/registry.py` owns raw ATS file normalization:

```python
NORMALIZERS = {
    SourceName.ASHBY.value: ashby.normalize_response,
    SourceName.GREENHOUSE.value: greenhouse.normalize_response,
    SourceName.LEVER.value: lever.normalize_response,
    SourceName.PERSONIO.value: personio.normalize_response,
    SourceName.RECRUITEE.value: recruitee.normalize_response,
    SourceName.SMARTRECRUITERS.value: smartrecruiters.normalize_response,
    SourceName.TEAMTAILOR.value: teamtailor.normalize_response,
    SourceName.WORKABLE.value: workable.normalize_response,
}
```

Registry behavior:

| Case | Behavior |
|------|----------|
| Known `platform` | Dispatch to the matching provider normalizer. |
| Empty or missing `platform` | Preserve existing Ashby fallback and attempt Ashby normalization. |
| Unknown non-empty `platform` | Return `[]`. |
| Non-dict raw file payload | Return `[]`. |
| Raw wrapper with `record_type == raw_ats_response` | Use wrapper as metadata and `response` as provider payload. |
| Raw provider payload without wrapper | Use empty metadata and the full payload as response, preserving current behavior. |

### 4.4 Shared Candidate Builder

`normalizers/common/candidate.py` introduces one ATS builder:

```python
def build_ats_candidate(
    *,
    source: SourceName,
    metadata: dict[str, Any],
    raw_file: Path,
    platform_company_slug: str,
    platform_job_id: str,
    board_url: str,
    source_url: str,
    job_title_raw: str,
    company_raw: object | None,
    country_inference: CountryInference,
    role_search_term: str | None = None,
    job_url: str | None = None,
    location: str | None = None,
    job_locations_raw: list[str] | None = None,
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ...
```

The builder owns repeated base fields:

| Field Group | Fields |
|-------------|--------|
| Record identity | `record_type`, `job_id`, `platform`, `platform_company_slug`, `platform_job_id` |
| Countries | `country_code`, `country`, `job_country_codes`, `job_countries` |
| Search metadata passthrough | `search_location_label`, `query_location`, `serper_location` |
| Source metadata | `source`, `source_mode`, `source_url`, `board_url`, `job_url` |
| Search-result legacy placeholders | `result_rank`, `displayed_link`, `search_query`, `snippet` |
| Company | `company_raw`, `company_normalized` |
| Role | `job_title_raw`, `job_title_normalized`, `role_search_term`, `role_group` |
| Review metadata | `evidence_quality`, `needs_review`, `collected_at`, `raw_file` |
| Location base | `location`, `job_location_raw`, `job_locations_raw` |

The builder must preserve exact current ATS output. That includes keeping base fields whose values are `None`, empty strings, or empty lists when current provider output includes them.

`extra_fields` is only for provider-specific fields such as `team`, `department`, `description`, `workplace_type`, `employment_type`, `offer_slug`, `remote_status`, or provider-native raw structures.

Conflict rule:

| Case | Behavior |
|------|----------|
| `extra_fields` includes a base builder key | Raise `ValueError`. |
| Provider needs a different base value | Pass the value through the explicit builder argument. |
| Provider-specific optional field is currently emitted as `None` | Continue emitting it through `extra_fields`. |

### 4.5 Common Helper Modules

| Module | Responsibilities |
|--------|------------------|
| `common/text.py` | `clean_optional`, `append_clean_unique`, `first_value`, `first_or_empty`, clean list helpers. |
| `common/company.py` | `normalize_company_name`, company cleanup, generic company filtering, `company_name_from_slug`. |
| `common/roles.py` | `ats_role_search_term`, role field calculation, provider-configurable title gates. |
| `common/countries.py` | Shared country-code normalization such as `gb` to `uk`, `CountryInference` field helpers, country code append helpers. |
| `common/raw.py` | Raw ATS wrapper unwrapping and raw ATS file iteration helpers used by processing and registry. |
| `common/xml.py` | XML local-name, child lookup, children lookup, and child text extraction. |
| `common/html.py` | HTML-to-text cleanup currently needed by Teamtailor and future provider details. |

Title filtering must preserve each provider's current policy. The current ATS providers use `is_ai_role_title_candidate(...)`, including its AI-trainer exclusion; future provider-specific deviations should be explicit in that provider normalizer instead of hidden inside shared helpers.

---

## 5. Legacy LinkedIn Removal

### 5.1 Removed CLI Commands

Remove these commands from `src/ai_hiring_radar/cli.py`:

| Command | Reason |
|---------|--------|
| `collect` | It only collects LinkedIn-safe raw Serper search files. |
| `run` | It orchestrates legacy LinkedIn collection, processing, and export. No replacement is needed in this feature. |

Existing provider-specific commands remain:

| Command Family | Status |
|----------------|--------|
| `discover-<provider>` | Keep. These use Serper for ATS board discovery. |
| `collect-<provider>` | Keep. These write raw ATS files. |
| `process` | Keep and change to ATS-only processing. |
| `export` and downstream enrichment/extraction commands | Keep if they consume processed ATS candidate files. |

### 5.2 Removed Raw Search Storage

Remove raw LinkedIn search storage helpers from `storage_json.py`:

| Helper | Reason |
|--------|--------|
| `raw_search_dir(...)` | Only used by legacy LinkedIn raw search files. |
| `write_raw_search_response(...)` | Only used by legacy LinkedIn raw search files. |
| `stable_search_filename(...)` | Only used by legacy LinkedIn raw search files. |
| `DEFAULT_SOURCE_NAME` | Only used by raw search storage. |

Keep ATS and processed storage helpers such as `raw_ats_dir(...)`, `ats_discovery_dir(...)`, `write_raw_ats_response(...)`, and `write_processed_jsonl(...)`.

### 5.3 Removed Query Builder Surface

Delete `src/ai_hiring_radar/query_builder.py` after moving reusable location helpers to `src/ai_hiring_radar/search_locations.py`.

Move and keep:

| Symbol | New Location | Reason |
|--------|--------------|--------|
| `LocationDepth` | `search_locations.py` | Used by ATS discovery query generation. |
| `country_search_location(...)` | `search_locations.py` | Used by ATS discovery location iteration. |
| `iter_search_locations(...)` | `search_locations.py` | Used by ATS discovery query generation. |

Remove:

| Symbol | Reason |
|--------|--------|
| `SearchQuery` | LinkedIn-safe search only. |
| `build_linkedin_jobs_query(...)` | LinkedIn-safe search only. |
| `build_google_search_query(...)` | LinkedIn-safe search only. |
| `generate_search_queries(...)` | LinkedIn-safe search only. |

### 5.4 Serper Client Cleanup

Keep `src/ai_hiring_radar/sources/serper_google.py`, but reduce it to generic Serper search behavior used by ATS discovery.

Keep:

| Symbol | Reason |
|--------|--------|
| `SerperGoogleClient` | `discover-*` and `collect-*` ATS commands use it. |
| `normalize_serper_response(...)` | Generic Serper response normalization. |
| `redact_secret_fields(...)` | Still useful for safe error/response handling and tests. |

Remove:

| Symbol | Reason |
|--------|--------|
| `CollectionResult` | LinkedIn raw search collection only. |
| `build_raw_search_record(...)` | LinkedIn raw search collection only. |
| `build_collection_manifest(...)` | LinkedIn raw search collection only. |
| `query_error_record(...)` | LinkedIn raw search collection only. |
| `collect_searches(...)` | LinkedIn raw search collection only. |

The client should accept ATS discovery query objects via a small protocol:

```python
class SerperSearchRequest(Protocol):
    request_params: dict[str, str | int]
```

### 5.5 Model Enum Cleanup

Remove `SourceMode.LINKEDIN_SAFE_SEARCH` from `src/ai_hiring_radar/models.py`.

Keep `SourceName.SERPER_GOOGLE` because ATS discovery records still identify Serper as the discovery search source.

---

## 6. Processing and Import Migration

### 6.1 New Processing Module

`src/ai_hiring_radar/processing.py` owns top-level processing:

```python
@dataclass(frozen=True)
class ProcessingResult:
    job_candidates_path: Path
    companies_path: Path
    raw_file_count: int
    candidate_count: int
    deduped_candidate_count: int
    company_count: int


def build_job_candidates(
    collection_date: str,
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
) -> list[dict[str, Any]]:
    ...


def process_collection(
    collection_date: str,
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
) -> ProcessingResult:
    ...
```

Processing reads only raw ATS files from `data/raw/ats/YYYY-MM-DD/<platform>/*.json`.

If no raw ATS files exist for a date, processing raises `FileNotFoundError` with a message that lists expected ATS directories. It must no longer mention `data/raw/searches`.

### 6.2 Import Migration

Update callers from:

```python
from ai_hiring_radar.normalize import process_collection
from ai_hiring_radar.normalize import normalize_raw_ats_file
from ai_hiring_radar.query_builder import LocationDepth
```

to:

```python
from ai_hiring_radar.processing import process_collection
from ai_hiring_radar.normalizers.ats.registry import normalize_raw_ats_file
from ai_hiring_radar.search_locations import LocationDepth
```

No compatibility import shim is required for `ai_hiring_radar.normalize`. The module is deleted and imports are updated.

---

## 7. Non-Applicable Application Layers

### 7.1 Generation Layer

N/A. This refactor does not change LLM prompts, Pydantic AI agents, model configuration, job description extraction prompts, or company enrichment prompts.

### 7.2 CRUD Layer

N/A. There is no CRUD layer involved in this file-based normalization refactor.

### 7.3 Celery Task Layer

N/A. The current application uses synchronous Typer CLI commands for this pipeline. No Celery tasks are added or modified.

### 7.4 API Layer

N/A. No HTTP endpoints or request/response models are changed.

### 7.5 Frontend

N/A. No frontend code is changed.

---

## 8. Testing Strategy

### 8.1 Behavior Lock

All ATS provider output must be preserved exactly. Existing provider tests are the primary behavior lock:

| Provider | Test File |
|----------|-----------|
| Ashby | `tests/test_ashby.py` |
| Greenhouse | `tests/test_greenhouse.py` |
| Lever | `tests/test_lever.py` |
| Personio | `tests/test_personio.py` |
| Recruitee | `tests/test_recruitee.py` |
| SmartRecruiters | `tests/test_smartrecruiters.py` |
| Teamtailor | `tests/test_teamtailor.py` |
| Workable | `tests/test_workable.py` |

These tests should update imports but keep expected candidate assertions unchanged unless an assertion only covered the removed LinkedIn path.

### 8.2 New Unit Tests

Add tests for:

| Test Area | Required Coverage |
|-----------|-------------------|
| ATS registry | Known platform dispatch, empty-platform Ashby fallback, unknown-platform skip. |
| Candidate builder | Base fields, role fields, country fields, metadata passthrough, exact `None` preservation, duplicate `extra_fields` rejection. |
| Common helpers | Company cleanup, slug-to-company name, `gb` to `uk` country-code normalization, XML child text helpers, HTML cleanup. |
| Processing | ATS-only file discovery, no raw search fallback, FileNotFoundError message. |
| Serper client | Generic request execution and response normalization without raw LinkedIn collection. |
| Search locations | `LocationDepth` and `iter_search_locations(...)` after moving from `query_builder.py`. |

### 8.3 Removed or Reworked Tests

| Test File | Change |
|-----------|--------|
| `tests/test_normalize.py` | Delete or replace with common helper and registry tests. Current LinkedIn normalizer assertions are removed. |
| `tests/test_query_builder.py` | Replace with `tests/test_search_locations.py` covering only location helper behavior. LinkedIn query tests are removed. |
| `tests/test_serper_google.py` | Keep client/response tests; remove raw LinkedIn collection and manifest tests. |
| `tests/test_storage_json.py` | Remove raw search path/write tests. Keep raw ATS and processed storage tests. |
| `tests/test_processing_exports.py` | Replace LinkedIn raw fixture with an ATS raw fixture. |
| `tests/test_job_description_extraction.py` | Update sample candidate records away from `source=serper_google` if the test is intended to represent normalized pipeline output. |

### 8.4 Verification Commands

Run after implementation:

```bash
uv run pytest tests/test_ashby.py tests/test_greenhouse.py tests/test_lever.py tests/test_personio.py
uv run pytest tests/test_recruitee.py tests/test_smartrecruiters.py tests/test_teamtailor.py tests/test_workable.py
uv run pytest tests/test_processing_exports.py tests/test_serper_google.py tests/test_storage_json.py
uv run pytest
```

---

## 9. Edge Cases & Behaviour

1. **Raw file has unknown non-empty platform:** `normalizers.ats.registry.normalize_raw_ats_file(...)` returns `[]`. Processing continues with other files.

2. **Raw file has empty or missing platform:** Registry preserves current Ashby fallback and attempts Ashby normalization. This keeps older Ashby raw files processable.

3. **Only legacy raw search files exist for a date:** `processing.process_collection(...)` raises `FileNotFoundError` because the processing pipeline is now ATS-only. The error message lists expected ATS raw directories and does not mention raw search directories.

4. **Provider `extra_fields` collides with base builder field:** `build_ats_candidate(...)` raises `ValueError`. This catches accidental output changes during tests instead of silently overriding base fields.

5. **Provider has no valid title:** Provider normalizer returns no candidate for that job, preserving current behavior.

6. **Provider-specific title gate differs from another provider:** Provider normalizers pass explicit policy to common title helpers. The refactor does not globalize AI-trainer exclusion or AI signal filtering in a way that changes current provider behavior.

7. **Country inference returns multiple countries:** Builder preserves the order provided by the provider-specific country inference logic and uses the first code/name as `country_code` and `country`.

8. **Provider emits optional fields with `None`:** Provider passes those fields through `extra_fields` where current output includes them. The builder must not drop them.

9. **Serper discovery still needs search location helpers:** `search_locations.py` keeps location depth and country/city expansion. Removing LinkedIn query building must not break ATS discovery commands.

10. **Existing downstream enrichment/extraction sees no LinkedIn candidates:** This is intended. Downstream commands continue to consume `job_candidates_YYYY-MM-DD.jsonl`, which will be produced from ATS raw files only.

---

## 10. Implementation Plan

This refactor can land as one larger PR if the full test suite stays green, but the phases below are also valid PR boundaries if review risk grows.

### Mergeable Task DAG

| Task | Name | Scope | Depends On | Verification |
|------|------|-------|------------|--------------|
| T1 | Add common normalization foundation | Add `normalizers/common/*`, `build_ats_candidate(...)`, common helper tests, and migrate Workable duplicate helper usage where it is low-risk. | None | `uv run pytest tests/test_normalizer_common.py tests/test_workable.py` |
| T2 | Split ATS providers and add registry | Move all ATS provider normalization into `normalizers/ats/<provider>/normalizer.py`, add `normalizers/ats/registry.py`, and update provider tests to call the registry or provider modules directly. | T1 | Provider tests for Ashby, Greenhouse, Lever, Personio, Recruitee, SmartRecruiters, Teamtailor, and Workable. |
| T3 | Move processing and delete normalize module | Add `processing.py`, move `ProcessingResult`, `build_job_candidates(...)`, and `process_collection(...)`, make processing ATS-only, update imports, and delete `normalize.py`. | T2 | `uv run pytest tests/test_processing_exports.py` plus provider tests. |
| T4 | Remove legacy LinkedIn search surfaces | Add `search_locations.py`, delete `query_builder.py`, remove CLI `collect` and `run`, remove raw search storage helpers, simplify `sources/serper_google.py`, and remove `SourceMode.LINKEDIN_SAFE_SEARCH`. | T3 | `uv run pytest tests/test_serper_google.py tests/test_storage_json.py tests/test_search_locations.py tests/test_cli.py` |
| T5 | Final acceptance and documentation | Implement or unskip the Phase 3 acceptance tests, update README command documentation, run removed-symbol searches, and run the full test suite. | T4 | `uv run pytest` and symbol search for removed legacy names. |

Dependency graph:

```text
T1 -> T2 -> T3 -> T4 -> T5
```

### Phase 1: Extract Reusable Non-Provider Foundations

1. Add `search_locations.py` with `LocationDepth`, `country_search_location(...)`, and `iter_search_locations(...)`.
2. Update ATS discovery and provider source modules to import `LocationDepth` from `search_locations.py`.
3. Reduce `sources/serper_google.py` to generic Serper client behavior.
4. Remove LinkedIn-only query builder functions and raw search collection helpers.
5. Remove `SourceMode.LINKEDIN_SAFE_SEARCH` from `models.py`.

### Phase 2: Add Common Normalization Helpers

1. Add `normalizers/common/text.py` and migrate duplicated clean/first/list helpers.
2. Add `normalizers/common/company.py` and migrate company cleanup plus slug-to-name conversion.
3. Add `normalizers/common/roles.py` and migrate `ats_role_search_term` and provider-configurable title gates.
4. Add `normalizers/common/countries.py` and migrate shared country-code normalization helpers.
5. Add `normalizers/common/xml.py` and `normalizers/common/html.py`.
6. Add `normalizers/common/raw.py` for raw ATS wrapper extraction.

### Phase 3: Add Shared Candidate Builder

1. Add `normalizers/common/candidate.py` with `build_ats_candidate(...)`.
2. Unit-test base fields, exact optional field preservation, and duplicate `extra_fields` rejection.
3. Migrate one simple provider, preferably Greenhouse, to validate the builder shape.
4. Confirm Greenhouse output remains unchanged.

### Phase 4: Split ATS Providers Into Folders

Move providers in this order to reduce risk:

| Order | Provider | Reason |
|-------|----------|--------|
| 1 | Workable | Already partially split; validates common helper de-duplication. |
| 2 | Greenhouse | Simple JSON response shape. |
| 3 | Lever | Simple JSON list response shape. |
| 4 | SmartRecruiters | JSON pages and country code handling. |
| 5 | Personio | XML helper reuse. |
| 6 | Teamtailor | XML plus HTML/date helper reuse. |
| 7 | Recruitee | Complex listing/detail merge and multi-location inference. |
| 8 | Ashby | Teams, details, secondary locations, and empty-platform fallback. |

After each provider move, run its provider test file and inspect output assertions.

### Phase 5: Add Registry and Processing Module

1. Add `normalizers/ats/registry.py`.
2. Move `ProcessingResult`, `build_job_candidates(...)`, and `process_collection(...)` into `processing.py`.
3. Make processing ATS-only.
4. Update CLI `process` and all tests to import from `processing.py` and `normalizers.ats.registry`.

### Phase 6: Remove Legacy Surfaces

1. Delete `normalize.py`.
2. Delete `query_builder.py` after all imports are migrated.
3. Remove CLI `collect` and `run` commands.
4. Remove raw search storage helpers.
5. Remove or rewrite LinkedIn-specific tests.
6. Update README and command documentation if they mention `collect`, `run`, LinkedIn-safe search, or raw search processing.

### Phase 7: Full Verification

1. Run provider tests.
2. Run processing/export tests.
3. Run Serper and ATS discovery tests.
4. Run full `uv run pytest`.
5. Manually inspect `src/ai_hiring_radar/normalize.py` and `src/ai_hiring_radar/query_builder.py` are deleted.
6. Search for `LINKEDIN_SAFE_SEARCH`, `linkedin_safe_search`, `collect_searches`, `raw_search_dir`, and `write_raw_search_response`; no production references should remain.

---

## 11. User Stories / Journeys

**US-1:** As an operator, I run `process --date YYYY-MM-DD` after collecting ATS boards, so that the system writes normalized job candidates and company records from raw ATS files only.

**Acceptance test:** `tests/test_normalization_refactor_acceptance.py::test_process_normalizes_ats_only_candidates`

**Status:** stub

---

**US-2:** As a developer changing a provider normalizer, I can edit one provider folder without touching unrelated provider normalization code.

**Acceptance test:** `tests/test_normalization_refactor_acceptance.py::test_provider_normalizers_are_isolated_by_provider_folder`

**Status:** stub

---

**US-3:** As a developer adding provider-specific fields, I get a test failure if I accidentally override a shared candidate base field through `extra_fields`.

**Acceptance test:** `tests/test_normalization_refactor_acceptance.py::test_candidate_builder_rejects_base_field_conflicts`

**Status:** new test planned

---

**US-4:** As an operator, I do not see legacy LinkedIn `collect` or `run` commands, because the pipeline is ATS-only.

**Acceptance test:** `tests/test_normalization_refactor_acceptance.py::test_legacy_linkedin_cli_commands_are_removed`

**Status:** stub

---

**US-5:** As an operator processing old Ashby raw files without explicit `platform`, I still get Ashby candidates through the existing fallback behavior.

**Acceptance test:** `tests/test_normalization_refactor_acceptance.py::test_missing_platform_raw_file_falls_back_to_ashby`

**Status:** new test planned

---

**US-6:** As an operator, I can still run `discover-*` and `collect-*` ATS commands that use Serper for board discovery.

**Acceptance test:** `tests/test_normalization_refactor_acceptance.py::test_ats_discovery_commands_still_use_serper_client`

**Status:** stub

---

## 12. Decisions Made

1. **Normalize ATS only:** Processing will no longer normalize raw Serper/LinkedIn search files. The old LinkedIn candidate path is intentionally removed.

2. **Delete `normalize.py`:** No compatibility facade is retained. Callers are migrated to `processing.py` or provider/registry modules.

3. **Move orchestration to `processing.py`:** Top-level process orchestration is separate from provider normalization internals.

4. **Use provider folders:** Each ATS provider gets `normalizers/ats/<provider>/normalizer.py` instead of a flat provider file. This satisfies the maintainability goal and leaves room for provider-local helper files later.

5. **Use function-based provider contracts:** Provider normalizers expose `normalize_response(...)` rather than classes. This is minimal and matches the current functional style.

6. **Use explicit registry dispatch:** `normalizers/ats/registry.py` maps platform names to provider functions. Dynamic discovery is rejected because it adds unnecessary import magic.

7. **Introduce a shared ATS candidate builder:** Repeated base candidate dict assembly is centralized to reduce duplication across providers.

8. **Reject `extra_fields` conflicts:** Provider-specific fields cannot silently override base candidate fields. A conflict raises `ValueError`.

9. **Preserve exact ATS output:** The refactor must not change ATS candidate output, IDs, field ordering expectations in tests, country inference ordering, or title filtering behavior.

10. **Keep Serper for ATS discovery:** `SourceName.SERPER_GOOGLE` and `SerperGoogleClient` remain because ATS discovery still depends on Serper search.

11. **Remove LinkedIn safe search mode:** `SourceMode.LINKEDIN_SAFE_SEARCH` is removed because no remaining production flow should emit it.

12. **Remove `collect` and `run`:** These commands are tied to the legacy LinkedIn path and are not replaced in this feature.

13. **Move location helpers out of `query_builder.py`:** `LocationDepth` and search location expansion remain, but LinkedIn query generation is deleted.

14. **Do not reorganize source collection modules:** `sources/<provider>.py` files stay in place. This feature only refactors normalization and removes legacy LinkedIn search processing.

---

## 13. Upgrade Paths

### 13.1 Full Provider Integration Packages

Later, `sources/<provider>.py` and `normalizers/ats/<provider>/` could be merged into `integrations/<provider>/` packages. That is intentionally deferred because it would mix collection refactoring with normalization behavior preservation.

### 13.2 Pydantic Candidate Model

A future feature could define a Pydantic model for normalized job candidates. This is deferred because the current records are flexible JSON dictionaries and exact output preservation is the priority.

### 13.3 Provider Scaffold Generator

After the folder structure stabilizes, a small template or checklist could help add future ATS normalizers. This is deferred until at least one new provider is added after the refactor.

### 13.4 Process-And-Export Command

The removed `run` command could be replaced later by an ATS-safe `process-and-export` command if operators need it. This feature removes `run` outright and does not introduce a replacement.

### 13.5 More Aggressive Provider Internal Splits

Complex providers such as Ashby and Recruitee may later split their provider folder into `parser.py`, `locations.py`, and `records.py`. The initial design uses one `normalizer.py` per provider to minimize unnecessary structure.

---

## 14. Files to Modify / Create

### 14.1 New Files

| File | Purpose |
|------|---------|
| `src/ai_hiring_radar/processing.py` | ATS-only processing orchestration and `ProcessingResult`. |
| `src/ai_hiring_radar/search_locations.py` | Location depth and country/city search-location helpers moved out of `query_builder.py`. |
| `src/ai_hiring_radar/normalizers/common/__init__.py` | Common normalizer package marker. |
| `src/ai_hiring_radar/normalizers/common/candidate.py` | Shared ATS candidate builder. |
| `src/ai_hiring_radar/normalizers/common/company.py` | Shared company cleanup and slug-to-name helpers. |
| `src/ai_hiring_radar/normalizers/common/countries.py` | Shared country-code and country inference helper glue. |
| `src/ai_hiring_radar/normalizers/common/html.py` | Shared HTML-to-text helper. |
| `src/ai_hiring_radar/normalizers/common/raw.py` | Raw ATS payload and file iteration helpers. |
| `src/ai_hiring_radar/normalizers/common/roles.py` | Shared role search term and title gate helpers. |
| `src/ai_hiring_radar/normalizers/common/text.py` | Shared text/list helpers. |
| `src/ai_hiring_radar/normalizers/common/xml.py` | Shared XML helpers. |
| `src/ai_hiring_radar/normalizers/ats/__init__.py` | ATS normalizer package marker. |
| `src/ai_hiring_radar/normalizers/ats/registry.py` | ATS platform dispatch and raw ATS file normalization. |
| `src/ai_hiring_radar/normalizers/ats/ashby/__init__.py` | Ashby normalizer package marker. |
| `src/ai_hiring_radar/normalizers/ats/ashby/normalizer.py` | Ashby provider normalization. |
| `src/ai_hiring_radar/normalizers/ats/greenhouse/__init__.py` | Greenhouse normalizer package marker. |
| `src/ai_hiring_radar/normalizers/ats/greenhouse/normalizer.py` | Greenhouse provider normalization. |
| `src/ai_hiring_radar/normalizers/ats/lever/__init__.py` | Lever normalizer package marker. |
| `src/ai_hiring_radar/normalizers/ats/lever/normalizer.py` | Lever provider normalization. |
| `src/ai_hiring_radar/normalizers/ats/personio/__init__.py` | Personio normalizer package marker. |
| `src/ai_hiring_radar/normalizers/ats/personio/normalizer.py` | Personio provider normalization. |
| `src/ai_hiring_radar/normalizers/ats/recruitee/__init__.py` | Recruitee normalizer package marker. |
| `src/ai_hiring_radar/normalizers/ats/recruitee/normalizer.py` | Recruitee provider normalization. |
| `src/ai_hiring_radar/normalizers/ats/smartrecruiters/__init__.py` | SmartRecruiters normalizer package marker. |
| `src/ai_hiring_radar/normalizers/ats/smartrecruiters/normalizer.py` | SmartRecruiters provider normalization. |
| `src/ai_hiring_radar/normalizers/ats/teamtailor/__init__.py` | Teamtailor normalizer package marker. |
| `src/ai_hiring_radar/normalizers/ats/teamtailor/normalizer.py` | Teamtailor provider normalization. |
| `src/ai_hiring_radar/normalizers/ats/workable/__init__.py` | Workable normalizer package marker. |
| `src/ai_hiring_radar/normalizers/ats/workable/normalizer.py` | Workable provider normalization, replacing the current flat file. |
| `tests/test_ats_normalizer_registry.py` | Registry dispatch and fallback tests. |
| `tests/test_normalizer_common.py` | Shared builder/helper tests. |
| `tests/test_search_locations.py` | Replacement tests for kept location helper behavior. |

### 14.2 Modified Files

| File | Change |
|------|--------|
| `src/ai_hiring_radar/cli.py` | Import `process_collection` from `processing.py`; remove `collect` and `run`; remove LinkedIn query imports; keep provider discovery/collection commands. |
| `src/ai_hiring_radar/models.py` | Remove `SourceMode.LINKEDIN_SAFE_SEARCH`; keep `SourceName.SERPER_GOOGLE`. |
| `src/ai_hiring_radar/storage_json.py` | Remove raw search storage helpers; keep raw ATS, ATS discovery, processed, and export helpers. |
| `src/ai_hiring_radar/sources/serper_google.py` | Keep generic client; remove LinkedIn raw collection helpers. |
| `src/ai_hiring_radar/sources/ats_discovery.py` | Import location helpers from `search_locations.py`. |
| `src/ai_hiring_radar/sources/ashby.py` | Import `LocationDepth` from `search_locations.py`. |
| `src/ai_hiring_radar/sources/greenhouse.py` | Import `LocationDepth` from `search_locations.py`. |
| `src/ai_hiring_radar/sources/lever.py` | Import `LocationDepth` from `search_locations.py`. |
| `src/ai_hiring_radar/sources/personio.py` | Import `LocationDepth` from `search_locations.py`. |
| `src/ai_hiring_radar/sources/recruitee.py` | Import `LocationDepth` from `search_locations.py`. |
| `src/ai_hiring_radar/sources/smartrecruiters.py` | Import `LocationDepth` from `search_locations.py`. |
| `src/ai_hiring_radar/sources/teamtailor.py` | Import `LocationDepth` from `search_locations.py`. |
| `src/ai_hiring_radar/sources/workable.py` | Import `LocationDepth` from `search_locations.py`. |
| `src/ai_hiring_radar/normalizers/__init__.py` | Update package exports if useful. |
| `README.md` | Remove or update references to `collect`, `run`, LinkedIn-safe search processing, and raw search files. |

### 14.3 Deleted Files

| File | Reason |
|------|--------|
| `src/ai_hiring_radar/normalize.py` | Replaced by `processing.py`, registry, provider normalizers, and common helpers. |
| `src/ai_hiring_radar/query_builder.py` | LinkedIn query builder removed; location helpers moved to `search_locations.py`. |
| `src/ai_hiring_radar/normalizers/workable.py` | Replaced by `normalizers/ats/workable/normalizer.py`. |

### 14.4 Test Files

| File | Change |
|------|--------|
| `tests/test_ashby.py` | Update normalization imports; preserve candidate expectations. |
| `tests/test_greenhouse.py` | Update normalization imports; preserve candidate expectations. |
| `tests/test_lever.py` | Update normalization imports; preserve candidate expectations. |
| `tests/test_personio.py` | Update normalization imports; preserve candidate expectations. |
| `tests/test_recruitee.py` | Update normalization imports; preserve candidate expectations. |
| `tests/test_smartrecruiters.py` | Update normalization imports; preserve candidate expectations. |
| `tests/test_teamtailor.py` | Update normalization imports; preserve candidate expectations. |
| `tests/test_workable.py` | Update normalization imports; preserve candidate expectations. |
| `tests/test_processing_exports.py` | Replace LinkedIn raw search fixture with ATS raw fixture. |
| `tests/test_serper_google.py` | Remove raw LinkedIn collection tests; keep generic client tests. |
| `tests/test_storage_json.py` | Remove raw search helper tests; keep raw ATS and processed storage tests. |
| `tests/test_query_builder.py` | Delete or replace with `tests/test_search_locations.py`. |
| `tests/test_normalize.py` | Delete or replace with registry/common helper tests. |
| `tests/test_job_description_extraction.py` | Update candidate fixtures away from legacy LinkedIn source where appropriate. |
| `tests/test_aggregate.py` | Consider updating example candidate source URLs to ATS URLs for consistency, unless tests intentionally use arbitrary URLs. |
| `tests/test_dedupe.py` | Consider updating example candidate source URLs to ATS URLs for consistency, unless tests intentionally use arbitrary URLs. |

---

## 15. Changelog

2026-07-10 - Jakob - Accepted the design document for implementation planning.
2026-07-10 - OpenCode - Added skipped acceptance test stubs for US-1 through US-6.
2026-07-10 - OpenCode - Added Phase 4 mergeable task DAG.
