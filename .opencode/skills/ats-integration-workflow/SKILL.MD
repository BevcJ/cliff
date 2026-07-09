---
name: ats-integration-workflow
description: >
  Use when the user asks to add a new ATS provider integration, ATS connector,
  public job board source, or AI Hiring Radar job board integration in this
  repository. Trigger for prompts like "add Greenhouse", "implement a new ATS
  integration", "add a Workable connector", or "integrate another job board".
---

# ATS Integration Workflow

Use this workflow to add a new ATS provider integration to the AI Hiring Radar
repository.

## Core Rule

Always prepare and confirm a detailed integration plan with the user before
implementation. Do not start coding until the user explicitly approves the plan.

## Required Context

Before proposing a plan, read the relevant repository context:

- `AGENT.md` for coding style and project principles.
- `README.md` for current CLI, processing, and documented integrations.
- `ats_provider_integration_guide.md` for the integration contract.
- `ats_public_job_board_discovery_plan.md` for provider priority and access rank.
- `ats_integration/README.md` if present.
- `ats_integration/{provider}.md` for the requested provider, when present.

Also inspect existing implementations in `src/ai_hiring_radar/sources/`,
`src/ai_hiring_radar/normalize.py`, `src/ai_hiring_radar/cli.py`, and matching
tests before designing the new connector.

## Initial Response Flow

When the user asks to add an integration:

1. Identify the requested ATS provider, if named.
2. List already implemented integrations by checking the source files, CLI, and README.
3. List providers with integration reports in `ats_integration/`.
4. List high-priority possible additions from `ats_public_job_board_discovery_plan.md`.
5. State whether the requested provider already has a report or needs research first.
6. Ask any focused clarification needed to choose the provider or scope.

## Integration Report Handling

If `ats_integration/{provider}.md` exists, use it as the main provider-specific
source for the plan. Extract:

- Public URL patterns and company identifier strategy.
- Best public listing endpoint, feed, embedded JSON, or HTML fallback.
- Request method, required params, pagination, language, region, or tenant details.
- Response shape and job fields.
- Raw response wrapper metadata.
- Normalization, country inference, and dedupe notes.
- Known risks, endpoint stability, and operational constraints.
- Recommended tests.

If the report is missing, research the public careers/job-board access first
and prepare the report before coding. Only use public job postings and public
career-board data. Do not use private/admin APIs, copied browser cookies,
authentication bypass, CAPTCHA bypass, LinkedIn scraping, Indeed scraping, or
non-public data.

## Title And Description Handling

The default integration target is title plus job-description data.

For every provider, explicitly determine whether public listing, feed, or detail
responses include job descriptions. When descriptions are available from public
provider data, preserve and normalize them. Title-only behavior should be treated
as a fallback for providers or endpoints where descriptions are unavailable,
incomplete, or would require fragile detail-page scraping outside the agreed
scope.

The plan and implementation should cover:

- Whether descriptions are present in the listing/feed response.
- Whether public detail fetching is needed to retrieve descriptions.
- Whether detail fetching is stable and worth the added complexity for this provider.
- Which description fields are stored, for example `description`, `description_html`, `description_plain`, `job_description_sections`, or provider-specific sections.
- Whether raw provider responses are preserved unchanged before any description cleanup.
- Whether descriptions are useful for `extract-job-descriptions`.
- Whether company enrichment still receives only compact candidate context and not full job descriptions.

Default behavior:

- Use job titles and provider-supplied descriptions when available from public data.
- Use title-only candidate records only when job descriptions are not available or are intentionally out of scope for the provider.
- Keep raw HTML or provider-native sections when useful for audit or replay.
- Add cleaned text to `description` when practical.
- Do not use private/admin APIs, copied cookies, or authenticated endpoints to get descriptions.
- Do not fetch fragile detail pages only for completeness unless the provider report or user scope justifies it.

Preferred wording:

```text
Title and job-description integration where public descriptions are available.
```

Fallback wording:

```text
Title-only fallback because public job descriptions are unavailable or out of scope.
```

## Planning Checklist

The plan presented to the user should cover:

- Provider priority and access rank.
- Discovery query patterns.
- URL parsing and provider company identifier.
- Public listing/detail endpoint, feed, or fallback strategy.
- Request headers, params, pagination, region/language handling, and rate limits.
- Raw response storage path and wrapper fields.
- Job normalization into the existing `job_candidate` schema.
- Title and job-description availability, normalization, and fallback behavior.
- Country inference from provider job-location data only.
- Dedupe identity using `source + platform_company_slug + platform_job_id`.
- CLI commands to add.
- Processing pipeline integration before dedupe and aggregation.
- Tests and verification commands.
- README and integration-report updates.

After presenting the plan, ask the user to approve it before implementation.

## Code Structure Outline

Use the closest existing connector as the implementation template:

| Template | Use For |
|---|---|
| `greenhouse.py` | Simple public JSON GET endpoint |
| `lever.py` | JSON endpoint with region/API fallback |
| `personio.py` | XML, RSS, or feed-style source |
| `smartrecruiters.py` | Paginated public JSON API |
| `ashby.py` | GraphQL-style source or optional detail fetches |

A typical integration touches:

- `src/ai_hiring_radar/sources/{provider}.py`: connector, discovery, fetch, raw wrapper, collection manifest.
- `src/ai_hiring_radar/models.py`: add `SourceName` value.
- `src/ai_hiring_radar/normalize.py`: add platform, provider helpers, normalization branch, pipeline inclusion.
- `src/ai_hiring_radar/cli.py`: add imports plus `discover-{provider}` and `collect-{provider}` commands.
- `src/ai_hiring_radar/company_enrichment/text.py`: classify new ATS domains as ATS URLs when relevant.
- `README.md`: add CLI examples and connector summary.
- `ats_integration/{provider}.md`: add or update the integration report.
- `tests/test_{provider}.py`: add provider-specific coverage.

Provider source files usually include, in this order:

1. Constants for endpoints, access type, stability, and discovery defaults.
2. `{Provider}Board`, optional `{Provider}FetchResult`, and `{Provider}CollectionResult` dataclasses.
3. URL parsing and normalization helpers.
4. `AtsDiscoveryProvider` plus wrappers around shared discovery helpers.
5. Endpoint or request-body builders.
6. `{Provider}Client.fetch_board()` and `close()`.
7. `build_raw_{provider}_response_record()` preserving the unmodified response.
8. Response-shape validation and collection error helpers.
9. `collect_{provider}_boards()` writing raw files and `manifest.json`.

Normalization usually adds provider-specific helpers for postings, title, job ID,
source URL, team/department, location, description fields, and country inputs.
It should preserve provider-supplied descriptions when available, infer country
from provider job-location data, use stable IDs from provider identity, and return
existing `job_candidate` fields. Title-only normalization should be used only as a
fallback when public descriptions are unavailable or intentionally out of scope.

Tests should cover URL parsing, discovery extraction, client request shape, raw
wrapper and manifest writing, title and description normalization, title-only
fallback behavior when descriptions are unavailable, country inference, and
`process_collection()` inclusion.

## Implementation Rules

After user approval:

- Make the smallest correct code changes.
- Follow `AGENT.md`: imports at the top, semantic names, modern Python unions, top-down scripts.
- Preserve raw provider responses before transformation.
- Keep request headers minimal and identify the crawler where appropriate.
- Continue per-board collection on errors and record structured failures.
- Do not add compatibility layers unless there is a concrete need.
- Run targeted provider tests first, then broader tests when practical.

## Done Criteria

The integration is complete when it can discover public boards, fetch current
public listings, store raw evidence, normalize AI job candidates with titles and
provider-supplied descriptions where available, fall back to title-only records
when descriptions are unavailable, participate in processing/dedupe/aggregation,
expose CLI commands, and pass the relevant tests.
