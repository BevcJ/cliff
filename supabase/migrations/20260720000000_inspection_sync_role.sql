do $$
begin
  if not exists (
    select 1
    from pg_catalog.pg_roles
    where rolname = 'app_inspection_user'
  ) then
    raise exception 'app_inspection_user is missing; apply supabase/roles.sql before this migration';
  end if;

  if exists (
    select 1
    from pg_catalog.pg_roles
    where rolname = 'app_inspection_user'
      and (
        not rolcanlogin
        or rolinherit
        or rolsuper
        or rolcreatedb
        or rolcreaterole
        or rolreplication
        or rolbypassrls
      )
  ) then
    raise exception 'app_inspection_user has unsafe role attributes';
  end if;

  if exists (
    select 1
    from pg_catalog.pg_auth_members
    where member = (
      select oid
      from pg_catalog.pg_roles
      where rolname = 'app_inspection_user'
    )
  ) then
    raise exception 'app_inspection_user must not inherit or assume other roles';
  end if;
end
$$;

revoke all privileges
  on table public.inspection_collections
  from app_inspection_user;

revoke all privileges
  on table public.inspection_company_snapshots
  from app_inspection_user;

revoke all privileges
  on table public.company_review_state
  from app_inspection_user;

grant usage
  on schema public
  to app_inspection_user;

grant insert, delete
  on table public.inspection_collections
  to app_inspection_user;

grant select (collection_date)
  on table public.inspection_collections
  to app_inspection_user;

grant insert
  on table public.inspection_company_snapshots
  to app_inspection_user;

create policy inspection_collections_sync_select
  on public.inspection_collections
  for select
  to app_inspection_user
  using (true);

create policy inspection_collections_sync_insert
  on public.inspection_collections
  for insert
  to app_inspection_user
  with check (true);

create policy inspection_collections_sync_delete
  on public.inspection_collections
  for delete
  to app_inspection_user
  using (true);

create policy inspection_company_snapshots_sync_insert
  on public.inspection_company_snapshots
  for insert
  to app_inspection_user
  with check (true);
