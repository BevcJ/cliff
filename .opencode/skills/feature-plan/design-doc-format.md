# Design Document: [Feature Title]

> **This document is the canonical scaffold template.** Copy it when starting a new design document and fill in every section. Delete guidance blockquotes once a section is complete. The `Status` field below must be changed from `Template` to `Draft` (and later to `Accepted` or `Superseded`) when you begin working in the document for real.
>
> See `architecture-design-documents/03-dual-decision-mnenje/DOC.md` and `architecture-design-documents/04-instituti-vprasanje/DOC.md` for fully completed examples.

> **Feature-Specific Sections:** This scaffold contains a fixed skeleton of universal sections (§1–§8 and the tail sections). Real features often require additional domain-specific sections — e.g. "Batch Import", "Institut Pool Construction", "Implementation Plan", "Context Search Integration". Insert those as numbered sections **between §3 (Database Design) and §9 (Edge Cases)**, then renumber Edge Cases, User Stories, Decisions, Upgrade Paths, Implementation Plan, and Files accordingly.
>
> Example: a feature with Generation Layer (§4), CRUD (§5), Celery (§6), API (§7), Frontend (§8), and a "Batch Import" sub-feature (§9) would push Edge Cases to §10, Implementation Plan to §11, User Stories to §12, and so on. Keep all internal `§N` cross-references consistent after any renumbering.

| Field | Value |
|-------|-------|
| **Status** | Template |
| **Author** | — |
| **Created** | YYYY-MM-DD |
| **Last Updated** | YYYY-MM-DD |
| **Epic** | — |
| **Related Issues** | — |

---

## 1. Overview

### 1.1 Problem Statement

> Describe the current behaviour and what is wrong or missing. Be concrete: name the specific code paths, columns, endpoints, or UI elements that are broken or absent. Explain the practical impact on users or the system. Aim for 2–4 paragraphs.
>
> Good example: see §1.1 in `03-dual-decision-mnenje` — it names the exact generation step, the two practical problems, and why they matter.

### 1.2 Proposed Solution

> Summarise the proposed change in plain language. Answer: what will exist after this feature lands that does not exist now? Name the key new entities (tables, columns, endpoints, task steps) without deep detail — those go in later sections.
>
> If the feature has multiple interconnected parts, enumerate them as a numbered list here. See §1.2 in `04-instituti-vprasanje` for a five-part summary as a worked example.

### 1.3 Terminology

> Define every domain-specific or project-specific term used in this document. Include both new terms introduced by this feature and any existing terms that might be ambiguous in the new context. Use the table below. Add rows as needed.

| Term | Definition |
|------|------------|
| **ExampleTerm** | Replace with your terms. |
| **AnotherTerm** | Every term used in this document that is not obvious to a new reader should appear here. |

---

## 2. Architecture

> Describe the system flow — the sequence of function calls, task steps, and data transformations involved. Use ASCII diagrams where possible. Show both the **current** flow (even if the answer is "this does not exist yet") and the **proposed** flow. This section should make the before/after change immediately visible to a reviewer.
>
> **Audit requirement:** Before drawing these diagrams, read the relevant code paths — CRUD files, Celery task files, context layer, server handlers — to ensure the diagrams reflect reality, not assumptions.

### 2.1 Current Flow

> Show what happens today. If the feature is entirely new (greenfield), say so explicitly and describe the relevant adjacent flow instead (e.g. the pipeline that will be extended).

```
ComponentA
  → step_one(arg)
  → step_two(arg)
      # describes current behaviour
```

### 2.2 Proposed Flow

> Show what happens after this feature lands. Highlight the new/changed lines with `# NEW` or `# CHANGED` comments inline, as done in `03-dual-decision-mnenje` §2.2.

```
ComponentA
  → step_one(arg)              # unchanged
  → new_step(arg)              # NEW — describe what this does
  → step_two(arg, new_param)   # CHANGED — describe the change
```

> Key differences: list 3–5 bullet points summarising the most important behavioural changes visible in the diagram above.

---

## 3. Database Design

> This section is required even for features with no schema changes — write "No schema changes" under §3.1 in that case and briefly explain why. For features that do change the schema, follow the patterns established in `03-dual-decision-mnenje` §3 and `04-instituti-vprasanje` §3.

### 3.1 New / Modified Tables

> For each new or modified SQLAlchemy model, show the relevant class definition with the new/changed columns annotated. Include the `doc=` parameter on each column. Explain the rationale for non-obvious design choices (nullable vs. non-nullable, column vs. relationship, default values, etc.) in prose below the code block.
>
> Cross-layer enums (used by server, worker, libs) must be defined in `libs/commons/aibackend/commons/data_models.py` as `StrEnum`. DB-layer-only enums belong in `libs/database/aibackend/database/data_models.py`.

```python
# libs/database/aibackend/database/data_models.py

@final
class ExampleDB(Base):
    __tablename__ = "example"

    # ... existing columns ...

    new_column: Mapped[ExampleType] = mapped_column(
        Enum(ExampleType, name="example_type"),
        nullable=False,
        doc="Describe what this column stores and why.",
    )
```

### 3.2 Schema Summary

> Fill in the table for every table touched by this feature, including tables with no change (explain why in the Details column). This gives reviewers a single at-a-glance view of the DB impact.

| Table | Change | Details |
|-------|--------|---------|
| `example_table` | Add column | `new_column: ExampleType NOT NULL` |
| `other_table` | No change | Already scoped correctly; no migration needed. |

### 3.3 Migration Strategy

> Describe how the schema change reaches production. Choose one approach and explain the rationale:
>
> - **Alembic migration** (preferred for new tables or complex changes): Provide the migration filename pattern and a summary of DDL steps. Describe backfill strategy for existing rows if applicable.
> - **Manual DDL** (simple column additions, no production data): Show the exact SQL statements a DBA will run. Explain why no Alembic file is needed.
>
> Always state whether a backfill of existing rows is required and, if not, what the effect of the default value is on legacy data.

---

## 4. Generation Layer

> **Omit this section (write "N/A — no generation changes") if this feature does not touch LLM prompt or agent code.**
>
> If applicable, describe:
> - Which prompt templates change and how (show the before/after diff of the relevant sections).
> - Which generation function signatures change (show the new signature).
> - Any new agents, output validators, or `ModelRetry` logic introduced.
> - How `decision_type` or other new parameters are resolved before they reach the prompt.
>
> Follow the pattern in `03-dual-decision-mnenje` §4 for prompt changes, or `04-instituti-vprasanje` §9 for a new generation sub-step.

---

## 5. CRUD Layer

> Describe all new and modified CRUD functions. CRUD is listed before the API and Celery layers because both depend on it — document the data access interface before documenting its consumers.
>
> Cover all functions that return Pydantic models (lifecycle models, response models) as well as helper functions used by the API or Celery layers. If a function uses the `sqlalchemy_to_lifecycle` / `sqlalchemy_to_dict` pattern with `**kwargs` to inject relationship-loaded fields (e.g. `instituti` loaded via a JOIN rather than a column), document that pattern here so implementors know to follow it. New functions belong in §5.1; modified functions in §5.2.

### 5.1 New Functions

> One row per new function. Include the exact location (file path, no package prefix needed) and a one-line description. Functions that assemble lifecycle models from ORM objects should note whether they use `sqlalchemy_to_lifecycle` with `**kwargs`.

| Function | Location | Description |
|----------|----------|-------------|
| `create_example(...)` | `database/dor/example.py` | Creates a new `ExampleDB` row and returns the lifecycle model. |
| `get_example(...)` | `database/dor/example.py` | Fetches the current version of an example row by ID. |

### 5.2 Modified Functions

> One row per modified function. Describe only what changes — not the full function spec.

| Function | File | Change |
|----------|------|--------|
| `existing_function(...)` | `database/dor/existing.py` | Gains a required `new_param: ExampleType` parameter. |

---

## 6. Celery Task Layer

> **Omit this section (write "N/A — no Celery task changes") if this feature does not touch task code.**
>
> Describe each modified or new Celery task function. Show the relevant before/after code where the change is non-trivial. Note any changes to return types (e.g. from `UUID` to `list[UUID]`) and explain the downstream impact. If orchestration changes (e.g. flattening a `list[list[UUID]]`), show the updated orchestrator code.
>
> Follow the pattern in `03-dual-decision-mnenje` §5 for task-layer changes.

---

## 7. API Layer

> **Omit this section (write "N/A — no API changes") if this feature does not touch HTTP endpoints.**
>
> Describe every new and modified endpoint. For each, provide:
> - HTTP method + path
> - Request body (if any), as a code block or prose description
> - Response shape and status codes
> - Authorization requirements
> - Rationale for non-obvious design choices (e.g. why route through `mnenje_id` rather than `vprasanje_id`)

### 7.1 New Endpoints

> For each new endpoint:

```
POST /example/{resource_id}/action

Request body:
  { "field": "value" }

Response:
  200 OK — { "result": ... }
  404 Not Found — if resource does not exist
```

### 7.2 Modified Endpoints

> List all modified endpoints in a table. Focus on what changes, not on the full spec of the unchanged parts.

| Endpoint | Change |
|----------|--------|
| `GET /example/{id}` | Response gains `new_field: ExampleType` |
| `POST /example/{id}/action` | Request body gains optional `flag: bool` |

### 7.3 Request / Response Shapes

> Show the relevant Pydantic model definitions for new or significantly changed request/response models. Use `StrictBaseModel` as the base class per project convention.

```python
class ExampleResponse(StrictBaseModel):
    id: uuid.UUID
    new_field: ExampleType
    # ... other fields ...
```

---

## 8. Frontend

> **Omit this section (write "N/A — no frontend changes") if this feature does not touch the frontend.**
>
> Describe:
> - Type changes in `apps/frontend/src/types/api.ts`
> - New or modified service calls in `apps/frontend/src/services/`
> - Component changes (which views/components, what UI behaviour changes)
>
> Include a Files Changed table at the end of this section (see `03-dual-decision-mnenje` §11.5 for an example).

---

## 9. Edge Cases & Behaviour

> Number every edge case. For each, describe the trigger condition, the expected system behaviour, and (if relevant) the user-visible effect. Do not leave vague statements like "handled gracefully" — be specific about what happens.
>
> Aim for at least 3–5 edge cases. Common categories to consider:
> - Partial failure (one sub-step fails; what happens to the others?)
> - Concurrent writes / race conditions
> - Legacy data (rows created before this feature was deployed)
> - Empty/null inputs at each boundary
> - Re-generation or re-processing of an entity that already has data
>
> See `03-dual-decision-mnenje` §13 and `04-instituti-vprasanje` §10 for worked examples.

1. **[Edge case title]:** Describe the trigger. Describe the expected behaviour. Describe any user-visible effect.

2. **[Another edge case]:** Describe the trigger. Describe the expected behaviour.

3. **[Another edge case]:** Describe the trigger. Describe the expected behaviour.

---

## 10. Implementation Plan

> Include this section for features that span multiple sequential phases or multiple PRs. Omit it (write "N/A — single PR") for small features where all changes land in one commit.
>
> Group steps by phase. Each step should be independently testable and ideally correspond to a single logical commit. Reference the relevant design doc sections so implementors can find the detail for each step.
>
> Example format:
>
> ```
> ### Phase 1: Schema & Data Model
> 1. Add `FooEnum` to `libs/commons/.../data_models.py` (see §3.1)
> 2. Add `FooDB` column to `libs/database/.../data_models.py` (see §3.1)
> 3. Write Alembic migration (see §3.3)
>
> ### Phase 2: CRUD Layer
> 4. Implement `create_foo` and `get_foo` in `database/dor/foo.py` (see §5.1)
> 5. Write unit tests for new CRUD functions
>
> ### Phase 3: API Layer
> 6. Add `FooResponse` model and `POST /foo/{id}/action` endpoint (see §7.1)
> 7. Write acceptance tests for user stories US-1 and US-2 (see §11)
> ```

---

## 11. User Stories / Journeys

> **This section is required in every design document.** Its purpose is to enumerate the user-facing and system-level behaviours the feature introduces, in story format, each traceable to a named acceptance test function in `tests/*_acceptance_test.py`.
>
> **Format for each story:**
>
> ```
> **US-N:** As a [role], I [action], so that [outcome].
> **Acceptance test:** `tests/foo_acceptance_test.py::test_name`
> **Status:** stub / implemented
> ```
>
> **What stories to include:**
> - **Happy path** — the feature works end-to-end as designed.
> - **Editing / update flows** — if the feature allows mutation, cover the update case.
> - **Error conditions** — what happens when inputs are invalid or a dependency fails.
> - **System / automated behaviours** — e.g. generation sub-steps triggered without user action.
>
> **Test stub convention:** Until a story is implemented, its acceptance test must use:
> ```python
> @pytest.mark.skip(reason="TDD stub - not yet implemented")
> def test_name():
>     raise NotImplementedError("TDD stub - ...")
> ```
>
> **Goal:** By the time implementation is complete, every story below has a corresponding acceptance test that passes and the `Status` field is updated to `implemented`.

> Add more stories as needed. Cover all meaningful user-facing and system behaviours. When the feature involves multiple roles (e.g. assignee vs. admin), write separate stories for each. System-triggered behaviours (automated generation steps, cascading updates) deserve their own stories even if no human initiates them directly.

---

**US-1:** As a registered user, I submit a valid request, so that the system creates the expected resource and returns a success response.
**Acceptance test:** `tests/example_acceptance_test.py::test_user_can_create_resource`
**Status:** stub

---

**US-2:** As a registered user, I submit a request with an invalid payload, so that the system returns a 422 error and does not create a partial resource.
**Acceptance test:** `tests/example_acceptance_test.py::test_invalid_payload_returns_422`
**Status:** stub

---

**US-3:** As the system, when a background task completes processing, the resource status transitions to `GENERATED` and the result is accessible via the read endpoint.
**Acceptance test:** `tests/example_acceptance_test.py::test_background_task_completes_and_status_transitions`
**Status:** stub

---

## 12. Decisions Made

> Number every decision. For each, state what was decided and why — include the alternatives considered and why they were rejected. Decisions should be permanent and reviewable; this section is the record of design reasoning.
>
> Common decision categories: data model choices (column vs. table, nullable vs. not), API routing choices, default values, scope inclusions/exclusions, migration strategy.
>
> See `03-dual-decision-mnenje` §14 for an example of a well-populated decisions list (12 entries).

1. **[Decision title]:** State what was decided. Explain the rationale and what alternatives were considered and rejected.

2. **[Another decision]:** State what was decided and why.

---

## 13. Upgrade Paths

> List future enhancements that are intentionally out of scope for this implementation. For each, explain what it would involve and why it is deferred. This prevents scope creep during implementation while preserving the ideas for later.
>
> Every "we could also..." or "in the future..." thought that came up during design belongs here, not in the main body.
>
> See `03-dual-decision-mnenje` §16 and `04-instituti-vprasanje` §12 for worked examples.

### 13.1 [Enhancement Title]

Describe what this enhancement would add and the rough implementation approach. Note any dependencies on the current feature being stable first.

### 13.2 [Another Enhancement]

Describe the enhancement and why it is deferred.

---

## 14. Files to Modify / Create

> This section must be complete before implementation begins. Every file touched by the feature should appear here. Use the three-table structure below. If a category has no entries, write "None."
>
> **New Files** — files that do not exist yet and will be created.
> **Modified Files** — existing files that will be changed.
> **Test Files** — both new and modified test files. Include unit tests, integration tests, and acceptance tests.

### 14.1 New Files

| File | Purpose |
|------|---------|
| `libs/example/aibackend/example/new_module.py` | Describe the purpose of this new file. |

### 14.2 Modified Files

| File | Change |
|------|--------|
| `libs/commons/aibackend/commons/data_models.py` | Add `ExampleEnum` shared enum. |
| `libs/database/aibackend/database/data_models.py` | Add new column to `ExampleDB`. |

### 14.3 Test Files

| File | Change |
|------|--------|
| `libs/example/tests/example_test.py` | New — unit tests for new CRUD functions. |
| `tests/example_acceptance_test.py` | New — acceptance tests for user stories US-1 through US-3. |

---

## 15. Changelog

> Add a chronological list of significant changes to this document after the initial Draft is written. The initial creation does not need an entry. Format: `YYYY-MM-DD — [author] — [brief description of what changed]`.
>
> Example entry: `2026-03-05 — Matic Pečovnik — Added Context Search sub-section (§9.5) after review feedback.`
