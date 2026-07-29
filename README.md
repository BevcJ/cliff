# AI Hiring Radar

MVP for discovering European companies with hiring signals for AI execution and AI product roles. AI candidate inclusion is title-based, and ATS job descriptions are retained when public provider feeds or APIs include them.

## Setup

```bash
uv sync --dev
cp .env.example .env
```

Set `SERPER_API_KEY` in `.env` before running search collection or ATS commands that perform discovery. `ats collect PROVIDER` does not require Serper when explicit `--board-url` or `--boards-file` input is provided. For job description extraction with Azure AI Foundry, set `JOB_DESCRIPTION_EXTRACTION_PROVIDER=azure`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT_NAME`, and `AZURE_OPENAI_API_KEY`. For company enrichment, set `COMPANY_ENRICHMENT_MODEL` to a web-search-capable Azure deployment such as `gpt-5.4-mini` and use the same Azure endpoint/key settings. For Postgres-backed inspection snapshots and shared review state, set `AI_HIRING_RADAR_DATABASE_URL` to the Supabase Postgres transaction-pooler connection string.

## CLI

```bash
uv run ai-hiring-radar --help
uv run ai-hiring-radar collect --countries nl,uk,dk
uv run ai-hiring-radar collect --countries nl,uk,dk --dry-run
uv run ai-hiring-radar collect --countries nl --role "AI Product Manager"
uv run ai-hiring-radar collect --countries nl,uk,dk --limit 10
uv run ai-hiring-radar collect --countries nl --location-depth cities --dry-run
uv run ai-hiring-radar collect --countries nl --location-depth cities --limit 20
uv run ai-hiring-radar ats --help
uv run ai-hiring-radar ats discover workable --countries nl --dry-run
uv run ai-hiring-radar ats collect workable --countries nl
uv run ai-hiring-radar ats collect workable --board-url https://apply.workable.com/workmotion
uv run ai-hiring-radar ats collect workable --boards-file boards.jsonl --collection-date YYYY-MM-DD --resume
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
uv run ai-hiring-radar sync-inspection-db --date YYYY-MM-DD
```

ATS discovery commands use Serper Google Search to find public provider boards. Provider collection commands store raw, self-describing JSON wrappers under `data/raw/ats/YYYY-MM-DD/<provider>/`.

Use `--location-depth cities` on ATS discovery and collection commands for deeper coverage across configured city/location variants. Provider defaults use city-level discovery where supported.

Supported ATS providers are `ashby`, `greenhouse`, `lever`, `personio`, `recruitee`, `smartrecruiters`, `teamtailor`, and `workable`. All use the same `ats discover PROVIDER` and `ats collect PROVIDER` interface. The optional `--language` setting affects Personio only and defaults to `en`; other providers ignore it. Use `ats discover --help` and `ats collect --help` for all options.

Processing reads those raw wrappers, writes deduplicated candidates to `data/processed/job_candidates_YYYY-MM-DD.jsonl`, aggregates parseable companies to `data/processed/companies_YYYY-MM-DD.jsonl`, and exports review files under `data/exports/`. ATS candidates may include provider-supplied job descriptions, but AI role filtering remains based on job titles.

Job description extraction is a separate step after `process`. It reads `data/processed/job_candidates_YYYY-MM-DD.jsonl`, calls a Pydantic AI structured-output extractor for candidates with useful ATS/job-description data, and writes compact records to `data/processed/job_description_extracts_YYYY-MM-DD.jsonl`. The extraction output includes model/prompt metadata and structured datapoints, but intentionally does not include full job description text, evidence snippets, raw LLM responses, or confidence scores. Progress is shown by default with `tqdm`; use `--no-progress` for quiet runs. Successful records are appended immediately, and reruns resume by skipping existing `job_id`s. Use `--countries nl,dk` to extract only jobs matching any selected country code before broadening to the full set later. Use `--restart` to clear existing extracts first. Use `--dry-run` to count processable candidates without model calls or output writes.

Company enrichment is a separate step after `process`. It reads `data/processed/companies_YYYY-MM-DD.jsonl`, optionally joins compact context from `data/processed/job_candidates_YYYY-MM-DD.jsonl`, uses Pydantic AI with native web search to extract company facts and public contacts, and writes `data/processed/company_enrichment_extracts_YYYY-MM-DD.jsonl`. The enrichment output includes model/prompt metadata, source URLs, company facts, named public contacts, generic public inboxes, and compact `quality_warnings`, but intentionally does not include full web page text, search result dumps, evidence snippets, job age, final recommendations, outreach reasons, or raw LLM responses. Progress is shown by default with `tqdm`; use `--no-progress` for quiet runs. Successful records are appended immediately, and reruns resume by skipping existing `company_key`s. Use `--countries nl,dk` to enrich only companies matching any selected country code before broadening to the full set later. Use `--restart` to clear existing extracts first. Core company facts require non-ATS source URLs; if a model returns ATS-only company facts, the runner retries once, then removes only unsupported fields while preserving useful ATS-supported AI hiring signals. Use `--dry-run` to count processable companies without model calls or output writes.

The inspection application is a desktop React SPA in `frontend/`. It authenticates invited users with Supabase Auth and reads/writes through the RLS-protected RPCs in `supabase/`. It does not read local JSONL files or receive a PostgreSQL password. The Python pipeline remains the producer: `sync-inspection-db` joins the canonical processed files, removes full descriptions and raw nested payloads, and transactionally replaces generated snapshots without modifying `company_review_state`.

The included Azure AI Foundry configuration uses the Responses API endpoint `https://dev-aibooking-openai.openai.azure.com/openai/responses?api-version=2025-04-01-preview` and deployment `gpt-5.4-mini`. The extractor normalizes that URL to the Azure resource endpoint and uses Pydantic AI's `OpenAIResponsesModel` automatically. If `--model` is omitted, `AZURE_OPENAI_DEPLOYMENT_NAME` is used before `JOB_DESCRIPTION_EXTRACTION_MODEL`.

Company enrichment uses `COMPANY_ENRICHMENT_MODEL` directly as the Azure deployment name when `AZURE_OPENAI_ENDPOINT` is configured. The default is `gpt-5.4-mini`; if Azure rejects native web search for that deployment/API version, the command reports sampled model errors in the CLI summary and continues counting per-record failures.

### Contact Email Provider Evaluation

The contact email evaluation is isolated from production data. Run the read-only query in `supabase/snippets/contact_email_evaluation_export.sql` in the Supabase SQL Editor and download its result as CSV. Add `FULLENRICH_API_KEY` and `PROSPEO_API_KEY` to the root `.env`, then run:

```bash
uv run ai-hiring-radar evaluate-contact-emails --input ~/Downloads/contact_email_evaluation_export.csv
```

Use `--limit 1` for the first live check. It selects the first contact that has a usable first and last name and does not already have an email:

```bash
uv run ai-hiring-radar evaluate-contact-emails \
  --input ~/Downloads/contact_email_evaluation_export.csv \
  --limit 1
```

The command submits only contacts without an existing email, requests work emails only, waits for FullEnrich, and writes raw provider responses plus `comparison.csv` and `summary.json` under `data/evaluations/`. That directory is ignored by Git. The command never writes to Supabase or the inspection JSONL files. To resume an interrupted run without repeating completed provider requests, rerun with the same input and the printed run directory:

```bash
uv run ai-hiring-radar evaluate-contact-emails \
  --input ~/Downloads/contact_email_evaluation_export.csv \
  --output-dir data/evaluations/contact-email-YYYYMMDD-HHMMSS
```

ATS discovery uses provider-specific hosted-board URL patterns, while collection keeps each provider's request, pagination, fallback, and detail-fetch behavior inside its source module. Raw responses use the shared `data/raw/ats/YYYY-MM-DD/PROVIDER/` layout and are included by `process` before dedupe and company aggregation. See the [ATS Provider Integration Guide](ats_provider_integration_guide.md) and [ATS integration notes](ats_integration/README.md) for provider details. Use `debug-ashby-discovery` for a paste-friendly summary of Ashby discovery errors.

## Inspection Application

Apply the migrations and local verification steps in `supabase/README.md`, then synchronize a processed date:

```bash
uv run ai-hiring-radar sync-inspection-db --date YYYY-MM-DD
```

The sync command requires `companies_YYYY-MM-DD.jsonl`. Candidate, job-description extraction, and enrichment files for the same date are optional inputs. It stores one sanitized snapshot row per company. Re-syncing a date replaces generated snapshots for that date without modifying `company_review_state`.

The persisted status values are:

```text
fit_status: unreviewed, best_fit, possible_fit, not_interesting
outreach_status: not_started, message_sent, follow_up_sent, active_conversation, closed, lost_client_rejection, lost_no_response
```

`closed` leads appear in the Closed workflow view. Leads with either `lost_client_rejection` or `lost_no_response` appear in Rejected, which also includes leads whose fit status is `not_interesting`. Terminal outreach statuses are excluded from Shortlist and Outreach; `closed` takes precedence if a lead also has a rejected fit status.

Last Outreach is a company-level calendar date edited directly in the table beside Fit and Outreach. `message_sent` and `follow_up_sent` require a date. The table displays a follow-up indicator: green through day 3, yellow on days 4-5, and red from day 6 onward. Other statuses do not show an age reminder. Partial RPCs ensure status edits preserve Last Outreach and notes/history, date edits preserve statuses and notes/history, and note edits preserve statuses and dates.

For local synchronization, use `.env` or your shell with the server-only producer role:

```bash
AI_HIRING_RADAR_DATABASE_URL=postgresql://app_inspection_user.PROJECT_REF:PASSWORD@aws-REGION.pooler.supabase.com:6543/postgres
```

The `app_inspection_user` role is limited to inserting and replacing generated collections and snapshots. It cannot access `company_review_state`; the TypeScript frontend reads and writes review state only through authenticated Supabase RPCs. Never expose the producer URL or password through `VITE_*` variables.

Frontend setup, authentication, build, and static-hosting requirements are documented in `frontend/README.md`. Only `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` belong in the browser environment. Never expose `AI_HIRING_RADAR_DATABASE_URL`, a Supabase secret/service-role key, or a PostgreSQL password through `VITE_*` variables.

## Tests

```bash
uv run pytest
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
npx supabase test db
```
