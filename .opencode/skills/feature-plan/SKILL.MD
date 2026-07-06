---
name: feature-design-workflow
description: >
  Standard operating procedure for taking a new feature from raw idea through
  design document, task breakdown, and Notion tracking. Used when the user
  asks for a non-trivial or cross-cutting feature.
---

# Feature Design Workflow

## Trigger

Use this workflow when the user asks for complex features spanning multiple modules (DB + API + orchestrator/tasks + frontend)

Do **not** use for one-line bug fixes, typo corrections, or pure questions.

---

## Phase 1 — Requirements & Options

**Goal:** Understand the problem, surface trade-offs, and agree on choices.

1. **Read the scaffold** [here](design-doc-format.md) to remind yourself of the
   required sections.

2. **Audit the codebase.** Before proposing anything, find:
   - `pydantic`, `dataclass`, ... which describes data and interfaces used in the codebase
   - focus on what defines established modules, what are the intended public interfaces, etc.
   - Docker-related files if infra is involved

3. **Present 2–3 concrete alternatives** for every major decision (not vague
   "we could do X or Y"). Use a comparison table:
   - Approach
   - Pros
   - Cons
   - Impact on existing code

4. **Ask focused clarifying questions.** Examples:
   - Retry interval / cap / schedule?
   - How to classify non-retryable vs retryable errors?
   - Which module should own the new logic?

5. **Iterate until the user locks in every choice.** Do not proceed to Phase 2
   with unresolved ambiguities. Make sure all options and branches are exhausted.

---

## Phase 2 — Design Document

**Goal:** Produce a single canonical design doc in
`architecture-design-documents/{NN}-{slug}/DOC.md`.

1. **Pick the next sequential number** (`{NN}`) by listing the existing
   `architecture-design-documents/` directories.

2. **Copy the scaffold** (`00-scaffold/DOC.md`) and fill every section

3. **Ask the user to review** the design doc before implementation begins.
   Do not start coding until the user says the doc looks complete.

---

## Phase 3 — Task Breakdown

**Goal:** Split the design into independently mergeable tasks that can land
in the default branch one at a time without breaking the build.

### Principles

1. **Each task leaves the codebase working.** It may be incomplete (a new
   function that is uncalled, a new column with a default, a skipped test), but
   it compiles and passes tests.

2. **Tasks should not pass between module borders** where possible. Keep a task
   within `libs/database`, `libs/celery_tasks`, `apps/server`, etc. If two modules
   must change in lockstep, combine them into one task and document why.

3. **Tasks are small enough to review efficiently.** A good task is one
   file changed + tests, or one logical concept (e.g. "add migration + update
   model") rather than "implement the entire feature".

4. **Dependencies are unidirectional.** If Task B needs something from Task A,
   Task A must land first. Use a simple DAG, no cycles.

---