# Design Document: Outreach Status Workflow

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Author** | OpenCode |
| **Created** | 2026-07-14 |
| **Last Updated** | 2026-07-14 |
| **Epic** | - |
| **Related Issues** | - |

---

## 1. Context

The inspection app previously modeled outreach with `not_started`, `message_sent`, `follow_up_needed`, `replied`, and `closed`. Workflow views were overlapping: every suitable lead stayed in Shortlist, and every suitable lead with any outreach activity stayed in Outreach, including closed leads. Rejected was based only on `fit_status = 'not_interesting'`.

The workflow needs clearer active and terminal outcomes. Follow-up and conversation labels should describe completed or current states, closed leads need their own view, and outreach losses need to route into Rejected.

## 2. Status Contract

The canonical outreach statuses, in UI order, are:

1. `not_started`
2. `message_sent`
3. `follow_up_sent`
4. `active_conversation`
5. `closed`
6. `lost_client_rejection`
7. `lost_no_response`

Persisted legacy rows are mapped while reading:

| Legacy value | Canonical value |
|--------------|-----------------|
| `follow_up_needed` | `follow_up_sent` |
| `replied` | `active_conversation` |

New writes accept canonical values only.

## 3. Workflow Views

| View | Membership |
|------|------------|
| `Inspect` | Records not assigned to Shortlist, Outreach, Closed, or Rejected after global filters |
| `Shortlist` | Suitable leads with `outreach_status = 'not_started'` |
| `Outreach` | Suitable leads with `message_sent`, `follow_up_sent`, or `active_conversation` |
| `Closed` | `outreach_status = 'closed'` |
| `Rejected` | Either lost outreach status, or `fit_status = 'not_interesting'` when outreach is not `closed` |

Workflow stage assignment is exclusive. A company must appear in exactly one workflow view, using this procedure:

1. `Closed` wins when `outreach_status = 'closed'`.
2. `Rejected` wins next for lost outreach statuses or `fit_status = 'not_interesting'`.
3. `Outreach` contains suitable leads whose outreach has started and is still active.
4. `Shortlist` contains suitable leads whose outreach has not started.
5. `Inspect` contains the remaining records that still need classification or have an unsupported status combination.

Terminal statuses are `closed`, `lost_client_rejection`, and `lost_no_response`. A terminal lead is removed from Shortlist and Outreach. Starting outreach removes a lead from Shortlist and moves it to Outreach. Saving a status reruns the Streamlit app but leaves the selected workflow view unchanged, so a lead that changes stage disappears from the current view and appears in the destination view.

The former Needs action filter is removed because none of the new statuses unambiguously means that an action is due.

## 4. Persistence Migration

The database check constraint and application validation must not be changed in an unsafe order. The rollout is:

1. Run `01-expand-outreach-statuses.sql` to accept both legacy and canonical values.
2. Deploy the application that normalizes legacy reads and writes canonical values.
3. Run `02-backfill-and-contract-outreach-statuses.sql` to rewrite persisted legacy rows and restore a canonical-only constraint.

Fresh installations use `architecture-design-documents/04-company-review-state/setup.sql`, which contains only the final canonical values.

## 5. Edge Cases

1. A suitable lead changed from `not_started` to an active outreach status disappears from Shortlist and appears in Outreach after rerun; the app does not navigate automatically.
2. A suitable lead changed to a terminal status disappears from Shortlist or Outreach after rerun and appears in Closed or Rejected.
3. A lead can be reopened by selecting a non-terminal outreach status, after which normal exclusive stage assignment applies.
4. Lost outreach statuses route to Rejected without changing `fit_status`; outreach outcome and fit assessment remain independent persisted dimensions.
5. Legacy statuses are tolerated only when loading persisted rows and are never exposed as dropdown choices.

## 6. Verification

Automated tests cover:

1. The exact canonical status tuple and dropdown values.
2. Both legacy-to-canonical read aliases.
3. Active, closed, and rejected workflow membership.
4. Exclusive stage assignment and movement out of Inspect and Shortlist.
5. Closed precedence over rejected fit status.
6. Existing status filtering and persistence payload behavior.
