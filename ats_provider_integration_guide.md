# ATS Provider Integration Guide

This guide describes the minimal process for adding a new ATS provider to the AI hiring radar pipeline.

## Goal

Each provider integration should discover public company boards, retrieve current job listings, store raw evidence, normalize title-only job candidates, and reuse the existing AI signal pipeline.

## 1. Discovery

Find public ATS-hosted job boards through search-index queries.

Examples:

```text
site:jobs.ashbyhq.com "Netherlands"
site:boards.greenhouse.io "Amsterdam"
site:jobs.lever.co "AI Engineer"
```

Discovery output should be one board record per company board:

```json
{
  "record_type": "ats_company_board",
  "platform": "ashby",
  "platform_company_slug": "everai",
  "board_url": "https://jobs.ashbyhq.com/everai",
  "discovered_from": "search_index",
  "source": "serper_google",
  "source_mode": "ats_board_discovery_search"
}
```

Normalize and deduplicate boards by platform plus provider-specific company identifier.

## 2. Provider Identifier

Every connector must define how the provider selects the company board.

For Ashby, the company is selected by the first URL path segment and sent as a GraphQL variable:

```json
{
  "organizationHostedJobsPageName": "everai"
}
```

For other providers, this may be a path slug, subdomain, board token, company ID, or API parameter.

## 3. Retrieve Listings

Use the most structured public source available.

Preferred order:

1. Public job-board API.
2. Embedded JSON or framework data.
3. JSON-LD `JobPosting` data.
4. HTML parsing as a fallback.

Do not use copied browser cookies. Keep request headers minimal. Fetch one board listing per company first.

## 4. Store Raw Data

Store the unmodified provider response before transformation.

Suggested path:

```text
data/raw/ats/YYYY-MM-DD/{platform}/{company_slug}.json
```

Raw wrappers should include:

```json
{
  "record_type": "raw_ats_response",
  "platform": "ashby",
  "source": "ashby",
  "source_mode": "public_job_board_endpoint",
  "platform_company_slug": "everai",
  "board_url": "https://jobs.ashbyhq.com/everai",
  "collected_at": "2026-06-16T10:00:00Z",
  "response": {}
}
```

## 5. Normalize Jobs

Convert provider-specific jobs into the existing `job_candidate` schema.

Minimum fields:

```json
{
  "record_type": "job_candidate",
  "source": "ashby",
  "source_mode": "public_job_board_endpoint",
  "source_url": "https://jobs.ashbyhq.com/everai",
  "platform": "ashby",
  "platform_company_slug": "everai",
  "platform_job_id": "provider-job-id",
  "company_normalized": "Everai",
  "job_title_raw": "Senior AI Engineer",
  "job_title_normalized": "AI Engineer",
  "location": "Amsterdam",
  "job_locations_raw": ["Amsterdam"],
  "country": "Netherlands",
  "country_code": "nl",
  "job_countries": ["Netherlands"],
  "job_country_codes": ["nl"],
  "role_search_term": "AI Engineer",
  "role_group": "AI Execution Role",
  "evidence_quality": "title_only_ats_listing",
  "needs_review": true
}
```

Country fields must be inferred from provider job-location data, not from the discovery query country. Discovery country only describes how a board was found and is not proof that a role is open in that country.

Use this precedence for job-country inference:

1. Structured country fields from the provider response, for example postal address country.
2. Provider office locations when they are available.
3. Provider display location as a fallback.
4. Deterministic city-to-country and country-alias mapping, for example `Amsterdam` -> `Netherlands`, `Remote - Netherlands` -> `Netherlands`, `UK` -> `United Kingdom`.

For Greenhouse specifically, prefer `offices[].location` or `offices[].name` over `location.name` when office locations infer a country. This handles cases where `location.name` says `Remote - Netherlands` but the actual office location is another country.

Keep raw provider locations in `location`, `job_location_raw`, `job_locations_raw`, `secondary_locations`, or `offices` so the inferred countries can be audited later.

For the first pass, keep only title-level AI signals. Do not fetch job detail pages unless explicitly needed later.

## 6. Pipeline Integration

The provider should integrate before dedupe and aggregation.

Processing flow:

```text
raw ATS response -> normalized job_candidate -> dedupe -> aggregate companies -> export CSV/Markdown
```

Reuse the existing role taxonomy and classifier:

```text
normalize_job_title -> classify_role -> aggregate_companies
```

Dedupe must prefer provider identity before URL identity:

```text
source + platform_company_slug + platform_job_id
```

This avoids collapsing multiple jobs from the same board when `source_url` is the board URL.

## 7. Error Handling

Handle these cases explicitly:

| Case | Behavior |
|---|---|
| Board URL cannot be parsed | Skip and record discovery error |
| Board does not exist | Store error and mark invalid |
| Listing response has no jobs | Store raw response and continue |
| Unknown response shape | Store raw response and flag connector update needed |
| 403, 429, or 5xx | Retry gently, then record temporary failure |

## 8. Tests

Each provider should have tests for:

```text
URL parsing
discovery result extraction
request body or endpoint shape
raw response wrapper
job normalization
AI title filtering
country inference from job location data
dedupe with multiple jobs on one board
process_collection integration
```

## Done Criteria

A provider integration is complete when it can discover public boards, fetch listing data, store raw evidence, normalize title-only AI job candidates, and produce company-level records through the existing processing and export commands.
