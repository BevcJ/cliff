alter table public.inspection_company_snapshots
  add column if not exists role_groups text[] not null default '{}';

comment on column public.inspection_company_snapshots.role_groups is
  'Ordered unique job role groups observed for the company in this collection.';

create index if not exists inspection_company_snapshots_role_groups_gin_idx
  on public.inspection_company_snapshots using gin (role_groups);
