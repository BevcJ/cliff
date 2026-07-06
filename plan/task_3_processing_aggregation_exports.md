# Task 3: Title-Only Processing, Aggregation, And Exports

## Objective

Process raw Serper search responses into title-only job candidates, aggregate them by company, and export review files.

## Deliverables

- Raw response parser for Serper organic results.
- Job candidate normalizer.
- Title-only role classifier.
- Deduplication logic.
- Company aggregation logic.
- CSV and Markdown exports.
- Tests for classification, deduplication, and aggregation.

## Suggested Files

```text
src/ai_hiring_radar/
  normalize.py
  classify.py
  dedupe.py
  aggregate.py
  export.py

tests/
  test_classify.py
  test_dedupe.py
  test_aggregate.py
```

## Input

Read raw files from:

```text
data/raw/searches/YYYY-MM-DD/serper_google/*.json
```

Skip `manifest.json`.

Use `response.organic_results` from each raw response.

## Job Candidate Normalization

For each organic result, extract:

- `position` as `result_rank`
- `title` as `job_title_raw`
- `link` as `source_url`
- `displayed_link`
- `snippet`
- raw wrapper metadata such as country, role search term, query, source, and collection time

Create one JSONL record per candidate:

```text
data/processed/job_candidates_YYYY-MM-DD.jsonl
```

## Company Extraction

Company extraction will be imperfect in title-only mode. Use simple heuristics and mark uncertain records for review.

Suggested parsing rules:

- If title contains ` - `, use the right side as possible company.
- If title contains ` at `, use text after ` at ` as possible company.
- If snippet contains ` at {company}` or `{company} is hiring`, use that as a weak fallback.
- If no company is parseable, set `company_raw` to `null` and keep the record with `needs_review: true`.

Do not overfit company parsing in the MVP.

## Title Normalization

Normalize titles by matching the role search term and known role terms.

Examples:

```text
Senior AI Product Manager - Example Company -> AI Product Manager
Applied AI Engineer at Example Company -> Applied AI Engineer
Lead LLM Engineer, Remote -> LLM Engineer
```

Keep the original title in `job_title_raw`.

## Role Classification

Classify using `job_title_raw`, `job_title_normalized`, and `role_search_term`.

Rules:

- Known execution role match -> `AI Execution Role`
- Known product role match -> `AI Product Role`
- AI term present but no known match -> `Unclear AI Role`
- No AI role signal -> skip candidate or mark as `Unclear AI Role` with `needs_review: true`

In title-only mode, set:

```json
{
  "evidence_quality": "title_only_search_result",
  "needs_review": true
}
```

## Deduplication

Deduplicate in this order:

1. Exact `source_url` match.
2. Same normalized company, normalized title, and country.
3. Same raw title, role search term, and country when company is missing.

Keep one canonical record and preserve all evidence URLs/search terms where possible during aggregation.

## Company Aggregation

Aggregate by `company_normalized`.

If company is missing, exclude from company exports but keep the job candidate record for debugging and future parser improvements.

Company role classification:

- Execution only -> `AI Execution Role`
- Product only -> `AI Product Role`
- Both execution and product -> `Both Execution + Product`
- Otherwise -> `Unclear AI Role`

Write company records to:

```text
data/processed/companies_YYYY-MM-DD.jsonl
```

## Export Columns

CSV export:

```text
Company
Countries
Role Classification
AI Execution Titles
AI Product Titles
Matched Search Terms
Evidence URLs
Sources
Evidence Quality
Needs Review
Review Status
Why Interesting
```

Markdown export should group companies by role classification:

- Both Execution + Product
- AI Product Role
- AI Execution Role
- Unclear AI Role

## Export Paths

```text
data/exports/companies_title_only_YYYY-MM-DD.csv
data/exports/companies_title_only_YYYY-MM-DD.md
```

## CLI Behavior

Implement:

```bash
uv run ai-hiring-radar process --date YYYY-MM-DD
uv run ai-hiring-radar export --date YYYY-MM-DD
```

The all-in-one command can run collection, processing, and export:

```bash
uv run ai-hiring-radar run --countries nl,uk,dk
```

## Acceptance Criteria

- Processing creates `job_candidates_YYYY-MM-DD.jsonl`.
- Processing creates `companies_YYYY-MM-DD.jsonl`.
- Export creates CSV and Markdown files.
- Every company record contains at least one evidence URL and matched search term.
- Every exported company has `review_status: new`.
- Tests cover role classification and deduplication.
