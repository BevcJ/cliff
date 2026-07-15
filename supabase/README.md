# Supabase Application Boundary

This directory contains the browser-facing database boundary for the inspection frontend.

## Migration model

The baseline migration reconstructs the existing production tables:

- `company_review_state`
- `inspection_collections`
- `inspection_company_snapshots`

On an existing hosted project, confirm the schema matches the baseline and mark the baseline as applied instead of re-running destructive setup manually. On a fresh local Supabase stack, the baseline creates the schema from scratch.

When linked to the existing hosted project, record the baseline in migration history before pushing later migrations:

```bash
npx supabase migration repair --status applied 20260715000000
```

The web API migration then enables RLS, removes browser table privileges, and exposes authenticated RPC functions.

## Local verification

Docker Desktop must be running.

```bash
npx supabase start
npx supabase db reset
npx supabase test db
```

The local stack is only for implementation and CI verification. Production data stays in hosted Supabase.

## Browser RPCs

Read functions:

- `inspection_list_collections()`
- `inspection_get_filter_options(p_collection_date)`
- `inspection_get_counts(p_collection_date, p_filters)`
- `inspection_list_companies(p_collection_date, p_filters, p_workflow, p_sort_field, p_sort_direction, p_page, p_page_size)`
- `inspection_get_company(p_collection_date, p_company_key)`

Write functions:

- `inspection_update_status(p_collection_date, p_company_key, p_fit_status, p_outreach_status)`
- `inspection_update_last_outreach(p_collection_date, p_company_key, p_last_outreach_date)`
- `inspection_update_notes(p_collection_date, p_company_key, p_notes, p_communication_history)`

The browser does not receive direct write privileges on any table.

## Existing Python sync

The existing Python synchronization command remains the producer of snapshot data:

```bash
uv run ai-hiring-radar sync-inspection-db --date YYYY-MM-DD
```

Keep its PostgreSQL credential server-only. Do not place that URL in the frontend environment.
