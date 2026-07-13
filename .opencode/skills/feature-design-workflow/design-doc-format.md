**IMPORTANT**: This is a generic design document template. Before using it, check if the repository has defined its own scaffolding to stay in sync with the repos conventions.

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

## 3. Impacted Module

This section is just a placeholder. For each impacted top-level module or same-workspace library (like when using uv workspaces) describe what the core needed changes for it are and what it means for modules that connect to it.

Some examples:
- **Database layer** list new/removed/modified tables, new CRUD helpers, migrations that are needed,
- **Infrastructure** lists new dependencies, new containers, etc.,
- **API Layer** lists new endpoints, new auth modes, etc.

---

## 4. Edge Cases & Behaviour

> Number every edge case. For each, describe the trigger condition, the expected system behaviour, and (if relevant) the user-visible effect. Do not leave vague statements like "handled gracefully" — be specific about what happens.
>
> Aim for at least 3–5 edge cases. Common categories to consider:
> - Partial failure (one sub-step fails; what happens to the others?)
> - Concurrent writes / race conditions
> - Legacy data (rows created before this feature was deployed)
> - Empty/null inputs at each boundary
> - Re-generation or re-processing of an entity that already has data

1. **[Edge case title]:** Describe the trigger. Describe the expected behaviour. Describe any user-visible effect.

2. **[Another edge case]:** Describe the trigger. Describe the expected behaviour.

3. **[Another edge case]:** Describe the trigger. Describe the expected behaviour.

---

## 5. User Stories / Journeys

> **This section is required in every design document.** Its purpose is to enumerate the user-facing and system-level behaviours the feature introduces, in story format.
>
> **Format for each story:**
>
> ```
> **US-N:** As a [role], I [action], so that [outcome].
> **Acceptance test:** `tests/foo_acceptance_test.py::test_name`
> ```
>
> **What stories to include:**
> - **Happy path** — the feature works end-to-end as designed.
> - **Editing / update flows** — if the feature allows mutation, cover the update case.
> - **Error conditions** — what happens when inputs are invalid or a dependency fails.
> - **System / automated behaviours** — e.g. generation sub-steps triggered without user action.
>
> If the project implements acceptance tests, either on top-level or per-module, each user-story should be tracable to a named acceptance test function.
>
> **Test stub convention:** Until a story is implemented, its acceptance test must use:
> ```python
> @pytest.mark.skip(reason="TDD stub - not yet implemented")
> def test_name():
>     """(design-doc-name, US-N)
>
>     Description of the scenario and the outcomes.
>     """
>     raise NotImplementedError("TDD stub - ...")
> ```
>
> **Goal:** By the time implementation is complete, every story below has a corresponding acceptance test that passes.

> Add more stories as needed. Cover all meaningful user-facing and system behaviours. When the feature involves multiple roles (e.g. assignee vs. admin), write separate stories for each. System-triggered behaviours (automated generation steps, cascading updates) deserve their own stories even if no human initiates them directly.

---

**US-1:** As a registered user, I submit a valid request, so that the system creates the expected resource and returns a success response.
**Acceptance test:** `tests/example_acceptance_test.py::test_user_can_create_resource`

---

**US-2:** As a registered user, I submit a request with an invalid payload, so that the system returns a 422 error and does not create a partial resource.
**Acceptance test:** `tests/example_acceptance_test.py::test_invalid_payload_returns_422`

---

**US-3:** As the system, when a background task completes processing, the resource status transitions to `GENERATED` and the result is accessible via the read endpoint.
**Acceptance test:** `tests/example_acceptance_test.py::test_background_task_completes_and_status_transitions`

---

## 6. Decisions Made

> Number every decision. For each, state what was decided and why — include the alternatives considered and why they were rejected. Decisions should be permanent and reviewable; this section is the record of design reasoning.
>
> Common decision categories: data model choices (column vs. table, nullable vs. not), API routing choices, default values, scope inclusions/exclusions, migration strategy.
>
> See `03-dual-decision-mnenje` §14 for an example of a well-populated decisions list (12 entries).

1. **[Decision title]:** State what was decided. Explain the rationale and what alternatives were considered and rejected.

2. **[Another decision]:** State what was decided and why.

---

## 7. Upgrade Paths

> List future enhancements that are intentionally out of scope for this implementation. For each, explain what it would involve and why it is deferred. This prevents scope creep during implementation while preserving the ideas for later.
>
> Every "we could also..." or "in the future..." thought that came up during design belongs here, not in the main body.
>
> See `03-dual-decision-mnenje` §16 and `04-instituti-vprasanje` §12 for worked examples.

### 7.1 [Enhancement Title]

Describe what this enhancement would add and the rough implementation approach. Note any dependencies on the current feature being stable first.

### 7.2 [Another Enhancement]

Describe the enhancement and why it is deferred.

---

## 8. Changelog

> Add a chronological list of significant changes to this document after the initial Draft is written. The initial creation does not need an entry. Format: `YYYY-MM-DD — [author] — [brief description of what changed]`.
>
> Example entry: `2026-03-05 — Matic Pečovnik — Added Context Search sub-section (§9.5) after review feedback.`
