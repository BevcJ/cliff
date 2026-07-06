# Ashby Public Job Board Prototype Plan

## Goal

Build a prototype connector that discovers and extracts public job postings from Ashby-hosted job boards.

Example:

```text
https://jobs.ashbyhq.com/everai
```

The connector should use Ashby's public job-board data endpoint used by the hosted careers page.

## Important Distinction

Ashby has an official documented API for job postings, but it requires authentication and permissions.

The public careers page uses a different endpoint:

```text
https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobBoardWithTeams
```

This endpoint is public but undocumented.

For this prototype, classify it as:

```json
{
  "platform": "ashby",
  "access_type": "public_job_board_endpoint",
  "official_api": false,
  "stability": "undocumented"
}
```

## Browser Request Notes

The browser request includes many headers, but the prototype should not copy all of them.

Do not use copied browser cookies.

CORS errors are only relevant when calling the endpoint from a browser. A backend script or server-side worker is not restricted by browser CORS.

Minimum likely request requirements:

| Field | Value |
|---|---|
| Method | `POST` |
| URL | `https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobBoardWithTeams` |
| Content-Type | `application/json` |
| Body | GraphQL operation payload |
| Cookie | Not required |
| Origin | Avoid unless required |
| Referer | Avoid unless required |

## Input

The first prototype should accept Ashby board URLs.

Examples:

```text
https://jobs.ashbyhq.com/everai
https://jobs.ashbyhq.com/pleo
```

From the URL, extract:

```json
{
  "platform": "ashby",
  "company_slug": "everai",
  "board_url": "https://jobs.ashbyhq.com/everai"
}
```

## Step 1: Capture The GraphQL Request Shape

Use DevTools once to capture the complete JSON request body for:

```text
op=ApiJobBoardWithTeams
```

The body likely includes:

```json
{
  "operationName": "ApiJobBoardWithTeams",
  "variables": {
    "organizationHostedJobsPageName": "everai"
  },
  "query": "..."
}
```

The exact request body should be saved in the connector implementation, with only the company slug changing.

If Ashby changes the frontend bundle, the connector may need to refresh this operation body.

## Step 2: Fetch Job Board Listing

Send a server-side POST request to:

```text
https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobBoardWithTeams
```

Expected response shape:

```json
{
  "data": {
    "jobBoard": {
      "teams": [],
      "jobPostings": []
    }
  }
}
```

Important fields from `teams`:

| Field | Use |
|---|---|
| `id` | Join key for job postings |
| `name` | Team or department name |
| `externalName` | Public team name if present |
| `parentTeamId` | Team hierarchy |

Important fields from `jobPostings`:

| Field | Use |
|---|---|
| `id` | Job posting ID |
| `title` | Primary role signal |
| `teamId` | Join to team |
| `locationId` | Raw location ID |
| `locationName` | Location/country/city signal |
| `workplaceType` | Remote/hybrid/onsite signal |
| `employmentType` | Full-time/part-time/etc. |
| `secondaryLocations` | Extra country/city signals |
| `compensationTierSummary` | Salary/compensation evidence |

## Step 3: Normalize Listing Data

Create one normalized record per job posting.

Example:

```json
{
  "platform": "ashby",
  "platform_company_slug": "everai",
  "source_url": "https://jobs.ashbyhq.com/everai",
  "job_id": "049a5002-6f90-41d0-a212-5fcb438d6870",
  "job_title": "Junior/Mid AI Legal Specialist (Full Remote - Austria)",
  "team": "Legal",
  "parent_team": "Operations",
  "location": "Austria",
  "workplace_type": "Remote",
  "employment_type": "FullTime",
  "compensation": "EUR 55K-85K",
  "collected_at": "2026-06-16"
}
```

## Step 4: Generate Job URLs

The prototype should generate or discover the public job detail URL for each posting.

Expected pattern to verify:

```text
https://jobs.ashbyhq.com/{company_slug}/{job_posting_id}
```

Example:

```text
https://jobs.ashbyhq.com/everai/049a5002-6f90-41d0-a212-5fcb438d6870
```

This should be verified against real Ashby boards because some boards may use slightly different routes or redirects.

## Step 5: Fetch Job Details

The listing endpoint gives good metadata but likely not the full description.

For AI intelligence, full descriptions are important.

Prototype options:

| Option | Description | Priority |
|---|---|---|
| Detail GraphQL endpoint | Observe job detail page network calls and reuse the public endpoint | Preferred |
| Job detail page HTML | Fetch public detail page and extract embedded data or text | Fallback |
| Listing-only mode | Use only title, team, and location | Acceptable for first smoke test |

The prototype should first support listing-only extraction, then add full detail extraction.

## Step 6: AI Signal Detection

Run the existing v1 AI hiring filters against Ashby jobs.

Strong title signals:

```text
AI Engineer
Applied AI Engineer
LLM Engineer
GenAI Engineer
Generative AI Engineer
AI Product Manager
GenAI Product Manager
AI Product Owner
AI Solutions Engineer
```

Additional Ashby-specific useful signals:

```text
team.name = AI
team.name = R&D
title contains AI
title contains LLM
title contains GenAI
title contains Agent
title contains Copilot
description contains OpenAI
description contains Azure OpenAI
description contains Anthropic
description contains RAG
description contains vector search
```

The first pass can classify from title and team only.

The second pass should include full job description.

## Step 7: Store Raw And Normalized Data

Store the raw Ashby response before transforming it.

Suggested records:

| Record | Purpose |
|---|---|
| `ats_company_board` | One record per discovered Ashby board |
| `raw_ats_response` | Raw JSON from Ashby endpoint |
| `raw_job_posting` | Raw job object from Ashby |
| `normalized_job_posting` | Platform-neutral job record |
| `company_hiring_signal` | Aggregated company-level AI hiring signal |

## Step 8: Error Handling

Handle these cases:

| Case | Expected Behavior |
|---|---|
| Board slug does not exist | Mark board as invalid |
| Response has no `jobBoard` | Store error and skip |
| Response has no jobs | Store board with zero active jobs |
| Endpoint returns 403/429/5xx | Retry gently, then mark temporary failure |
| Unknown response shape | Store raw response and flag connector update needed |
| Job detail fetch fails | Keep listing record and mark description missing |

## Step 9: Rate Limiting

Use conservative request behavior.

Recommended initial limits:

```text
1 request per Ashby board listing
1 request per job detail only for promising jobs
small delay between boards
cache board responses for at least 24 hours
```

Do not repeatedly fetch the same boards during development unless needed.

## Step 10: Prototype Validation

Test with a small batch first.

Seed boards:

```text
https://jobs.ashbyhq.com/everai
https://jobs.ashbyhq.com/pleo
```

Then add 10 to 25 Ashby boards discovered from search.

Validation checks:

| Check | Expected Result |
|---|---|
| Board URL parsed correctly | Company slug extracted |
| Listing endpoint works | `jobPostings` returned |
| Team mapping works | `teamId` resolves to team name |
| Job URLs work | Detail URLs resolve |
| AI title filter works | AI jobs are flagged |
| Raw data stored | Original JSON preserved |
| Normalized output created | Common schema populated |

## Step 11: Search-Based Ashby Discovery

Use search queries to discover more Ashby boards.

Examples:

```text
site:jobs.ashbyhq.com "Amsterdam"
site:jobs.ashbyhq.com "Netherlands"
site:jobs.ashbyhq.com "AI Engineer"
site:jobs.ashbyhq.com "LLM"
site:jobs.ashbyhq.com "GenAI"
site:jobs.ashbyhq.com "Product Manager" "AI"
```

From search result URLs:

1. Keep only URLs under `jobs.ashbyhq.com`.
2. Extract first path segment as company slug.
3. Normalize to board URL `https://jobs.ashbyhq.com/{slug}`.
4. Deduplicate by slug.
5. Fetch the board listing endpoint.
6. Store discovered board metadata.

## Step 12: Prototype Output

The first prototype should produce a table like:

| Company Slug | Job Title | Team | Location | Workplace | Compensation | AI Signal | Source URL |
|---|---|---|---|---|---|---|---|
| everai | Junior/Mid AI Legal Specialist | Legal | Austria | Remote | EUR 55K-85K | title contains AI | `https://jobs.ashbyhq.com/everai/...` |

## MVP Success Criteria

The Ashby prototype is successful if it can:

- Take an Ashby board URL.
- Fetch active public job postings from the Ashby public job-board endpoint.
- Normalize job postings into the common job schema.
- Identify AI-related job postings from title and team.
- Preserve source URLs and raw JSON evidence.
- Process a small batch of discovered Ashby company boards.

## Follow-Up Work

After the Ashby prototype works:

- Add job detail extraction.
- Add description-based AI technology signal extraction.
- Add search-index discovery automation.
- Add company name/domain enrichment.
- Add deduplication across other ATS platforms.
- Implement Greenhouse and Lever connectors next.
