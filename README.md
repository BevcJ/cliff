# AI Hiring Radar

Title-only MVP for discovering European companies with hiring signals for AI execution and AI product roles.

## Setup

```bash
uv sync --dev
cp .env.example .env
```

Set `SERPER_API_KEY` in `.env` before running collection-related commands. For job description extraction with Azure AI Foundry, set `JOB_DESCRIPTION_EXTRACTION_PROVIDER=azure`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT_NAME`, and `AZURE_OPENAI_API_KEY`. For company enrichment, set `COMPANY_ENRICHMENT_MODEL` to a web-search-capable Azure deployment such as `gpt-5.4-mini` and use the same Azure endpoint/key settings. For optional shared company review state in the Streamlit inspection app, set `AI_HIRING_RADAR_REVIEW_STATE_DATABASE_URL` to the Supabase Postgres transaction-pooler connection string.

## CLI

```bash
uv run ai-hiring-radar --help
uv run ai-hiring-radar collect --countries nl,uk,dk
uv run ai-hiring-radar collect --countries nl,uk,dk --dry-run
uv run ai-hiring-radar collect --countries nl --role "AI Product Manager"
uv run ai-hiring-radar collect --countries nl,uk,dk --limit 10
uv run ai-hiring-radar collect --countries nl --location-depth cities --dry-run
uv run ai-hiring-radar collect --countries nl --location-depth cities --limit 20
uv run ai-hiring-radar discover-ashby --countries nl --dry-run
uv run ai-hiring-radar collect-ashby --countries nl
uv run ai-hiring-radar collect-ashby --countries nl --pages 3 --results-per-query 10
uv run ai-hiring-radar collect-ashby --countries nl --discovery-depth broad
uv run ai-hiring-radar collect-ashby --board-url https://jobs.ashbyhq.com/everai
uv run ai-hiring-radar discover-lever --countries nl --dry-run
uv run ai-hiring-radar collect-lever --countries nl
uv run ai-hiring-radar collect-lever --board-url https://jobs.lever.co/insiderone
uv run ai-hiring-radar discover-personio --countries nl --dry-run
uv run ai-hiring-radar collect-personio --countries nl
uv run ai-hiring-radar collect-personio --board-url https://acme.jobs.personio.com
uv run ai-hiring-radar discover-workable --countries nl --dry-run
uv run ai-hiring-radar collect-workable --countries nl
uv run ai-hiring-radar collect-workable --board-url https://apply.workable.com/workmotion
uv run ai-hiring-radar debug-ashby-discovery --sample 5 --json
uv run ai-hiring-radar process --date YYYY-MM-DD
uv run ai-hiring-radar extract-job-descriptions --date YYYY-MM-DD --dry-run
uv run ai-hiring-radar extract-job-descriptions --date YYYY-MM-DD --countries nl,dk --dry-run
uv run ai-hiring-radar extract-job-descriptions --date YYYY-MM-DD --limit 10
uv run ai-hiring-radar extract-job-descriptions --date YYYY-MM-DD --model gpt-5.4-mini
uv run ai-hiring-radar extract-job-descriptions --date YYYY-MM-DD --restart
uv run ai-hiring-radar enrich-companies --date YYYY-MM-DD --dry-run
uv run ai-hiring-radar enrich-companies --date YYYY-MM-DD --countries nl,dk --dry-run
uv run ai-hiring-radar enrich-companies --date YYYY-MM-DD --limit 3
uv run ai-hiring-radar enrich-companies --date YYYY-MM-DD --model gpt-5.4-mini
uv run ai-hiring-radar enrich-companies --date YYYY-MM-DD --no-progress
uv run ai-hiring-radar export --date YYYY-MM-DD
uv run ai-hiring-radar inspect --date YYYY-MM-DD
uv run ai-hiring-radar run --countries nl,uk,dk
```

Collection uses Serper Google Search and stores raw, self-describing JSON wrappers under `data/raw/searches/YYYY-MM-DD/serper_google/`. It targets LinkedIn `/jobs/view` results, skips aggregate LinkedIn listing pages, and does not fetch LinkedIn pages directly.

Use `--location-depth cities` for deeper Netherlands-only coverage across configured city/location variants. The default remains `--location-depth country`.

Processing reads those raw wrappers, writes deduplicated candidates to `data/processed/job_candidates_YYYY-MM-DD.jsonl`, aggregates parseable companies to `data/processed/companies_YYYY-MM-DD.jsonl`, and exports review files under `data/exports/`.

Job description extraction is a separate step after `process`. It reads `data/processed/job_candidates_YYYY-MM-DD.jsonl`, calls a Pydantic AI structured-output extractor for candidates with useful ATS/job-description data, and writes compact records to `data/processed/job_description_extracts_YYYY-MM-DD.jsonl`. The extraction output includes model/prompt metadata and structured datapoints, but intentionally does not include full job description text, evidence snippets, raw LLM responses, or confidence scores. Progress is shown by default with `tqdm`; use `--no-progress` for quiet runs. Successful records are appended immediately, and reruns resume by skipping existing `job_id`s. Use `--countries nl,dk` to extract only jobs matching any selected country code before broadening to the full set later. Use `--restart` to clear existing extracts first. Use `--dry-run` to count processable candidates without model calls or output writes.

Company enrichment is a separate step after `process`. It reads `data/processed/companies_YYYY-MM-DD.jsonl`, optionally joins compact context from `data/processed/job_candidates_YYYY-MM-DD.jsonl`, uses Pydantic AI with native web search to extract company facts and public contacts, and writes `data/processed/company_enrichment_extracts_YYYY-MM-DD.jsonl`. The enrichment output includes model/prompt metadata, source URLs, company facts, named public contacts, generic public inboxes, and compact `quality_warnings`, but intentionally does not include full web page text, search result dumps, evidence snippets, job age, final recommendations, outreach reasons, or raw LLM responses. Progress is shown by default with `tqdm`; use `--no-progress` for quiet runs. Successful records are appended immediately, and reruns resume by skipping existing `company_key`s. Use `--countries nl,dk` to enrich only companies matching any selected country code before broadening to the full set later. Use `--restart` to clear existing extracts first. Core company facts require non-ATS source URLs; if a model returns ATS-only company facts, the runner retries once, then removes only unsupported fields while preserving useful ATS-supported AI hiring signals. Use `--dry-run` to count processable companies without model calls or output writes.

Inspection launches a Streamlit UI for one processed date. It requires `data/processed/companies_YYYY-MM-DD.jsonl` and uses `data/processed/job_candidates_YYYY-MM-DD.jsonl`, `data/processed/job_description_extracts_YYYY-MM-DD.jsonl`, and `data/processed/company_enrichment_extracts_YYYY-MM-DD.jsonl` when present. Missing optional files only reduce available filters and detail panels. The UI supports filtering by workplace mode, AI team context, delivery context, company type, raw company size, country, role classification, source/platform, AI tech-forward signal, fit status, outreach status, needs-action state, contacts, JD extracts, enrichment status, and free-text search. Generated company/job/enrichment facts remain read-only. When Supabase review-state persistence is configured, operators can save shared company fit status, outreach status, and notes. When Supabase is missing or unavailable, the app still renders generated inspection data in read-only mode.

The included Azure AI Foundry configuration uses the Responses API endpoint `https://dev-aibooking-openai.openai.azure.com/openai/responses?api-version=2025-04-01-preview` and deployment `gpt-5.4-mini`. The extractor normalizes that URL to the Azure resource endpoint and uses Pydantic AI's `OpenAIResponsesModel` automatically. If `--model` is omitted, `AZURE_OPENAI_DEPLOYMENT_NAME` is used before `JOB_DESCRIPTION_EXTRACTION_MODEL`.

Company enrichment uses `COMPANY_ENRICHMENT_MODEL` directly as the Azure deployment name when `AZURE_OPENAI_ENDPOINT` is configured. The default is `gpt-5.4-mini`; if Azure rejects native web search for that deployment/API version, the command reports sampled model errors in the CLI summary and continues counting per-record failures.

Ashby collection discovers public boards through exhaustive Serper query families such as `site:jobs.ashbyhq.com`, `site:jobs.ashbyhq.com "Netherlands"`, `site:jobs.ashbyhq.com "AI Engineer"`, `site:jobs.ashbyhq.com "LLM" "Netherlands"`, and `site:jobs.ashbyhq.com "AI Engineer" "Amsterdam"`. By default it uses configured city locations, broad AI terms, v1 role terms, 10 results per query, and 2 result pages. Use `--discovery-depth broad` or `--discovery-depth standard` to reduce query volume. It fetches each discovered board through Ashby's public hosted job-board endpoint, attempts per-job detail retrieval for full descriptions, and stores raw board responses under `data/raw/ats/YYYY-MM-DD/ashby/`. Detail retrieval failures are recorded per job and do not fail the whole board collection. Processing includes Ashby candidates alongside Serper candidates. Use `debug-ashby-discovery` to print a paste-friendly summary of discovery errors from the latest manifest.

Lever collection uses the same discovery flow against `site:jobs.lever.co`, then fetches public postings from `https://api.lever.co/v0/postings/{site_slug}?mode=json` with an EU API fallback. Raw board responses are stored under `data/raw/ats/YYYY-MM-DD/lever/` and are included by `process` before dedupe and company aggregation.

Personio collection uses the same discovery flow against `site:*.jobs.personio.com`, then fetches the public XML feed from `https://{company_slug}.jobs.personio.com/xml?language=en`. Raw XML is stored in JSON wrappers under `data/raw/ats/YYYY-MM-DD/personio/` and is included by `process` before dedupe and company aggregation.

Workable collection uses the same discovery flow against `site:apply.workable.com`, then fetches public hosted-careers JSON from `https://apply.workable.com/api/v3/accounts/{company_slug}/jobs` and per-job details from `https://apply.workable.com/api/v2/accounts/{company_slug}/jobs/{shortcode}`. Raw listing and detail responses are stored under `data/raw/ats/YYYY-MM-DD/workable/` and are included by `process` before dedupe and company aggregation.

## Streamlit Cloud Deployment

The deployment entrypoint is `streamlit_app.py`.

The local inspection app reads full processed JSONL files from `data/processed/`. For Streamlit Cloud, export a compact inspection artifact instead of committing the full candidate data:

```bash
uv run ai-hiring-radar export-inspection --date YYYY-MM-DD
```

This writes `data/processed/inspection_companies_YYYY-MM-DD.jsonl`. The artifact keeps company facts, job metadata, extracted filters, contacts, and URLs, but omits full job-description text and raw nested payloads. If no date is provided, the deployed app loads the latest `companies_YYYY-MM-DD.jsonl` or `inspection_companies_YYYY-MM-DD.jsonl` file. Optional date override:

```text
https://your-app.streamlit.app/?date=YYYY-MM-DD
```

### Shared Review State

The inspection app can persist current manual review state in Supabase Postgres. Generated JSONL and compact inspection artifacts stay read-only; only `company_review_state` is written by the app.

Create the table and indexes by running the SQL in `architecture-design-documents/04-company-review-state/setup.sql` from the Supabase SQL editor.

The persisted status values are:

```text
fit_status: unreviewed, best_fit, possible_fit, not_interesting
outreach_status: not_started, message_sent, follow_up_needed, replied, closed
```

For Streamlit Cloud, add the Supabase transaction-pooler connection string to app secrets:

```toml
[connections.supabase_review_state]
url = "postgres://app_user.PROJECT_REF:PASSWORD@aws-REGION.pooler.supabase.com:6543/postgres"
```

For local development, use `.env` or your shell:

```bash
AI_HIRING_RADAR_REVIEW_STATE_DATABASE_URL=postgres://app_user.PROJECT_REF:PASSWORD@aws-REGION.pooler.supabase.com:6543/postgres
```

Use a dedicated least-privilege database user for the app. It only needs `usage` on schema `public` and `select`, `insert`, and `update` on `public.company_review_state`; it does not need delete, DDL, or access to generated files.

To verify configuration, launch the app and check the top summary area. It shows whether review-state persistence is enabled, how many persisted rows loaded for the current generated records, how many records are using defaults, and counts by fit/outreach status. If the URL is missing, the table is missing, or Supabase is unavailable, the app shows a warning and disables save controls while still rendering generated inspection data.

For the simplest private deployment:

1. Create a private GitHub repository.
2. Generate and commit the selected `data/processed/inspection_companies_*.jsonl` artifact files you want visible.
3. In Streamlit Community Cloud, create a new private app from the repository.
4. Set the main file path to `streamlit_app.py`.
5. Add trusted viewers in Streamlit Community Cloud.

Only commit processed data that is safe for the selected viewers. Do not commit `.env`, `data/raw/`, `data/exports/`, or full `job_candidates_*.jsonl` files. Candidate files may include job descriptions, and enrichment files may include public contacts.

## Tests

```bash
uv run pytest
```
