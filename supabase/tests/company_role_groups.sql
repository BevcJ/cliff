begin;

select plan(6);

select has_column(
  'public',
  'inspection_company_snapshots',
  'role_groups',
  'inspection snapshots store company role groups'
);

select col_type_is(
  'public',
  'inspection_company_snapshots',
  'role_groups',
  'text[]',
  'company role groups use a text array'
);

select ok(
  (
    select attribute.attnotnull
      and pg_catalog.pg_get_expr(default_value.adbin, default_value.adrelid) = '''{}''::text[]'
    from pg_catalog.pg_attribute as attribute
    join pg_catalog.pg_class as relation on relation.oid = attribute.attrelid
    join pg_catalog.pg_namespace as namespace on namespace.oid = relation.relnamespace
    left join pg_catalog.pg_attrdef as default_value
      on default_value.adrelid = relation.oid
      and default_value.adnum = attribute.attnum
    where namespace.nspname = 'public'
      and relation.relname = 'inspection_company_snapshots'
      and attribute.attname = 'role_groups'
      and not attribute.attisdropped
  ),
  'company role groups are non-null with an empty-array default'
);

select ok(
  exists (
    select 1
    from pg_catalog.pg_class as index_relation
    join pg_catalog.pg_namespace as namespace
      on namespace.oid = index_relation.relnamespace
    join pg_catalog.pg_index as index_definition
      on index_definition.indexrelid = index_relation.oid
    join pg_catalog.pg_am as access_method
      on access_method.oid = index_relation.relam
    where namespace.nspname = 'public'
      and index_relation.relname = 'inspection_company_snapshots_role_groups_gin_idx'
      and access_method.amname = 'gin'
      and index_definition.indrelid = 'public.inspection_company_snapshots'::regclass
  ),
  'company role groups have a GIN index'
);

insert into public.inspection_collections (
  collection_date,
  source_kind,
  snapshot_count,
  job_count,
  sync_summary
) values (
  '2026-07-29',
  'jsonl',
  1,
  1,
  '{}'::jsonb
);

insert into public.inspection_company_snapshots (
  collection_date,
  company_key,
  company,
  role_groups,
  summary_payload,
  detail_payload
) values (
  '2026-07-29',
  'acme-ai',
  'Acme AI',
  array['Data Science Role', 'Machine Learning Role'],
  '{}'::jsonb,
  '{}'::jsonb
);

select is(
  (
    select role_groups
    from public.inspection_company_snapshots
    where collection_date = '2026-07-29'
      and company_key = 'acme-ai'
  ),
  array['Data Science Role', 'Machine Learning Role'],
  'inspection snapshots retain populated role groups'
);

delete from public.inspection_collections where collection_date = '2026-07-29';

select is(
  (
    select count(*)::integer
    from public.inspection_company_snapshots
    where collection_date = '2026-07-29'
  ),
  0,
  'collection replacement deletes prior role-group snapshots by cascade'
);

select * from finish();

rollback;
