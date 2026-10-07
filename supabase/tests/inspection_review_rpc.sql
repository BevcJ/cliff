begin;

select plan(22);

insert into public.inspection_collections (
  collection_date,
  source_kind,
  snapshot_count,
  job_count
) values (
  date '2026-01-01',
  'test',
  1,
  1
);

insert into public.inspection_company_snapshots (
  collection_date,
  company_key,
  company,
  job_count,
  summary_payload,
  detail_payload
) values (
  date '2026-01-01',
  'test company',
  'Test Company',
  1,
  '{"company":"Test Company","company_key":"test company"}'::jsonb,
  '{"company":"Test Company","company_key":"test company","jobs":[]}'::jsonb
);

select ok(
  not has_function_privilege('anon', 'public.inspection_list_collections()', 'execute'),
  'anonymous users cannot execute inspection RPCs'
);

select ok(
  has_function_privilege('authenticated', 'public.inspection_list_collections()', 'execute'),
  'authenticated users can execute public inspection RPCs'
);

select ok(
  not has_table_privilege('authenticated', 'public.company_review_state', 'insert'),
  'authenticated users cannot write review tables directly'
);

select ok(
  not has_function_privilege('anon', 'public.inspection_update_star(date,text,boolean)', 'execute'),
  'anonymous users cannot update company stars'
);

set local role authenticated;
select set_config(
  'request.jwt.claims',
  '{"sub":"00000000-0000-4000-8000-000000000001","email":"reviewer@example.com","role":"authenticated"}',
  true
);

select is(
  public.inspection_update_notes(
    date '2026-01-01',
    'test company',
    'General note',
    'Sent introduction'
  ) ->> 'notes',
  'General note',
  'notes RPC stores notes'
);

select is(
  public.inspection_update_star(
    date '2026-01-01',
    'test company',
    true
  ) ->> 'is_starred',
  'true',
  'star RPC marks the company'
);

select is(
  public.inspection_update_star(
    date '2026-01-01',
    'test company',
    true
  ) ->> 'notes',
  'General note',
  'star RPC preserves notes'
);

select is(
  public.inspection_update_star(
    date '2026-01-01',
    'test company',
    true
  ) ->> 'last_updated_by',
  'reviewer@example.com',
  'star RPC preserves review audit metadata'
);

select is(
  public.inspection_update_status(
    date '2026-01-01',
    'test company',
    'best_fit',
    'not_started'
  ) ->> 'notes',
  'General note',
  'status RPC preserves notes'
);

select is(
  public.inspection_update_status(
    date '2026-01-01',
    'test company',
    'best_fit',
    'not_started'
  ) ->> 'is_starred',
  'true',
  'status RPC preserves the star'
);

select throws_ok(
  $$select public.inspection_update_status(date '2026-01-01', 'test company', 'best_fit', 'message_sent')$$,
  '22023',
  'last_outreach_date is required for outbound outreach statuses',
  'outbound status without a date is rejected'
);

select is(
  public.inspection_update_status_with_last_outreach(
    date '2026-01-01',
    'test company',
    'best_fit',
    'message_sent',
    current_date
  ) ->> 'last_outreach_date',
  current_date::text,
  'outbound status and date are stored atomically'
);

select is(
  public.inspection_update_status(
    date '2026-01-01',
    'test company',
    'possible_fit',
    'message_sent'
  ) ->> 'last_outreach_date',
  current_date::text,
  'fit-only edit preserves the outbound date'
);

select throws_ok(
  $$select public.inspection_update_last_outreach(date '2026-01-01', 'test company', null)$$,
  '22023',
  'last_outreach_date cannot be cleared while outreach status is outbound',
  'outbound date cannot be cleared'
);

select throws_ok(
  $$select public.inspection_update_last_outreach(date '2026-01-01', 'test company', current_date + 1)$$,
  '22023',
  'last_outreach_date cannot be in the future',
  'future outbound dates are rejected'
);

select is(
  public.inspection_update_notes(
    date '2026-01-01',
    'test company',
    'Updated note',
    'Updated history'
  ) ->> 'outreach_status',
  'message_sent',
  'notes RPC preserves outreach status'
);

select is(
  public.inspection_update_notes(
    date '2026-01-01',
    'test company',
    'Updated note',
    'Updated history'
  ) ->> 'last_outreach_date',
  current_date::text,
  'notes RPC preserves Last Outreach'
);

select is(
  public.inspection_update_status(
    date '2026-01-01',
    'test company',
    'possible_fit',
    'active_conversation'
  ) ->> 'last_updated_by',
  'reviewer@example.com',
  'reviewer identity comes from the authenticated email'
);

select is(
  public.inspection_update_last_outreach(
    date '2026-01-01',
    'test company',
    null
  ) ->> 'last_outreach_date',
  null,
  'Last Outreach can be cleared after leaving an outbound status'
);

select is(
  public.inspection_update_star(date '2026-01-01', 'test company', false) ->> 'is_starred',
  'false',
  'star RPC unmarks the company'
);

select throws_ok(
  $$select public.inspection_update_star(date '2026-01-01', 'test company', null)$$,
  '22023',
  'is_starred is required',
  'star RPC rejects null state'
);

select throws_ok(
  $$select public.inspection_update_star(date '2026-01-01', 'missing company', true)$$,
  'P0002',
  'Inspection company not found',
  'star RPC rejects unknown companies'
);

select * from finish();

rollback;
