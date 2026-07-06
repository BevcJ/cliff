# ATS Public Job Board Discovery Plan

## Goal

Discover companies with public career boards hosted on applicant tracking systems, then extract active job postings as structured hiring signals.

The goal is company intelligence, not job search.

## Core Idea

Many companies expose public job data through hosted ATS job boards.

Instead of relying only on Google Search, LinkedIn, or generic job boards, we can discover ATS-hosted career pages and extract jobs directly from the source.

Example boards:

- `https://jobs.ashbyhq.com/pleo`
- `https://careers.smartrecruiters.com/Gousto1`
- `https://boards.greenhouse.io/company`
- `https://jobs.lever.co/company`

## Important Constraint

We should not aim to find every customer of every ATS.

The realistic goal is:

Find all publicly discoverable companies with public ATS-hosted job boards.

This is enough for the company intelligence use case because companies without public job postings do not provide useful hiring evidence.

## Target Platforms

Access rank:

- `1` means simple public structured source.
- `2` means practical but connector-specific, less stable, or requires endpoint discovery.
- `3` means hard, fragile, mostly HTML/stateful, or generally requires authenticated APIs for clean access.

| MVP Priority | Access Rank | Platform | Common URL Pattern | Best Public Access Path | Notes |
|---|---:|---|---|---|---|
| 1 | 1 | Ashby | `jobs.ashbyhq.com/{company}` | `https://api.ashbyhq.com/posting-api/job-board/{company}` | Very clean public JSON. Include compensation where available. |
| 1 | 1 | Greenhouse | `boards.greenhouse.io/{company}` | `https://boards-api.greenhouse.io/v1/boards/{company}/jobs?content=true` | Official public JSON. No auth for GET endpoints. |
| 1 | 1 | Lever | `jobs.lever.co/{company}` | `https://api.lever.co/v0/postings/{company}?mode=json` | Public JSON. EU tenants may use `api.eu.lever.co`. |
| 1 | 1 | SmartRecruiters | `careers.smartrecruiters.com/{company}` | `https://api.smartrecruiters.com/v1/companies/{company}/postings` | Public JSON works for postings; use detail endpoint for full descriptions. |
| 1 | 1 | Recruitee | `{company}.recruitee.com` | `https://{company}.recruitee.com/api/offers/` | Strong public careers API, very relevant for NL/EU. |
| 1 | 1 | Personio | `{company}.jobs.personio.com` | `https://{company}.jobs.personio.com/xml?language=en` | Public XML feed if enabled; language-specific. |
| 1 | 1 | Teamtailor | `{company}.teamtailor.com` | `https://{company}.teamtailor.com/jobs.rss` | RSS is easy for listings; detail pages may need HTML parsing. |
| 2 | 2 | Workable | `apply.workable.com/{company}` | `POST https://apply.workable.com/api/v3/accounts/{company}/jobs` | Public JSON used by hosted board; schema is less documented and JS-driven. |
| 2 | 2 | BambooHR | `{company}.bamboohr.com/careers` | `https://{company}.bamboohr.com/careers/list` | Public JSON often works; official ATS API requires auth. |
| 2 | 2 | Homerun | `{company}.homerun.co` | Career page, sitemap, Atom/RSS feed where exposed | Public API needs auth; use page/feed discovery. Relevant for Dutch startups. |
| 2 | 2 | Comeet | `www.comeet.com/jobs/{company}` | `https://www.comeet.co/careers-api/2.0/company/{uid}/positions?token={token}` | Careers API is clean but requires UID and token, usually discovered from page/settings. |
| 2 | 2 | BreezyHR | `{company}.breezy.hr` | Public career HTML pages | Official API requires auth; public pages are parseable but less structured. |
| 2 | 2 | Jobvite | `jobs.jobvite.com/{company}` | `https://jobs.jobvite.com/{company}/search?nl=1` | Mostly HTML with some public facets endpoints; tenant-specific. |
| 2 | 2 | iCIMS | `careers-{company}.icims.com` | Modern sites often expose `/api/jobs` | Modern iCIMS/Jibe sites can be JSON; legacy portals are HTML-heavy. |
| 2 | 2 | Workday | `{company}.wd*.myworkdayjobs.com` | `POST https://{host}/wday/cxs/{tenant}/{site}/jobs` | Public JSON but requires tenant/site discovery and POST body handling. |
| 3 | 3 | SAP SuccessFactors | `*.jobs2web.com` / custom domains | Public `/search/` pages | Mostly custom HTML and custom domains; lower connector stability. |
| 3 | 3 | Oracle Taleo | `*.taleo.net` | `careersection/{section}/jobsearch.ftl` | Stateful, older, tenant-specific, fragile. |
| 3 | 3 | JazzHR | Various JazzHR / `applytojob` URLs | Public apply pages or authenticated `resumatorapi` | Official API requires API key; public data access is inconsistent. |
| 3 | 3 | Zoho Recruit | `recruit.zoho.*` patterns | Public portal pages with digest/token | Official API uses OAuth; public portals are hard to generalize. |

## Discovery Sources

| Source | Use |
|---|---|
| Search index discovery | Fast MVP discovery from known ATS URL patterns |
| Common Crawl | Scalable historical discovery of ATS URLs |
| Company-first website crawling | Find careers pages from known company domains |
| Technology fingerprint providers | Detect ATS links/widgets on company websites |
| Manual seed lists | Add high-value companies or industries |
| Existing CRM/company lists | Best input when available |

## Search Index Discovery

Use search queries that combine ATS domains with geography and AI hiring terms.

Example queries:

```text
site:jobs.ashbyhq.com "Amsterdam"
site:jobs.ashbyhq.com "Netherlands"
site:jobs.ashbyhq.com "AI Engineer"
site:jobs.ashbyhq.com "LLM"
site:boards.greenhouse.io "Amsterdam" "AI Engineer"
site:jobs.lever.co "Netherlands" "Product Manager AI"
site:careers.smartrecruiters.com "Amsterdam" "GenAI"
site:*.teamtailor.com "Netherlands" "AI Engineer"
site:*.recruitee.com "Amsterdam" "AI"
site:*.jobs.personio.com "Netherlands" "AI"
site:apply.workable.com "Amsterdam" "Machine Learning"
```

Search results should be treated as board discovery candidates, not final job data.

## Connector Build Order

Build connectors in this order:

| Order | Platforms | Reason |
|---:|---|---|
| 1 | Ashby, Greenhouse, Lever | Cleanest public JSON and common in target startup/scaleup segment |
| 2 | Recruitee, Personio, Teamtailor | Strong EU coverage and simple public feeds/APIs |
| 3 | SmartRecruiters, Workable | Useful coverage; slightly more connector-specific handling |
| 4 | BambooHR, Homerun, Comeet, BreezyHR, Jobvite, iCIMS, Workday | Good expansion set after core connector abstraction works |
| 5 | SAP SuccessFactors, Oracle Taleo, JazzHR, Zoho Recruit | Defer unless coverage requires them; highest maintenance cost |

Do not build connectors around private customer/admin APIs unless we have explicit customer authorization. The default ingestion path should use only data already presented on the public careers site.

## Discovery Output

Each discovered board should be normalized into a board record.

```json
{
  "company_name": "Pleo",
  "company_domain": "pleo.io",
  "ats_platform": "ashby",
  "board_url": "https://jobs.ashbyhq.com/pleo",
  "platform_company_slug": "pleo",
  "access_rank": 1,
  "public_listing_url": "https://api.ashbyhq.com/posting-api/job-board/pleo",
  "auth_required_for_public_jobs": false,
  "discovered_from": "search_index",
  "discovered_at": "2026-06-16"
}
```

## Extraction Strategy

For each discovered board:

1. Detect ATS platform from URL.
2. Extract platform-specific company identifier.
3. Fetch active job postings using the best available structured source.
4. Store raw response.
5. Normalize job postings into a common schema.
6. Fetch job detail pages or detail APIs where needed.
7. Extract title, location, team, employment type, description, compensation, and source URL.
8. Run AI role and technology signal classification.
9. Aggregate signals at company level.

## Structured Data Priority

Use the most structured source available.

| Priority | Method | Notes |
|---|---|---|
| 1 | Official public job-board API/feed | Best source when no authentication is required for public jobs |
| 2 | Public careers-page API | Often used by hosted careers page; may be undocumented but directly represents visible jobs |
| 3 | RSS/XML feed | Good for Teamtailor, Personio, and similar platforms |
| 4 | Embedded JSON / Next.js data | Good fallback for custom frontends |
| 5 | JSON-LD `JobPosting` schema | Useful but often incomplete |
| 6 | HTML parsing | Last resort for public pages only |

Avoid private ATS APIs for discovery and extraction. They may expose non-public candidate, requisition, or admin data and normally require customer credentials.

## Public Endpoint Examples

These endpoint templates should be treated as connector-specific starting points, not universal guarantees.

| Platform | Listing Endpoint | Detail Strategy |
|---|---|---|
| Ashby | `GET https://api.ashbyhq.com/posting-api/job-board/{slug}` | Same response usually includes enough detail; fetch job URL if needed |
| Greenhouse | `GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true` | `GET /v1/boards/{slug}/jobs/{job_id}?questions=true&pay_transparency=true` when needed |
| Lever | `GET https://api.lever.co/v0/postings/{slug}?mode=json` | `GET https://api.lever.co/v0/postings/{slug}/{posting_id}` |
| SmartRecruiters | `GET https://api.smartrecruiters.com/v1/companies/{slug}/postings` | Follow posting detail URL from `ref` |
| Recruitee | `GET https://{slug}.recruitee.com/api/offers/` | Use offer detail page/API fields from listing response |
| Personio | `GET https://{slug}.jobs.personio.com/xml?language=en` | XML usually includes detail fields; fetch job page if incomplete |
| Teamtailor | `GET https://{slug}.teamtailor.com/jobs.rss` | Fetch public job page for full description if RSS is partial |
| Workable | `POST https://apply.workable.com/api/v3/accounts/{slug}/jobs` | `GET https://apply.workable.com/api/v2/accounts/{slug}/jobs/{shortcode}` where available |
| BambooHR | `GET https://{slug}.bamboohr.com/careers/list` | Fetch public job detail page if list response is partial |
| Workday | `POST https://{host}/wday/cxs/{tenant}/{site}/jobs` | `GET https://{host}/wday/cxs/{tenant}/{site}/job/{external_path}` |

## Connector Abstraction

Each ATS should have its own connector.

A connector should define:

```json
{
  "platform": "ashby",
  "url_patterns": ["https://jobs.ashbyhq.com/{slug}"],
  "company_identifier_strategy": "path_slug",
  "access_rank": 1,
  "auth_required_for_public_jobs": false,
  "listing_strategy": "public_job_board_api",
  "listing_endpoint_template": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
  "detail_strategy": "public_job_detail_api_or_page",
  "official_public_api": true,
  "private_api_required": false,
  "stability": "stable_public_endpoint"
}
```

Connector outputs should include both raw and normalized data. Raw response storage is important because endpoint schemas change and because normalization bugs should be replayable.

## Normalized Job Schema

```json
{
  "job_id": "platform-specific-id",
  "platform": "ashby",
  "company_name": "EverAI",
  "platform_company_slug": "everai",
  "job_title": "Junior/Mid AI Legal Specialist",
  "team": "Legal",
  "location": "Austria",
  "country": "Austria",
  "workplace_type": "Remote",
  "employment_type": "FullTime",
  "compensation": "EUR 55K-85K",
  "description": "...",
  "job_url": "https://jobs.ashbyhq.com/everai/...",
  "source_url": "https://jobs.ashbyhq.com/everai",
  "collected_at": "2026-06-16"
}
```

## MVP Workflow

1. Start with Ashby, Greenhouse, Lever, Recruitee, Personio, Teamtailor, SmartRecruiters, and Workable.
2. Use search index queries to discover board URLs.
3. Deduplicate by platform and company slug.
4. Extract current job listings from each board.
5. Store raw responses and normalized job records.
6. Apply AI role filters from the existing company intelligence plan.
7. Fetch full job descriptions only for matching or promising postings.
8. Aggregate matching jobs into company intelligence records.
9. Manually review the first batch of companies.
10. Expand discovery with Common Crawl once the connector model works.

## Legal And Operational Notes

Only collect public job postings.

Do not use copied browser cookies.

Do not use private customer/admin APIs without explicit authorization.

Do not bypass authentication, CAPTCHA, bot challenges, or paywalls.

Do not scrape LinkedIn or Indeed directly.

Respect reasonable crawl rates.

Respect robots.txt and each site/platform's terms where applicable.

Identify the crawler when appropriate.

Cache responses.

Store evidence URLs and timestamps.

Treat undocumented APIs as unstable and connector-specific.

Build each connector so it can be replaced if an endpoint changes.

## MVP Success Criteria

The MVP is successful if it can:

- Discover ATS-hosted company boards from search results.
- Extract current job postings from at least one platform.
- Normalize postings into a common schema.
- Identify companies hiring AI execution or AI product roles.
- Produce evidence-backed company intelligence records.
