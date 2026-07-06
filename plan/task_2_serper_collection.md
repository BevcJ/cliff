# Task 2: Serper Query Generation And Raw Collection

## Objective

Implement safe LinkedIn discovery using Serper Google Search.

This task collects raw search result JSON only. It must not directly fetch LinkedIn pages.

## Deliverables

- Query generator for countries and role terms.
- Serper Google Search client.
- Raw response storage under `data/raw/searches/YYYY-MM-DD/serper_google/`.
- Collection manifest summarizing each query and output file.
- CLI command for running collection.

## Suggested Files

```text
src/ai_hiring_radar/
  query_builder.py

src/ai_hiring_radar/sources/
  __init__.py
  serper_google.py

tests/
  test_query_builder.py
```

## Query Strategy

Generate one country-level query for each role term by default:

```text
"{role_term}" site:linkedin.com/jobs/view {country_name}
```

Examples:

```text
"AI Engineer" site:linkedin.com/jobs/view Netherlands
"AI Product Manager" site:linkedin.com/jobs/view United Kingdom
"LLM Engineer" site:linkedin.com/jobs/view Denmark
```

Initial query count:

```text
3 countries x 10 role terms = 30 queries
```

For deeper Netherlands-only runs, `--location-depth cities` expands each role term across configured Netherlands city/location variants.

Expanded Netherlands query count:

```text
1 country x 11 search locations x 10 role terms = 110 queries
```

## Serper Request Parameters

Use the Serper Google Search endpoint:

```python
headers = {
    "X-API-KEY": serper_api_key,
    "Content-Type": "application/json",
}
payload = {
    "q": search_query,
    "location": search_location.serper_location,
    "gl": country.gl,
    "hl": country.hl,
    "num": 10,
}
```

Store the full response returned by Serper.

## Raw Response Contract

Each raw file should include a wrapper around the Serper response so the local data is self-describing:

```json
{
  "record_type": "raw_search_response",
  "source": "serper_google",
  "source_mode": "linkedin_safe_search",
  "country_code": "nl",
  "country": "Netherlands",
  "search_location_label": "Amsterdam",
  "query_location": "Amsterdam Netherlands",
  "serper_location": "Amsterdam, North Holland, Netherlands",
  "role_search_term": "AI Product Manager",
  "search_query": "\"AI Product Manager\" site:linkedin.com/jobs/view Amsterdam Netherlands",
  "request_params": {
    "q": "\"AI Product Manager\" site:linkedin.com/jobs/view Amsterdam Netherlands",
    "location": "Amsterdam, North Holland, Netherlands",
    "gl": "nl",
    "hl": "en",
    "num": 10
  },
  "collected_at": "2026-06-13T10:30:00Z",
  "response": {}
}
```

Do not write the API key to raw files.

## Manifest Contract

Create one manifest file per collection run:

```text
data/raw/searches/YYYY-MM-DD/serper_google/manifest.json
```

Manifest shape:

```json
{
  "record_type": "collection_manifest",
  "source": "serper_google",
  "source_mode": "linkedin_safe_search",
  "started_at": "2026-06-13T10:30:00Z",
  "finished_at": "2026-06-13T10:35:00Z",
  "countries": ["nl"],
  "search_locations": ["Netherlands", "Amsterdam", "Rotterdam"],
  "query_count": 110,
  "result_files": [
    "data/raw/searches/2026-06-13/serper_google/nl_ai-product-manager_amsterdam.json"
  ],
  "errors": []
}
```

## Error Handling

- Continue collection if one query fails.
- Record failed query details in the manifest.
- Do not retry aggressively in the MVP.
- Print a concise summary at the end.

## CLI Behavior

Implement:

```bash
uv run ai-hiring-radar collect --countries nl,uk,dk
```

Optional flags:

```bash
uv run ai-hiring-radar collect --countries nl,uk,dk --limit 10
uv run ai-hiring-radar collect --countries nl --role "AI Product Manager"
uv run ai-hiring-radar collect --countries nl,uk,dk --dry-run
```

`--dry-run` should print generated queries without calling Serper.

## Acceptance Criteria

- Dry run prints the expected 30 country-level LinkedIn-safe queries.
- Real collection writes one raw JSON file per query.
- Raw files contain full Serper responses and no API key.
- Manifest records successful and failed queries.
- LinkedIn pages are not fetched directly.
