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

The web API migration then enables RLS, removes browser table privileges, and exposes authenticated RPC functions. `roles.sql` defines the passwordless `app_inspection_user` role, and the inspection sync migration grants that role the minimum table privileges and RLS policies needed by the Python producer.

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
- `inspection_update_status_with_last_outreach(p_collection_date, p_company_key, p_fit_status, p_outreach_status, p_last_outreach_date)`
- `inspection_update_last_outreach(p_collection_date, p_company_key, p_last_outreach_date)`
- `inspection_update_star(p_collection_date, p_company_key, p_is_starred)`
- `inspection_update_notes(p_collection_date, p_company_key, p_notes, p_communication_history)`

The browser does not receive direct write privileges on any table.

`message_sent` and `follow_up_sent` require `last_outreach_date`. The combined status/date RPC creates those states atomically. Fit-only status updates preserve an existing date, and the date RPC rejects clearing it while the company remains in an outbound status.

## Existing Python sync

The existing Python synchronization command remains the producer of snapshot data:

```bash
uv run ai-hiring-radar sync-inspection-db --date YYYY-MM-DD
```

The producer connects directly to PostgreSQL as `app_inspection_user`. Its hosted RLS provisioning is managed separately from the browser application boundary. It can:

- insert and delete collection rows;
- read only `inspection_collections.collection_date`, which is required by the replacement delete;
- insert company snapshot rows.

It cannot read snapshots, update generated rows, or access `company_review_state`. Review-state access remains behind the authenticated browser RPCs.

Keep the producer's PostgreSQL credential server-only. Do not place that URL in the frontend environment.

## Hosted deployment

Apply custom roles and migrations together. The role must exist before the migration that references it:

```bash
npx supabase db push --dry-run --include-roles
npx supabase db push --include-roles
```

`roles.sql` intentionally contains no password. Connect to the hosted database with an administrative `psql` session and set a generated password without placing it in shell history or source control:

```text
\password app_inspection_user
```

Set `AI_HIRING_RADAR_DATABASE_URL` to the transaction-pooler URL for that role. The username format is `app_inspection_user.PROJECT_REF`; percent-encode special characters in the password.

Run the same date twice after deployment. The first command verifies inserts and the second verifies RLS-protected replacement deletion:

```bash
uv run ai-hiring-radar sync-inspection-db --date YYYY-MM-DD
uv run ai-hiring-radar sync-inspection-db --date YYYY-MM-DD
```

After both runs succeed and no service uses the old credential, revoke its table privileges and disable login for the old role. Do not disable the old role before switching `AI_HIRING_RADAR_DATABASE_URL`.
