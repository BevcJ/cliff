# Task 1: Foundation, Configuration, And JSON Storage

## Objective

Create the Python project foundation and the configuration/storage layer needed by the title-only MVP.

This task should not call external APIs yet.

## Deliverables

- Python package scaffold.
- CLI entrypoint.
- Environment variable loading for `SERPER_API_KEY`.
- Country configuration for Netherlands, United Kingdom, and Denmark.
- Role taxonomy configuration.
- JSON/JSONL storage helpers.
- Basic tests for configuration loading and deterministic IDs.

## Suggested Files

```text
pyproject.toml
.env.example
README.md

src/ai_hiring_radar/
  __init__.py
  cli.py
  config.py
  models.py
  storage_json.py
  hashing.py

src/ai_hiring_radar/configs/
  countries.yaml
  taxonomy.yaml

tests/
  test_config.py
  test_hashing.py
```

## Dependencies

Recommended dependencies:

```text
typer
pydantic
pydantic-settings
python-dotenv
httpx
pyyaml
rich
pytest
```

Use `uv` as the dependency manager unless there is a reason not to.

## Country Config

Create `countries.yaml` with:

```yaml
countries:
  nl:
    name: Netherlands
    search_location: Netherlands
    gl: nl
    hl: en
    search_locations:
      - label: Netherlands
        query_location: Netherlands
        serper_location: Netherlands
      - label: Amsterdam
        query_location: Amsterdam Netherlands
        serper_location: Amsterdam, North Holland, Netherlands
      - label: Rotterdam
        query_location: Rotterdam Netherlands
        serper_location: Rotterdam, South Holland, Netherlands

  uk:
    name: United Kingdom
    search_location: United Kingdom
    gl: uk
    hl: en

  dk:
    name: Denmark
    search_location: Denmark
    gl: dk
    hl: en
```

## Taxonomy Config

Create `taxonomy.yaml` with:

```yaml
execution_roles:
  - AI Engineer
  - Applied AI Engineer
  - LLM Engineer
  - GenAI Engineer
  - Generative AI Engineer
  - AI Solutions Engineer

product_roles:
  - AI Product Manager
  - GenAI Product Manager
  - AI Product Owner
  - AI Solutions Product Manager
```

## Environment Config

Create `.env.example`:

```text
SERPER_API_KEY=your_serper_api_key_here
```

The app should fail with a clear message if a collection command is run without `SERPER_API_KEY`.

## Storage Helpers

Implement helpers for:

- Creating date-based directories under `data/raw/searches/YYYY-MM-DD/serper_google/`.
- Writing a full raw Serper response as pretty JSON.
- Writing JSONL records under `data/processed/`.
- Writing exports under `data/exports/`.
- Generating stable filenames from country code, role term, and search location.

## Stable IDs

Create deterministic SHA-256 IDs from normalized fields.

For job candidates, use:

```text
source_url | country_code | role_search_term | job_title_raw
```

If `source_url` is missing, use:

```text
country_code | role_search_term | job_title_raw | snippet
```

## CLI Skeleton

Add commands as stubs:

```bash
uv run ai-hiring-radar collect --countries nl,uk,dk
uv run ai-hiring-radar process --date YYYY-MM-DD
uv run ai-hiring-radar export --date YYYY-MM-DD
uv run ai-hiring-radar run --countries nl,uk,dk
```

At the end of this task, commands may print planned actions but should not yet call Serper.

## Acceptance Criteria

- `uv run ai-hiring-radar --help` works.
- Country config loads successfully.
- Taxonomy config loads successfully.
- Storage helper can write and read back a sample JSON file.
- Tests pass.
- No external API calls are made in this task.
