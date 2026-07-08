# Company Web Enrichment

## Status

Draft

## Context

The Notion page `Obogatitev hiring podatkov` defines a broader enrichment need for hiring data: quickly assess which companies are interesting, what type of outreach target they represent, and who can be contacted inside the company. The accepted `01-job-description-extraction` design covers only data available in ATS/job description records, including workplace mode, AI team context, delivery context, contacts found in job data, and explicit source dates.

This design covers the next enrichment layer: company-level research from web-search-capable LLMs. The feature is intentionally scoped to company information and contacts. It does not generate final priority, offer recommendation, outreach reason, or job/company-pair recommendations.

The existing project is a Python CLI and file pipeline. It collects raw search and ATS data, processes it into `job_candidates_YYYY-MM-DD.jsonl`, aggregates title-only company records into `companies_YYYY-MM-DD.jsonl`, optionally extracts JD signals into `job_description_extracts_YYYY-MM-DD.jsonl`, and exports title-only review files. There is no company enrichment stage today.

## Goals

1. Add a separate company-level enrichment stage after `process`.
2. Enrich every company in `data/processed/companies_YYYY-MM-DD.jsonl`.
3. Use LLM-native web search through `pydantic-ai`, not custom Serper query generation for this feature.
4. Extract company facts: short description, industry, company size, founded year or age, company type, funding/investment summary, and AI/tech-forward signal.
5. Extract contacts as company information: named people and generic public inboxes in one `contacts` list.
6. Store source URLs for extracted factual fields and contacts.
7. Keep output compact: no full web page text, no search result dumps, no evidence snippets, and no raw LLM responses in the successful extract file.
8. Keep the enrichment stage independently re-runnable so prompt/model changes do not require re-collection or re-processing.

## Non-Goals

1. Job/company-pair recommendation.
2. Final priority, offer type, or outreach reason generation.
3. Job ad age extraction. Job age belongs to job-ad-level data and must not be estimated here.
4. Company/job pair output records.
5. Custom Serper query generation for company research.
6. Direct LinkedIn scraping.
7. Browser automation or crawling arbitrary websites.
8. Database storage, migrations, server APIs, queues, or background workers.
9. Export/report redesign in this feature.

## Requirements

Functional requirements:

1. Company enrichment must be LLM-based.
2. The LLM must have web-search capability through the selected provider/model integration.
3. Output must validate with Pydantic models.
4. Enum-valued fields must use explicit enum classes, not free-form strings.
5. Missing values must be stored as `null` or an empty list.
6. All companies from `companies_YYYY-MM-DD.jsonl` must be considered for enrichment.
7. Enrichment input may use existing processed company records and relevant candidate context.
8. Contacts must include only public information found through web search or existing input data.
9. Named LinkedIn person-profile contacts and named non-generic public work-email contacts are preferred over generic emails.
10. Multiple credible named contacts should be returned when available.
11. Generic public emails such as `info@`, `hello@`, `contact@`, or `careers@` are allowed as fallback contacts.
12. Email addresses must not be inferred from naming patterns.
13. LinkedIn person profile URLs are allowed when surfaced through search results or other public sources.
14. Every non-null factual field and every contact should include one or more source URLs where possible.
15. The persisted enrichment record must not include full page text, full search result payloads, or raw LLM responses.
16. The enrichment step must be runnable separately after `process`.

Non-functional requirements:

1. Preserve the current raw-first/file-first project style where practical, while accepting that LLM-native web search may not expose raw provider search payloads.
2. Keep implementation in the existing CLI/file pipeline.
3. Keep model switching simple through one config value and one CLI override.
4. Make enrichment deterministic at the application layer: same input record, prompt version, and model name should produce one persisted output record per run.
5. Make validation/model failures visible without failing the whole batch.
6. Keep the design compatible with future recommendation/export stages.

## Current State

Relevant existing modules:

1. `src/ai_hiring_radar/cli.py` owns the Typer CLI and orchestration.
2. `src/ai_hiring_radar/storage_json.py` owns raw, processed, and export paths plus JSON/JSONL helpers.
3. `src/ai_hiring_radar/normalize.py` processes raw search and ATS files into `job_candidate` records and company records.
4. `src/ai_hiring_radar/aggregate.py` aggregates candidates into title-only company records.
5. `src/ai_hiring_radar/export.py` exports title-only company review files.
6. `src/ai_hiring_radar/config.py` reads runtime settings from environment variables.
7. `src/ai_hiring_radar/job_description_extraction/*` already implements Pydantic AI structured extraction for job data.
8. `src/ai_hiring_radar/sources/serper_google.py` collects Serper search responses for job discovery, but this feature will not use custom Serper queries for enrichment.

Current company record shape is title-only. Example fields include:

1. `company`
2. `countries`
3. `role_classification`
4. `ai_execution_titles`
5. `ai_product_titles`
6. `ai_role_title_counts`
7. `matched_search_terms`
8. `evidence_urls`
9. `sources`
10. `evidence_quality`
11. `why_interesting`

Current limitations:

1. No company fact enrichment exists.
2. No web-search contact enrichment exists.
3. Company exports are title-only.
4. The project has `pydantic-ai` and a JD extraction adapter, but no reusable company enrichment module.
5. There is no field-level source URL model for enriched company facts.

## Proposed Design

Add a separate company enrichment stage that reads processed company records, joins limited candidate context for each company, calls a Pydantic AI agent with web-search capability and a Pydantic output model, validates the result, and writes one compact JSONL enrichment record per successfully processed company.

The new stage is separate from `process`, `extract-job-descriptions`, and `export`:

1. `collect-*` retrieves public search/ATS data.
2. `process` writes `job_candidates_YYYY-MM-DD.jsonl` and `companies_YYYY-MM-DD.jsonl`.
3. `extract-job-descriptions` optionally writes `job_description_extracts_YYYY-MM-DD.jsonl`.
4. `enrich-companies` writes `company_enrichment_extracts_YYYY-MM-DD.jsonl`.

This design follows the JD extraction stage's pattern: a pure data contract, an input builder, a Pydantic AI adapter, a JSONL runner with injectable extractor, and a CLI command. It does not alter existing collection, process, or export behavior.

`pydantic-ai` is already a runtime dependency. Current Pydantic AI documentation shows agents can be configured with structured output models and web-search capability, for example through `capabilities=[WebSearch()]` or provider-native search capabilities where supported. The implementation should verify the exact installed `pydantic-ai` API at implementation time because web-search support is model/provider-specific.

## Data Model

### Pydantic Output Model

The output contract should live in a new module, proposed as `src/ai_hiring_radar/company_enrichment/contracts.py`.

```python
from enum import StrEnum

from pydantic import BaseModel, Field


class CompanyType(StrEnum):
    PRODUCT_COMPANY = "product_company"
    AGENCY_CONSULTING = "agency_consulting"
    TRADITIONAL_COMPANY = "traditional_company"
    AI_NATIVE = "ai_native"
    OTHER = "other"


class AiTechForwardSignal(StrEnum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    NONE = "none"


class CompanyContactRole(StrEnum):
    HIRING_MANAGER = "hiring_manager"
    CTO = "cto"
    CEO_FOUNDER = "ceo_founder"
    HEAD_OF_AI_DATA_ENGINEERING = "head_of_ai_data_engineering"
    RECRUITER = "recruiter"
    GENERIC_COMPANY_EMAIL = "generic_company_email"
    OTHER = "other"


class CompanyContact(BaseModel):
    name: str | None = None
    role: CompanyContactRole | None = None
    title: str | None = None
    email: str | None = None
    linkedin_url: str | None = None
    source_urls: list[str] = Field(default_factory=list)


class CompanySizeRange(StrEnum):
    UP_TO_50 = "0-50"
    FROM_51_TO_100 = "51-100"
    FROM_101_TO_500 = "101-500"
    FROM_501_UP = "501+"


class CompanyEnrichment(BaseModel):
    company_description: str | None = None
    company_description_source_urls: list[str] = Field(default_factory=list)
    industry: str | None = None
    industry_source_urls: list[str] = Field(default_factory=list)
    company_size: CompanySizeRange | None = None
    company_size_source_urls: list[str] = Field(default_factory=list)
    founded_year: int | None = None
    founded_year_source_urls: list[str] = Field(default_factory=list)
    company_age: str | None = None
    company_age_source_urls: list[str] = Field(default_factory=list)
    company_type: CompanyType | None = None
    company_type_source_urls: list[str] = Field(default_factory=list)
    funding_summary: str | None = None
    funding_summary_source_urls: list[str] = Field(default_factory=list)
    ai_tech_forward_signal: AiTechForwardSignal | None = None
    ai_tech_forward_reason: str | None = None
    ai_tech_forward_source_urls: list[str] = Field(default_factory=list)
    contacts: list[CompanyContact] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
```

Field rules:

1. `company_description` is a short factual description, not marketing copy generated by the model.
2. `industry` is populated only when a source states or clearly categorizes the company.
3. `company_size` is stored as a sortable sourced bucket: `0-50`, `51-100`, `101-500`, or `501+`.
4. `founded_year` is populated only when a source explicitly states a founding year.
5. `company_age` is sourced text such as `founded in 2018`, `established in 2009`, or `15 years old`; it is not a job-ad age field.
6. `company_type` is a classification based on sourced facts, not a final sales recommendation.
7. `funding_summary` is a compact sourced summary such as `Series B, $25M total funding` when available.
8. `ai_tech_forward_signal` captures whether public web evidence suggests the company is AI/tech-forward.
9. `contacts` prioritizes multiple named technical, data, AI, ML, engineering, or technical hiring contacts.
10. A LinkedIn person profile URL is a first-class contact result even when no email is available.
11. Named public non-generic work emails are first-class contacts when explicitly found and not inferred.
12. A generic public inbox uses `role="generic_company_email"`, `name=null`, and `title=null`, and is kept as fallback.
13. Each contact should have `source_urls`; a LinkedIn-only contact may use its LinkedIn person profile URL as source evidence.
14. `source_urls` is the de-duplicated union of field/contact source URLs used by the model.

### Persisted Enrichment Record

The persisted JSONL record wraps the validated LLM output with company metadata.

```json
{
  "record_type": "company_enrichment_extract",
  "enrichment_version": "v1",
  "prompt_version": "v5",
  "model": "openai:gpt-5-mini",
  "company": "Acme AI",
  "company_key": "acme-ai",
  "countries": ["Netherlands"],
  "role_classification": "AI Execution Role",
  "ai_execution_titles": ["AI Engineer"],
  "ai_product_titles": [],
  "evidence_urls": ["https://jobs.example.com/ai-engineer"],
  "company_description": "Acme AI builds workflow automation software for logistics teams.",
  "company_description_source_urls": ["https://example.com/about"],
  "industry": "Logistics software",
  "industry_source_urls": ["https://example.com/about"],
  "company_size": "101-500",
  "company_size_source_urls": ["https://www.linkedin.com/company/acme-ai"],
  "founded_year": 2018,
  "founded_year_source_urls": ["https://www.crunchbase.com/organization/acme-ai"],
  "company_age": "Founded in 2018",
  "company_age_source_urls": ["https://www.crunchbase.com/organization/acme-ai"],
  "company_type": "product_company",
  "company_type_source_urls": ["https://example.com/about"],
  "funding_summary": "Series A funding announced in 2024.",
  "funding_summary_source_urls": ["https://example.com/news/series-a"],
  "ai_tech_forward_signal": "moderate",
  "ai_tech_forward_reason": "Public hiring and product pages mention AI workflow automation.",
  "ai_tech_forward_source_urls": ["https://example.com/product/ai"],
  "contacts": [
    {
      "name": "Ada Lovelace",
      "role": "cto",
      "title": "CTO",
      "email": "ada@example.com",
      "linkedin_url": "https://www.linkedin.com/in/ada-lovelace",
      "source_urls": ["https://example.com/team"]
    },
    {
      "name": null,
      "role": "generic_company_email",
      "title": null,
      "email": "info@example.com",
      "linkedin_url": null,
      "source_urls": ["https://example.com/contact"]
    }
  ],
  "source_urls": [
    "https://example.com/about",
    "https://example.com/team",
    "https://example.com/contact"
  ],
  "enriched_at": "2026-07-02T10:00:00Z"
}
```

The record intentionally excludes:

1. Full web page text.
2. Search result dumps.
3. Evidence snippets.
4. Confidence scores.
5. Raw LLM response text.
6. Final priority, offer type, outreach reason, and job-pair recommendations.
7. Job ad age signals.

## Interfaces

### Configuration

Add settings in `src/ai_hiring_radar/config.py`:

1. `COMPANY_ENRICHMENT_MODEL`, defaulting to a web-search-capable configured model string.
2. Provider API keys are read by the provider integration in `pydantic-ai` through its expected environment variables.

The enrichment module receives the model string as an argument so tests can inject a fake extractor without calling a real model.

### CLI

Add a Typer command:

```bash
uv run ai-hiring-radar enrich-companies --date YYYY-MM-DD
```

Expected behavior:

1. Reads `data/processed/companies_YYYY-MM-DD.jsonl`.
2. Reads `data/processed/job_candidates_YYYY-MM-DD.jsonl` if present and joins relevant candidate context by company.
3. Processes every company record unless malformed.
4. Calls the enrichment extractor for each processable company.
5. Writes `data/processed/company_enrichment_extracts_YYYY-MM-DD.jsonl`.
6. Prints counts: companies read, enriched, skipped, validation errors, LLM errors, output path.

Optional flags:

1. `--limit N` for small runs.
2. `--model MODEL` to override config for one run.
3. `--dry-run` to print planned company count without model calls.

### Storage

Use existing `write_processed_jsonl` and `read_processed_jsonl` helpers. Add naming helpers only if implementation finds repeated filename construction.

Output file:

```text
data/processed/company_enrichment_extracts_YYYY-MM-DD.jsonl
```

## Execution Flow

1. Operator runs collection commands.
2. Operator runs `process --date YYYY-MM-DD`.
3. `process_collection` writes processed company and candidate files.
4. Operator optionally runs `extract-job-descriptions --date YYYY-MM-DD`.
5. Operator runs `enrich-companies --date YYYY-MM-DD`.
6. The enrichment command loads company records.
7. The enrichment command loads candidate records and groups compact context by company.
8. For each company, the command builds an enrichment input from company metadata and candidate context.
9. The Pydantic AI agent receives a prompt instructing it to use web search and return a `CompanyEnrichment` object.
10. Pydantic validates the model output.
11. The command writes compact enrichment records to JSONL.
12. Batch summary is printed to the console.

### Enrichment Input

The input sent to the model should be compact and should avoid full job descriptions. Company enrichment can include enough hiring context to disambiguate the company and search intent:

```json
{
  "company": "Acme AI",
  "countries": ["Netherlands"],
  "role_classification": "AI Execution Role",
  "ai_execution_titles": ["AI Engineer"],
  "ai_product_titles": [],
  "ai_role_title_counts": [
    {"title": "AI Engineer", "count": 1}
  ],
  "evidence_urls": ["https://jobs.example.com/ai-engineer"],
  "sources": ["lever"],
  "candidate_context": [
    {
      "job_title_raw": "AI Engineer",
      "job_url": "https://jobs.example.com/ai-engineer",
      "platform": "lever",
      "location": "Amsterdam",
      "team": "Engineering",
      "department": "AI"
    }
  ]
}
```

The input should not include:

1. Full job descriptions.
2. JD extraction output unless a later implementation explicitly needs it.
3. Raw ATS/search payloads.

### Prompt Contract

The prompt must include these rules:

```text
Research the company using web search and extract company-level enrichment data.
Use the provided company and hiring context only to identify the correct company and relevant search intent.
Return only information supported by public sources.
Do not guess, estimate, or infer facts from stereotypes.
Do not infer private email addresses from name or domain patterns.
Generic public company inboxes are allowed as fallback contacts with role generic_company_email.
Contact research is required. After identifying the correct company, run targeted web searches for public named contacts responsible for technology, data, AI, ML, engineering, or technical hiring.
Contact research must be two-pass: first find relevant people from official about/team/leadership pages, job context, speaker pages, news, or reputable public pages; then use each discovered name and title as a search lead to find the person's LinkedIn profile URL or public non-generic work email.
For every named lead, search exact combinations such as "{person name}" "{company}" LinkedIn, "{person name}" "{title}" "{company}" LinkedIn, and site:linkedin.com/in "{person name}" "{company}".
Contacts are not limited to email addresses. A LinkedIn person profile URL is a first-class contact result.
Prefer contacts in this order: named relevant person with LinkedIn profile URL; named relevant person with public non-generic work email; named relevant person from official team, leadership, speaker, or reputable public pages; generic company inbox only as fallback.
Return multiple credible contacts when found. Do not stop after the first contact.
Do not stop at an about/team page when it provides only names and titles. Use those names and titles to search for LinkedIn person profiles.
Do not infer LinkedIn URLs from names. Only return LinkedIn person profile URLs that are found in public search results or public pages.
LinkedIn company, jobs, search, or post URLs are not valid contact profile URLs.
Company size must be one of these sortable buckets when supported by public sources: 0-50, 51-100, 101-500, or 501+.
Sources may include official company pages, Crunchbase-style databases, local company registries, CompanyWall-like pages, news/funding pages, LinkedIn pages surfaced by search, and other credible public pages.
Every non-null factual field should include source URL(s) where possible.
Every contact should include source URL(s) where possible.
Do not extract job ad age or job posting age.
Do not generate priority, offer recommendation, or outreach reason.
If a field is not present in public sources, return null or an empty list.
```

## Error Handling

Company skip cases:

1. Missing or blank `company`.
2. Non-dict or malformed company record.
3. Invalid enrichment input after compaction.

LLM/validation failure cases:

1. If a model call fails, record an error count and continue.
2. If Pydantic validation fails, record an error count and continue.
3. Failed companies are not written to the successful extracts file in v1.
4. A later follow-up may add a separate error JSONL if batch debugging requires it.

Source URL handling:

1. Empty or malformed source URL lists should become `[]`.
2. Duplicate source URLs should be removed while preserving order.
3. Source URLs returned at the field/contact level should be unioned into the top-level `source_urls` list.
4. The runner should not fail a record solely because one optional source URL list is empty.

Model capability handling:

1. If the selected model/provider does not support web search, initialization or the first call should fail visibly.
2. The CLI should print a readable error and exit for initialization failures.
3. Per-record model errors should be counted and should not abort the batch.

## Observability

Console output should include:

1. Collection date.
2. Input company path.
3. Input candidate path.
4. Output extract path.
5. Model string.
6. Companies read.
7. Companies processable.
8. Companies skipped.
9. Successful enrichments.
10. LLM errors.
11. Validation errors.
12. Dry-run status.

Persisted records include `enrichment_version`, `prompt_version`, `model`, and `enriched_at` so enrichment outputs can be compared across future prompt/model changes.

## Testing

Unit tests:

1. Pydantic model accepts valid enum values and rejects invalid values.
2. Empty/missing values become `None` or `[]`.
3. Generic public email contacts validate with `role=generic_company_email` and `name=None`.
4. Enrichment record builder does not include full job descriptions, raw search result dumps, or raw LLM responses.
5. Source URL normalization removes blank values and duplicates.
6. Top-level `source_urls` includes field-level and contact-level source URLs.
7. Enrichment input builder includes company fields and compact candidate context.
8. Enrichment input builder excludes full job description fields.

Command/runner tests:

1. `enrich-companies` reads company JSONL and writes extract JSONL.
2. Fake extractor returns deterministic `CompanyEnrichment` objects.
3. All valid companies are processed.
4. Skipped malformed companies and validation failures do not fail the whole command.
5. Dry run does not call the model and does not write extracts.

Adapter tests:

1. Adapter construction passes configured model string, output type, and web-search capability to the Pydantic AI agent.
2. Adapter tests avoid real network calls.
3. Existing JD extraction tests keep passing.

Manual verification:

1. Run `uv run pytest`.
2. Run `uv run ai-hiring-radar enrich-companies --date YYYY-MM-DD --dry-run`.
3. Run a small enrichment batch with `--limit 3` and a web-search-capable model.
4. Inspect `data/processed/company_enrichment_extracts_YYYY-MM-DD.jsonl` to verify no full page text, snippets, job age, recommendations, or raw LLM responses are persisted.

## Rollout

1. Add enrichment code behind a new CLI command only.
2. Existing `collect`, `process`, `extract-job-descriptions`, `export`, and `run` behavior remains unchanged.
3. Add config without requiring users to run enrichment unless they set a model/API key and call the command.
4. Keep output in a new JSONL file to avoid changing existing exports.
5. After review, a follow-up feature can merge company enrichment and JD extraction into prioritization/recommendation exports.

## Task Breakdown

### Dependency Graph

Task 1 is the foundation for Tasks 2 and 3. Task 4 depends on Tasks 2 and 3. Task 5 can land after Task 4. Task 6 updates docs after the CLI shape is final.

### Task 1: Add Company Enrichment Data Contracts

Scope:

1. Add `src/ai_hiring_radar/company_enrichment/` package.
2. Define enum classes: `CompanyType`, `AiTechForwardSignal`, `CompanyContactRole`.
3. Define Pydantic models: `CompanyContact`, `CompanyEnrichment`.
4. Add constants: `ENRICHMENT_VERSION`, `PROMPT_VERSION`, `COMPANY_ENRICHMENT_RECORD_TYPE`, `COMPANY_ENRICHMENT_PROMPT`, `DEFAULT_COMPANY_ENRICHMENT_MODEL`.
5. Add pure helper functions to normalize source URLs.
6. Add pure helper functions to build compact persisted enrichment records.
7. Ensure record builders do not persist full descriptions or raw responses.

Files likely changed:

1. `src/ai_hiring_radar/company_enrichment/__init__.py`
2. `src/ai_hiring_radar/company_enrichment/contracts.py`
3. `src/ai_hiring_radar/company_enrichment/constants.py`
4. `src/ai_hiring_radar/company_enrichment/records.py`
5. `src/ai_hiring_radar/company_enrichment/text.py`
6. `tests/test_company_enrichment.py`

Verification:

1. Unit tests validate enum acceptance/rejection.
2. Unit tests validate generic email contact shape.
3. Unit tests validate the persisted record shape excludes full job descriptions and raw model/search content.
4. Unit tests validate source URL normalization and unioning.

### Task 2: Add Enrichment Input Builder

Scope:

1. Build an input object from a company record and grouped candidate records.
2. Include company metadata, role titles/counts, evidence URLs, sources, and compact candidate context.
3. Exclude full job description fields: `description`, `description_plain`, `job_description_sections`, and `lists`.
4. Skip malformed companies and companies without a usable company name.

Files likely changed:

1. `src/ai_hiring_radar/company_enrichment/inputs.py`
2. `tests/test_company_enrichment.py`

Verification:

1. Tests verify all relevant company fields are included.
2. Tests verify compact candidate context is included.
3. Tests verify full job description fields are excluded.
4. Tests verify malformed records are skipped.

### Task 3: Add Pydantic AI Web-Search Adapter And Config

Scope:

1. Add `COMPANY_ENRICHMENT_MODEL` setting to `config.py`.
2. Add a real extractor adapter that creates a Pydantic AI `Agent` with `CompanyEnrichment` as `output_type`.
3. Configure web-search capability for the selected Pydantic AI API/provider.
4. Keep model string injectable for CLI overrides and tests.
5. Avoid real network calls in tests.

Files likely changed:

1. `src/ai_hiring_radar/config.py`
2. `src/ai_hiring_radar/company_enrichment/adapter.py`
3. `.env.example` if present
4. `tests/test_config.py`
5. `tests/test_company_enrichment.py`

Verification:

1. Tests verify config reads the company enrichment model setting.
2. Tests verify adapter construction passes the configured model string and output type.
3. Tests verify web-search capability configuration without making network calls.
4. Existing tests still pass without requiring provider API keys.

### Task 4: Add JSONL Enrichment Runner With Injectable Extractor

Scope:

1. Add a runner that reads `companies_YYYY-MM-DD.jsonl`.
2. Read `job_candidates_YYYY-MM-DD.jsonl` when available and group by company.
3. Build enrichment input for every company.
4. Accept an injectable extractor callable/protocol so tests do not call a real LLM.
5. Write `company_enrichment_extracts_YYYY-MM-DD.jsonl`.
6. Return a result dataclass with counts and output path.

Files likely changed:

1. `src/ai_hiring_radar/company_enrichment/contracts.py`
2. `src/ai_hiring_radar/company_enrichment/runner.py`
3. `src/ai_hiring_radar/company_enrichment/inputs.py`
4. `src/ai_hiring_radar/company_enrichment/records.py`
5. `tests/test_company_enrichment.py`

Verification:

1. Unit tests use a fake extractor and verify output JSONL.
2. Unit tests verify skipped, successful, and failed records are counted correctly.
3. Unit tests verify all companies are processed when valid.
4. Unit tests verify dry run does not write output.

### Task 5: Add CLI Command

Scope:

1. Add `enrich-companies --date YYYY-MM-DD` to `src/ai_hiring_radar/cli.py`.
2. Add optional `--limit`, `--model`, and `--dry-run` flags.
3. Wire CLI command to the JSONL runner and Pydantic AI adapter.
4. Print collection date, model, input paths, output path, read count, processable count, skipped count, success count, LLM error count, and validation error count.

Files likely changed:

1. `src/ai_hiring_radar/cli.py`
2. `tests/test_cli.py`
3. `tests/test_company_enrichment.py` if CLI tests live there

Verification:

1. CLI test uses fake extraction path or monkeypatched runner.
2. Dry run does not call the model and does not write extracts.
3. Existing CLI commands keep working.

### Task 6: Documentation Update

Scope:

1. Update `README.md` with the new enrichment command.
2. Document the required model config environment variable.
3. Document the step-by-step flow: collect, process, extract JDs if desired, enrich companies.
4. Document that output JSONL does not include full web page text, snippets, job age, recommendations, or raw LLM responses.

Files likely changed:

1. `README.md`
2. `.env.example` if not already updated in Task 3

Verification:

1. Command examples are copy-pasteable.
2. Documentation matches actual CLI flags.

## Open Questions

None. V1 decisions are locked:

1. Company-level enrichment only.
2. Contacts are part of company enrichment.
3. Generic public emails are stored in the same contacts list as named contacts.
4. All companies are enriched.
5. LLM-native web search is used.
6. Source URLs are stored.
7. Job age is excluded from this feature.
8. Final recommendations are deferred.
