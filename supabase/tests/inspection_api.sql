begin;

select plan(22);

select is(public.inspection_workflow('unreviewed', 'not_started'), 'inspect', 'unreviewed companies remain in Inspect');
select is(public.inspection_workflow('best_fit', 'not_started'), 'shortlist', 'suitable not-started companies enter Shortlist');
select is(public.inspection_workflow('possible_fit', 'message_sent'), 'outreach', 'sent suitable companies enter Outreach');
select is(public.inspection_workflow('best_fit', 'closed'), 'closed', 'Closed takes precedence');
select is(public.inspection_workflow('not_interesting', 'closed'), 'closed', 'Closed beats rejected fit');
select is(public.inspection_workflow('best_fit', 'lost_no_response'), 'rejected', 'lost outreach is rejected');
select is(public.inspection_workflow('not_interesting', 'not_started'), 'rejected', 'rejected fit is rejected');

select is(public.inspection_follow_up_status('message_sent', current_date), 'fresh', 'same-day outreach is fresh');
select is(public.inspection_follow_up_status('message_sent', current_date - 4), 'due_soon', 'four-day outreach is due soon');
select is(public.inspection_follow_up_status('follow_up_sent', current_date - 6), 'follow_up', 'six-day follow-up needs action');
select is(public.inspection_follow_up_status('message_sent', null), 'date_missing', 'active outreach without date is flagged');
select is(public.inspection_follow_up_status('closed', current_date - 20), '', 'closed outreach suppresses follow-up');

select ok(public.inspection_matches_text_array(array['remote'], array['remote']), 'array filters match overlap');
select ok(public.inspection_matches_text_value(null, array['__missing__']), 'scalar filters match missing sentinel');

insert into public.inspection_collections (
  collection_date,
  source_kind,
  snapshot_count,
  job_count
) values
  (date '2026-01-01', 'test', 2, 2),
  (date '2026-01-02', 'test', 1, 1);

insert into public.inspection_company_snapshots (
  collection_date,
  company_key,
  company,
  job_count,
  summary_payload,
  detail_payload
) values
  (
    date '2026-01-01',
    'test company',
    'Test Company',
    1,
    '{"company":"Test Company","company_key":"test company"}'::jsonb,
    '{"company":"Test Company","company_key":"test company","jobs":[]}'::jsonb
  ),
  (
    date '2026-01-01',
    'other company',
    'Other Company',
    1,
    '{"company":"Other Company","company_key":"other company"}'::jsonb,
    '{"company":"Other Company","company_key":"other company","jobs":[]}'::jsonb
  ),
  (
    date '2026-01-02',
    'test company',
    'Test Company',
    1,
    '{"company":"Test Company","company_key":"test company"}'::jsonb,
    '{"company":"Test Company","company_key":"test company","jobs":[]}'::jsonb
  );

set local role authenticated;
select set_config(
  'request.jwt.claims',
  '{"sub":"00000000-0000-4000-8000-000000000001","email":"reviewer@example.com","role":"authenticated"}',
  true
);

select is(
  jsonb_typeof(public.inspection_list_companies(date '2026-01-01') #> '{rows,0,is_starred}'),
  'boolean',
  'company list exposes boolean star state'
);

select is(
  public.inspection_get_company(date '2026-01-01', 'test company') ->> 'is_starred',
  'false',
  'company detail defaults to unstarred without review state'
);

select is(
  public.inspection_update_star(date '2026-01-01', 'test company', true) ->> 'is_starred',
  'true',
  'company can be starred through the authenticated RPC'
);

select is(
  public.inspection_get_company(date '2026-01-01', 'test company') ->> 'last_reviewed_at',
  null,
  'a star-only company has no review timestamp'
);

select is(
  public.inspection_list_companies(date '2026-01-01') ->> 'total',
  '2',
  'inactive star filter keeps all matching companies'
);

select is(
  public.inspection_list_companies(date '2026-01-01', '{"starred_only":true}'::jsonb) ->> 'total',
  '1',
  'Starred-only list filter keeps marked companies'
);

select is(
  public.inspection_get_counts(date '2026-01-01', '{"starred_only":true}'::jsonb) ->> 'total_companies',
  '1',
  'Starred-only filter applies to inspection counts'
);

select is(
  public.inspection_get_company(date '2026-01-02', 'test company') ->> 'is_starred',
  'true',
  'company stars are shared across collection dates'
);

select * from finish();

rollback;
