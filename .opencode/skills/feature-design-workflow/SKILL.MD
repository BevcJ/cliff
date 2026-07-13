---
name: feature-design-workflow
description: >
  Standard operating procedure for taking a new feature from raw idea through
  design document, task breakdown, and Notion tracking. Used when the user
  asks for a non-trivial or cross-cutting feature.
---

# Feature Design Workflow

## Trigger

Use this workflow when the user asks for complex features spanning multiple modules. Do **not** use for one-line bug fixes, typo corrections, or pure questions.

---

## Phase 1 — Requirements & Options

**Goal:** Understand the problem, surface trade-offs, challenge ideas in a constructive way and agree on choices.

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
---

## Phase 3 — Write acceptance tests (Optional)

**Goal:** Codify the user-stories/requirements as acceptance test stubs. The goal is to have a bill-of-work in terms of needed verification and follow test-driven design practices before implementation even starts. Not all projects/repos implement acceptance tests, so if you can't clearly determine if it does, ask the user if they want it implemented.

### Principles

1. **Follow existing practices.** Don't reinvent the wheel. Scan the codebase for existing practices and follow them to the letter unless you absolutely can't.

2. **One acceptance test per user-story.**

3. **Use acceptance test docstrings to describe scenario** so it is immidiately clear to the user what is being tested and the test is easier to maintain if for some reason the test needs to evolve.

4. **Document links between user-stories and tests.** In the docstring of each test, link to the design document and user story it is testing in the following format `(XY-some-feature, US-N)` for tracability purposes.

5. **Skip the stub test** to avoid blocking the PR cycle.
---

## Phase 4 — Task Breakdown

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

## Phase 5 — Notion Tracking

**Goal:** Create an Epic in the Epics database, paste the design doc into its
body, and create linked Tasks with dependencies. Reference the `notion-mcp` skill how to do it efficiently.

### Step 1: Find or create the Epic
- Search Notion for an existing epic on this topic, or create one in the
  `Epics` database.
- Set Status = `In progress`, Owner = the user.

### Step 2: Copy the design doc to the epic body
Use `update_page(..., command: "replace_content", new_str: DOC_MARKDOWN)`.

### Step 3: Create Tasks in the `⚙️ Tasks` database
For each task from Phase 3:
- **Task name:** Short, imperative (e.g. "Add retry cap to FailedTasksDB")
- **Assignee:** JSON array of user IDs: `"[{\"id\": \"USER_UUID\"}]"`
- **Effort:** `XS (≤ 2 hours)` for tasks ≤2h, scale up as needed
- **Status:** `to-do`
- **Sprint:** Current sprint URL.
- **⛰️ Epic:** Link to the epic page URL
- **Blocked by:** Use full page URLs in a JSON array. Set after all tasks are
  created so the target IDs exist.

Many of the linked entities can be found using the knowledge in the `notion-mcp` skill.

### Property formats
```json
{
  "Task name": "Add retry cap",
  "Status": "to-do",
  "Effort": "XS (≤ 2 hours)",
  "Assignee": "[{\"id\": \"281d...\"}]",
  "Sprint": "[\"https://app.notion.com/p/SPRINT_ID\"]",
  "⛰️ Epic": "[\"https://app.notion.com/p/EPIC_ID\"]",
  "Blocked by": "[\"https://app.notion.com/p/TASK_A_ID\"]"
}
```

**CRITICAL:** Relations need full Notion page URLs (`https://app.notion.com/p/...`).
Bare UUIDs trigger a validation error.

### Step 5: Confirm with the user
Show the task list, dependency graph, and Notion links. Ask:
"Ready to execute? If so, I'll start with Task 1 (Foundation)."

---

## Summary Checklist

- [ ] Phase 1: Audited codebase, asked clarifying questions, got user lock-in
- [ ] Phase 2: Wrote design doc following `00-scaffold/DOC.md`
- [ ] Phase 3: Skipped acceptance tests written
- [ ] Phase 4: Split into ≤5 small, module-bounded tasks with unidirectional deps. 
- [ ] Phase 5: Epic created, Tasks in Notion