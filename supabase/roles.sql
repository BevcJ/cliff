do $$
begin
  if not exists (
    select 1
    from pg_catalog.pg_roles
    where rolname = 'app_inspection_user'
  ) then
    create role app_inspection_user with login noinherit;
  end if;
end
$$;

alter role app_inspection_user with
  login
  noinherit;

comment on role app_inspection_user is
  'Server-only producer for AI Hiring Radar inspection snapshots. Password is managed outside source control.';
