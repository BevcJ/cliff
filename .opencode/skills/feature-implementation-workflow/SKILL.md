---
name: feature-implementation-workflow
description: >
  Execution phase of feature delivery. Reads the epic body and task DAG from
  Notion, determines the next unblocked task that is not yet done, implements
  it, runs checks, unskips relevant tests, and marks it complete. Repeats until
  the feature is fully landed.
---

# Feature Implementation Workflow

## Trigger

Use this skill when the user says things like:
- "Go ahead and implement."
- "Start implementing Task 2."
- "Continue from where we left off."
- "Finish the remaining tasks."

## Preconditions

- The epic exists in Notion with the design doc pasted into its body.
- Tasks exist in the `⚙️ Tasks` database, linked to the epic, with `Blocked by`
  relations forming a DAG.
- Create a new git branch from the default branch with a standard stub based on the Notion task name. For instance for a task named 'Add login via Google OAuth',
  the branch name should be `add-login-via-google-oauth`. 

IMPORTANT: Never use the default git branch directly!

Use the `notion-mcp` skill for knowledge how to operate the Notion MCP server.

---

## Step 1: Read State from Notion

### 1.1 Fetch the epic
```json
{"id": "EPIC_URL"}
```

**Extract:**
- `content` → design doc (for context on what we are building)
- `properties["⚙️ Tasks"]` → list of task page URLs

### 1.2 Fetch every linked task
For each task URL from the epic, call `notion_notion-fetch` to get:
- `Task name`
- `Status`
- `Blocked by` (list of blocker page URLs)
- `content` (task description / implementation notes)

### 1.3 Build the Task DAG

```
TASK_A  ──► TASK_B  ──► TASK_D
  │
  └──► TASK_C
```

A task is **unblocked when** either:
- `Blocked by` is empty, OR
- Every blocker has Status ∈ `{done, finished (hide)}`.

A task is **ready for implementation when** it is unblocked and Status ∉ `{done, finished (hide), cancelled}`. The status of the task should be `to-do`. In progress or in review tasks are considered already taken.

### 1.4 Determine what to do next

| Scenario | Action |
|----------|--------|
| One or more ready tasks | Pick the **earliest** one (topological order, closest to foundation). Skip any marked `in progress` or `in-review` unless user says continue that task. |
| All remaining tasks are blocked | Report blockers and ask user to unblock or review stalled PRs. |
| Everything is `done` | Report feature complete. |

When you and the user decide what to tackle next, set the task as `in progress`.


```json
{
  "page_id": "TASK_UUID",
  "command": "update_properties",
  "properties": {
    "Status": "in progress"
  }
}
```

---

## Step 2: Understand the Task Scope

Read the task's `content` and description. It should tell you:
- Which files to create or modify
- Which acceptance tests to unskip / flesh out
- Known gotchas

Map these to the design doc sections if ambiguity exists.

---

## Step 3: Implement

### 3.1 Start clean
```bash
git status
```
Ensure you are not on the default (`main`, `master`, `develop`, ...) branch and there are no unexpected uncommitted changes.

### 3.2 Make changes
- Follow the **module-bounded** rule from design: stay within the task's module(s).
- Keep existing interfaces backward-compatible where possible.
- Add new code before wiring it to callers if the callers live in another task.

### 3.3 Confirm changes

Run linting, formatting, type-checking and tests. Determine how to run them by checking out makefiles, CI/CD yamls files, pyproject.toml, etc. Do not blindly just try out commands. If you are not confident in what to run, prompt the user.

Fix errors before committing.

---

## Step 4: Verify and Mark Complete

### 4.1 Update Notion task status
```json
{
  "page_id": "TASK_UUID",
  "command": "update_properties",
  "properties": {
    "Status": "in-review"
  }
}
```

The user will change it to `done` when the feature lands on the default branch.

IMPORTANT: Never mark the task `done` yourself.

### 4.2 Report to user
Summarize:
- What files were changed
- Which tests now pass
- What remains unblocked next (if any)

Ask: **"Ready for the next task?"**

---

## Fast-Path: The user names a specific task

If the user says "Implement Task 3" or "Do the retry dispatch task":

1. Skip the DAG scan.
2. Fetch that specific task by URL or search.
3. Read its content.
4. Go directly to **Step 3**.
5. After implementation, mark it `in-review` and report.

---

## Common Pitfalls

1. **Do not implement a blocked task.** Check `Blocked by` first. If blockers are
   not `done`, the task is not ready and implementing it risks conflicts or
   missing foundation changes. If the user insists, they should provide you with a git branch to branch of.

2. **Do not re-fetch the epic every turn unless asked.** Once you know the DAG,
   keep the task list in context. Re-fetch only if the user says "refresh state"
   or if a blocker was supposedly resolved.

3. **Leave skipped tests alone unless the task explicitly says to unskip them.**
   A later task may own that test.