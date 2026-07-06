# Title-Only European AI Hiring Radar MVP

## Goal

Build a small Python MVP that discovers European companies hiring for specific AI execution and AI product roles.

The first version is intentionally title-only. It should answer:

- Which companies appear in hiring/search results for priority AI role titles?
- Which countries are those hiring signals connected to?
- Is the signal an AI execution role, AI product role, or both at company level?
- Which source query and URL produced the evidence?

The MVP is for company discovery, not job search.

## Initial Countries

- Netherlands
- United Kingdom
- Denmark

## Source Strategy

Use Serper Google Search as the first and only automated source.

Use LinkedIn safely through Google search results only:

```text
"AI Product Manager" site:linkedin.com/jobs/view Netherlands
"LLM Engineer" site:linkedin.com/jobs/view United Kingdom
"Applied AI Engineer" site:linkedin.com/jobs/view Denmark
```

Do not directly fetch or scrape LinkedIn job pages in the MVP.

## MVP Scope

Collect and process only:

- Job/search result title
- Company name when visible or parseable
- Country searched
- Role search term
- Full search query
- Result URL
- Source name
- Search result rank
- Search result snippet as optional weak evidence
- Collection timestamp
- Raw Serper JSON response

## Out Of Scope

- Full job description scraping
- Direct LinkedIn scraping
- Company enrichment
- Technology signal extraction from descriptions
- AI use case extraction
- Numeric scoring
- SQL database
- Web UI

## Role Taxonomy

AI execution roles:

- AI Engineer
- Applied AI Engineer
- LLM Engineer
- GenAI Engineer
- Generative AI Engineer
- AI Solutions Engineer

AI product roles:

- AI Product Manager
- GenAI Product Manager
- AI Product Owner
- AI Solutions Product Manager

## Pipeline

1. Generate search queries from countries and role terms.
2. Run Serper Google Search queries.
3. Store complete raw JSON responses locally.
4. Normalize organic results into title-only job candidate JSONL.
5. Classify each candidate using title and role search term.
6. Deduplicate candidates by URL and company/title/country fallback.
7. Aggregate candidates by company.
8. Export company review files as CSV and Markdown.

## Local Storage Layout

```text
data/
  raw/
    searches/
      YYYY-MM-DD/
        serper_google/
          nl_ai-product-manager_netherlands.json
          uk_llm-engineer_united-kingdom.json
          dk_applied-ai-engineer_denmark.json

  processed/
    job_candidates_YYYY-MM-DD.jsonl
    companies_YYYY-MM-DD.jsonl

  exports/
    companies_title_only_YYYY-MM-DD.csv
    companies_title_only_YYYY-MM-DD.md
```

## Normalized Job Candidate Contract

```json
{
  "record_type": "job_candidate",
  "job_id": "sha256_hash",
  "country_code": "nl",
  "country": "Netherlands",
  "source": "serper_google",
  "source_mode": "linkedin_safe_search",
  "source_url": "https://www.linkedin.com/jobs/view/...",
  "result_rank": 1,
  "company_raw": "Example Company",
  "company_normalized": "Example Company",
  "job_title_raw": "AI Product Manager - Example Company",
  "job_title_normalized": "AI Product Manager",
  "role_search_term": "AI Product Manager",
  "role_group": "AI Product Role",
  "search_query": "\"AI Product Manager\" site:linkedin.com/jobs/view Netherlands",
  "snippet": "Optional search result snippet",
  "evidence_quality": "title_only_search_result",
  "needs_review": true,
  "collected_at": "2026-06-13T10:30:00Z",
  "raw_file": "data/raw/searches/2026-06-13/serper_google/nl_ai-product-manager_netherlands.json"
}
```

## Company Aggregation Contract

```json
{
  "record_type": "company_intelligence_title_only",
  "company": "Example Company",
  "countries": ["Netherlands"],
  "role_classification": "AI Product Role",
  "ai_execution_titles": [],
  "ai_product_titles": ["AI Product Manager"],
  "matched_search_terms": ["AI Product Manager"],
  "evidence_urls": ["https://www.linkedin.com/jobs/view/..."],
  "sources": ["serper_google"],
  "evidence_quality": ["title_only_search_result"],
  "needs_review": true,
  "review_status": "new",
  "why_interesting": "Company appears in search results for AI Product Manager in Netherlands. Needs manual validation because evidence is title-only."
}
```

## Implementation Tasks

The implementation is split into three tasks:

1. Foundation, configuration, and JSON storage.
2. Serper query generation and raw collection.
3. Title-only processing, aggregation, and exports.

## Definition Of Done

The MVP is done when a single command or documented sequence can:

- Generate searches for Netherlands, United Kingdom, and Denmark.
- Store raw Serper JSON responses locally.
- Produce `job_candidates_YYYY-MM-DD.jsonl`.
- Produce `companies_YYYY-MM-DD.jsonl`.
- Export a CSV and Markdown company review list.
- Preserve enough metadata to trace every company signal back to the search query and source URL.
