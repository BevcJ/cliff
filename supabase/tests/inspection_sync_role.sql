begin;

select plan(29);

select ok(
  exists (select 1 from pg_catalog.pg_roles where rolname = 'app_inspection_user'),
  'inspection sync role exists'
);
select ok(
  (select rolcanlogin from pg_catalog.pg_roles where rolname = 'app_inspection_user'),
  'inspection sync role can log in'
);
select ok(
  not (select rolinherit from pg_catalog.pg_roles where rolname = 'app_inspection_user'),
  'inspection sync role does not inherit privileges'
);
select ok(
  not (select rolsuper from pg_catalog.pg_roles where rolname = 'app_inspection_user'),
  'inspection sync role is not a superuser'
);
select ok(
  not (select rolcreatedb from pg_catalog.pg_roles where rolname = 'app_inspection_user'),
  'inspection sync role cannot create databases'
);
select ok(
  not (select rolcreaterole from pg_catalog.pg_roles where rolname = 'app_inspection_user'),
  'inspection sync role cannot create roles'
);
select ok(
  not (select rolreplication from pg_catalog.pg_roles where rolname = 'app_inspection_user'),
  'inspection sync role cannot replicate'
);
select ok(
  not (select rolbypassrls from pg_catalog.pg_roles where rolname = 'app_inspection_user'),
  'inspection sync role cannot bypass RLS'
);
select ok(
  not exists (
    select 1
    from pg_catalog.pg_auth_members
    where member = (
      select oid
      from pg_catalog.pg_roles
      where rolname = 'app_inspection_user'
    )
  ),
  'inspection sync role cannot assume another role'
);

select ok(
  has_schema_privilege('app_inspection_user', 'public', 'USAGE'),
  'inspection sync role can use the public schema'
);
select ok(
  has_table_privilege('app_inspection_user', 'public.inspection_collections', 'INSERT'),
  'inspection sync role can insert collections'
);
select ok(
  has_table_privilege('app_inspection_user', 'public.inspection_collections', 'DELETE'),
  'inspection sync role can delete collections'
);
select ok(
  has_column_privilege(
    'app_inspection_user',
    'public.inspection_collections',
    'collection_date',
    'SELECT'
  ),
  'inspection sync role can read collection dates for replacement deletes'
);
select ok(
  not has_table_privilege('app_inspection_user', 'public.inspection_collections', 'SELECT'),
  'inspection sync role cannot read complete collection rows'
);
select ok(
  not has_table_privilege('app_inspection_user', 'public.inspection_collections', 'UPDATE'),
  'inspection sync role cannot update collections'
);

select ok(
  has_table_privilege('app_inspection_user', 'public.inspection_company_snapshots', 'INSERT'),
  'inspection sync role can insert snapshots'
);
select ok(
  not has_table_privilege('app_inspection_user', 'public.inspection_company_snapshots', 'SELECT'),
  'inspection sync role cannot read snapshots directly'
);
select ok(
  not has_table_privilege('app_inspection_user', 'public.inspection_company_snapshots', 'UPDATE'),
  'inspection sync role cannot update snapshots'
);
select ok(
  not has_table_privilege('app_inspection_user', 'public.inspection_company_snapshots', 'DELETE'),
  'inspection sync role cannot delete snapshots directly'
);

select ok(
  not has_table_privilege('app_inspection_user', 'public.company_review_state', 'SELECT'),
  'inspection sync role cannot read review state'
);
select ok(
  not has_table_privilege('app_inspection_user', 'public.company_review_state', 'INSERT'),
  'inspection sync role cannot insert review state'
);
select ok(
  not has_table_privilege('app_inspection_user', 'public.company_review_state', 'UPDATE'),
  'inspection sync role cannot update review state'
);
select ok(
  not has_table_privilege('app_inspection_user', 'public.company_review_state', 'DELETE'),
  'inspection sync role cannot delete review state'
);

select is(
  (
    select count(*)::integer
    from pg_catalog.pg_policies
    where schemaname = 'public'
      and tablename in ('inspection_collections', 'inspection_company_snapshots')
      and 'app_inspection_user' = any(roles)
  ),
  4,
  'four sync policies apply to the inspection sync role'
);
select is(
  (
    select count(*)::integer
    from pg_catalog.pg_policies
    where schemaname = 'public'
      and tablename = 'company_review_state'
      and 'app_inspection_user' = any(roles)
  ),
  0,
  'no review-state policy applies to the inspection sync role'
);
select is(
  (
    select count(*)::integer
    from pg_catalog.pg_policies
    where schemaname = 'public'
      and tablename = 'inspection_collections'
      and cmd = 'SELECT'
      and qual = 'true'
      and 'app_inspection_user' = any(roles)
  ),
  1,
  'collection-date reads have an unrestricted sync policy'
);
select is(
  (
    select count(*)::integer
    from pg_catalog.pg_policies
    where schemaname = 'public'
      and tablename = 'inspection_collections'
      and cmd = 'INSERT'
      and with_check = 'true'
      and 'app_inspection_user' = any(roles)
  ),
  1,
  'collection inserts have an unrestricted sync check'
);
select is(
  (
    select count(*)::integer
    from pg_catalog.pg_policies
    where schemaname = 'public'
      and tablename = 'inspection_collections'
      and cmd = 'DELETE'
      and qual = 'true'
      and 'app_inspection_user' = any(roles)
  ),
  1,
  'collection deletes have an unrestricted sync policy'
);
select is(
  (
    select count(*)::integer
    from pg_catalog.pg_policies
    where schemaname = 'public'
      and tablename = 'inspection_company_snapshots'
      and cmd = 'INSERT'
      and with_check = 'true'
      and 'app_inspection_user' = any(roles)
  ),
  1,
  'snapshot inserts have an unrestricted sync check'
);

select * from finish();

rollback;
