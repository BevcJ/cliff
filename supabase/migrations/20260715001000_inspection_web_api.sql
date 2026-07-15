alter table public.inspection_collections enable row level security;
alter table public.inspection_company_snapshots enable row level security;
alter table public.company_review_state enable row level security;

revoke all on table public.inspection_collections from anon, authenticated;
revoke all on table public.inspection_company_snapshots from anon, authenticated;
revoke all on table public.company_review_state from anon, authenticated;

grant usage on schema public to authenticated;

create or replace function public.inspection_require_auth()
returns uuid
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_user_id uuid;
begin
  v_user_id := auth.uid();
  if v_user_id is null then
    raise exception 'Authentication required' using errcode = '28000';
  end if;
  return v_user_id;
end;
$$;

create or replace function public.inspection_reviewer_label()
returns text
language sql
stable
security definer
set search_path = ''
as $$
  select coalesce(nullif(auth.jwt() ->> 'email', ''), auth.uid()::text)
$$;

create or replace function public.inspection_filter_values(p_filters jsonb, p_key text)
returns text[]
language plpgsql
stable
set search_path = ''
as $$
declare
  v_value jsonb;
  v_values text[];
begin
  v_value := coalesce(p_filters -> p_key, '[]'::jsonb);
  if jsonb_typeof(v_value) <> 'array' then
    return '{}'::text[];
  end if;

  select coalesce(array_agg(value order by value), '{}'::text[])
  into v_values
  from jsonb_array_elements_text(v_value) as j(value)
  where btrim(value) <> '';

  return coalesce(v_values, '{}'::text[]);
end;
$$;

create or replace function public.inspection_filter_text(p_filters jsonb, p_key text)
returns text
language sql
stable
set search_path = ''
as $$
  select btrim(coalesce(p_filters ->> p_key, ''))
$$;

create or replace function public.inspection_matches_text_array(p_values text[], p_filters text[])
returns boolean
language plpgsql
immutable
set search_path = ''
as $$
declare
  v_values text[] := coalesce(p_values, '{}'::text[]);
  v_filters text[] := coalesce(p_filters, '{}'::text[]);
  v_non_missing text[] := array_remove(coalesce(p_filters, '{}'::text[]), '__missing__');
begin
  if cardinality(v_filters) = 0 then
    return true;
  end if;

  return (
    (cardinality(v_non_missing) > 0 and v_values && v_non_missing)
    or ('__missing__' = any(v_filters) and cardinality(v_values) = 0)
  );
end;
$$;

create or replace function public.inspection_matches_text_value(p_value text, p_filters text[])
returns boolean
language plpgsql
immutable
set search_path = ''
as $$
declare
  v_value text := nullif(btrim(coalesce(p_value, '')), '');
  v_filters text[] := coalesce(p_filters, '{}'::text[]);
  v_non_missing text[] := array_remove(coalesce(p_filters, '{}'::text[]), '__missing__');
begin
  if cardinality(v_filters) = 0 then
    return true;
  end if;

  return (
    (cardinality(v_non_missing) > 0 and v_value = any(v_non_missing))
    or ('__missing__' = any(v_filters) and v_value is null)
  );
end;
$$;

create or replace function public.inspection_normalize_outreach_status(p_status text)
returns text
language sql
immutable
set search_path = ''
as $$
  select case coalesce(p_status, '')
    when 'follow_up_needed' then 'follow_up_sent'
    when 'replied' then 'active_conversation'
    when '' then 'not_started'
    else p_status
  end
$$;

create or replace function public.inspection_workflow(p_fit_status text, p_outreach_status text)
returns text
language sql
immutable
set search_path = ''
as $$
  select case
    when public.inspection_normalize_outreach_status(p_outreach_status) = 'closed'
      then 'closed'
    when public.inspection_normalize_outreach_status(p_outreach_status) in ('lost_client_rejection', 'lost_no_response')
      or coalesce(p_fit_status, 'unreviewed') = 'not_interesting'
      then 'rejected'
    when coalesce(p_fit_status, 'unreviewed') in ('best_fit', 'possible_fit')
      and public.inspection_normalize_outreach_status(p_outreach_status) in ('message_sent', 'follow_up_sent', 'active_conversation')
      then 'outreach'
    when coalesce(p_fit_status, 'unreviewed') in ('best_fit', 'possible_fit')
      and public.inspection_normalize_outreach_status(p_outreach_status) = 'not_started'
      then 'shortlist'
    else 'inspect'
  end
$$;

create or replace function public.inspection_follow_up_status(p_outreach_status text, p_last_outreach_date date)
returns text
language plpgsql
stable
set search_path = ''
as $$
declare
  v_days integer;
  v_status text := public.inspection_normalize_outreach_status(p_outreach_status);
begin
  if v_status not in ('message_sent', 'follow_up_sent') then
    return '';
  end if;

  if p_last_outreach_date is null then
    return 'date_missing';
  end if;

  v_days := current_date - p_last_outreach_date;
  if v_days < 0 then
    return 'invalid_date';
  elsif v_days <= 3 then
    return 'fresh';
  elsif v_days <= 5 then
    return 'due_soon';
  end if;

  return 'follow_up';
end;
$$;

create or replace function public.inspection_company_size_rank(p_company_size text)
returns integer
language sql
immutable
set search_path = ''
as $$
  select case p_company_size
    when '0-50' then 1
    when '51-100' then 2
    when '101-500' then 3
    when '501+' then 4
    else 100
  end
$$;

create or replace function public.inspection_review_json(p_state public.company_review_state)
returns jsonb
language sql
stable
set search_path = ''
as $$
  select jsonb_build_object(
    'company_key', p_state.company_key,
    'company', p_state.company,
    'fit_status', coalesce(p_state.fit_status, 'unreviewed'),
    'outreach_status', public.inspection_normalize_outreach_status(p_state.outreach_status),
    'notes', coalesce(p_state.notes, ''),
    'communication_history', coalesce(p_state.communication_history, ''),
    'last_outreach_date', p_state.last_outreach_date,
    'inspected_at', p_state.inspected_at,
    'last_seen_collection_date', p_state.last_seen_collection_date,
    'created_at', p_state.created_at,
    'last_updated_at', p_state.last_updated_at,
    'last_updated_by', p_state.last_updated_by
  )
$$;

create or replace function public.inspection_company_matches_filters(
  p_snapshot public.inspection_company_snapshots,
  p_fit_status text,
  p_outreach_status text,
  p_filters jsonb
)
returns boolean
language plpgsql
stable
set search_path = ''
as $$
declare
  v_filters jsonb := coalesce(p_filters, '{}'::jsonb);
  v_min_jobs integer;
  v_max_jobs integer;
  v_search text;
begin
  v_min_jobs := nullif(public.inspection_filter_text(v_filters, 'min_jobs'), '')::integer;
  v_max_jobs := nullif(public.inspection_filter_text(v_filters, 'max_jobs'), '')::integer;
  v_search := lower(public.inspection_filter_text(v_filters, 'search'));

  return public.inspection_matches_text_array(
      p_snapshot.workplace_modes,
      public.inspection_filter_values(v_filters, 'workplace_modes')
    )
    and public.inspection_matches_text_array(
      p_snapshot.ai_team_contexts,
      public.inspection_filter_values(v_filters, 'ai_team_contexts')
    )
    and public.inspection_matches_text_array(
      p_snapshot.delivery_contexts,
      public.inspection_filter_values(v_filters, 'delivery_contexts')
    )
    and public.inspection_matches_text_value(
      p_snapshot.company_type,
      public.inspection_filter_values(v_filters, 'company_types')
    )
    and public.inspection_matches_text_value(
      p_snapshot.company_size,
      public.inspection_filter_values(v_filters, 'company_sizes')
    )
    and public.inspection_matches_text_array(
      p_snapshot.countries,
      public.inspection_filter_values(v_filters, 'countries')
    )
    and public.inspection_matches_text_value(
      p_snapshot.role_classification,
      public.inspection_filter_values(v_filters, 'role_classifications')
    )
    and public.inspection_matches_text_array(
      p_snapshot.sources,
      public.inspection_filter_values(v_filters, 'sources')
    )
    and public.inspection_matches_text_value(
      p_snapshot.ai_tech_forward_signal,
      public.inspection_filter_values(v_filters, 'ai_tech_forward_signals')
    )
    and public.inspection_matches_text_value(
      p_fit_status,
      public.inspection_filter_values(v_filters, 'fit_statuses')
    )
    and public.inspection_matches_text_value(
      p_outreach_status,
      public.inspection_filter_values(v_filters, 'outreach_statuses')
    )
    and (v_min_jobs is null or p_snapshot.job_count >= v_min_jobs)
    and (v_max_jobs is null or p_snapshot.job_count <= v_max_jobs)
    and (
      v_filters -> 'has_contacts' is null
      or jsonb_typeof(v_filters -> 'has_contacts') <> 'boolean'
      or p_snapshot.has_contacts = (v_filters ->> 'has_contacts')::boolean
    )
    and (
      v_filters -> 'has_job_description_extracts' is null
      or jsonb_typeof(v_filters -> 'has_job_description_extracts') <> 'boolean'
      or p_snapshot.has_job_description_extracts = (v_filters ->> 'has_job_description_extracts')::boolean
    )
    and (
      v_filters -> 'has_company_enrichment' is null
      or jsonb_typeof(v_filters -> 'has_company_enrichment') <> 'boolean'
      or p_snapshot.has_company_enrichment = (v_filters ->> 'has_company_enrichment')::boolean
    )
    and (
      v_search = ''
      or lower(p_snapshot.search_text) like '%' || v_search || '%'
    );
end;
$$;

create or replace function public.inspection_list_collections()
returns table (
  collection_date date,
  snapshot_count integer,
  job_count integer,
  synced_at timestamptz
)
language sql
stable
security definer
set search_path = ''
as $$
  with _auth as materialized (select public.inspection_require_auth())
  select
    c.collection_date,
    c.snapshot_count,
    c.job_count,
    c.synced_at
  from public.inspection_collections c, _auth
  order by c.collection_date desc;
$$;

create or replace function public.inspection_get_filter_options(p_collection_date date)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  with _auth as materialized (
    select public.inspection_require_auth()
  ), rows as (
    select *
    from public.inspection_company_snapshots
    where collection_date = p_collection_date
  )
  select jsonb_build_object(
    'workplace_modes', coalesce((
      select jsonb_agg(value order by value)
      from (select distinct value from rows r cross join lateral unnest(r.workplace_modes) as u(value)) x
    ), '[]'::jsonb),
    'has_missing_workplace_modes', coalesce((select bool_or(cardinality(workplace_modes) = 0) from rows), false),
    'ai_team_contexts', coalesce((
      select jsonb_agg(value order by value)
      from (select distinct value from rows r cross join lateral unnest(r.ai_team_contexts) as u(value)) x
    ), '[]'::jsonb),
    'has_missing_ai_team_contexts', coalesce((select bool_or(cardinality(ai_team_contexts) = 0) from rows), false),
    'delivery_contexts', coalesce((
      select jsonb_agg(value order by value)
      from (select distinct value from rows r cross join lateral unnest(r.delivery_contexts) as u(value)) x
    ), '[]'::jsonb),
    'has_missing_delivery_contexts', coalesce((select bool_or(cardinality(delivery_contexts) = 0) from rows), false),
    'company_types', coalesce((
      select jsonb_agg(value order by value)
      from (select distinct company_type as value from rows where nullif(company_type, '') is not null) x
    ), '[]'::jsonb),
    'has_missing_company_types', coalesce((select bool_or(nullif(company_type, '') is null) from rows), false),
    'company_sizes', coalesce((
      select jsonb_agg(value order by public.inspection_company_size_rank(value), value)
      from (select distinct company_size as value from rows where nullif(company_size, '') is not null) x
    ), '[]'::jsonb),
    'has_missing_company_sizes', coalesce((select bool_or(nullif(company_size, '') is null) from rows), false),
    'countries', coalesce((
      select jsonb_agg(value order by value)
      from (select distinct value from rows r cross join lateral unnest(r.countries) as u(value)) x
    ), '[]'::jsonb),
    'has_missing_countries', coalesce((select bool_or(cardinality(countries) = 0) from rows), false),
    'role_classifications', coalesce((
      select jsonb_agg(value order by value)
      from (select distinct role_classification as value from rows where nullif(role_classification, '') is not null) x
    ), '[]'::jsonb),
    'has_missing_role_classifications', coalesce((select bool_or(nullif(role_classification, '') is null) from rows), false),
    'sources', coalesce((
      select jsonb_agg(value order by value)
      from (select distinct value from rows r cross join lateral unnest(r.sources) as u(value)) x
    ), '[]'::jsonb),
    'has_missing_sources', coalesce((select bool_or(cardinality(sources) = 0) from rows), false),
    'ai_tech_forward_signals', coalesce((
      select jsonb_agg(value order by value)
      from (select distinct ai_tech_forward_signal as value from rows where nullif(ai_tech_forward_signal, '') is not null) x
    ), '[]'::jsonb),
    'has_missing_ai_tech_forward_signals', coalesce((select bool_or(nullif(ai_tech_forward_signal, '') is null) from rows), false)
  ) from _auth;
$$;

create or replace function public.inspection_get_counts(
  p_collection_date date,
  p_filters jsonb default '{}'::jsonb
)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  with _auth as materialized (
    select public.inspection_require_auth()
  ), base as (
    select
      s as snapshot,
      s.*,
      coalesce(rs.fit_status, 'unreviewed') as fit_status,
      public.inspection_normalize_outreach_status(coalesce(rs.outreach_status, 'not_started')) as outreach_status,
      rs.last_outreach_date,
      public.inspection_workflow(coalesce(rs.fit_status, 'unreviewed'), coalesce(rs.outreach_status, 'not_started')) as workflow
    from public.inspection_company_snapshots s
    left join public.company_review_state rs on rs.company_key = s.company_key
    where s.collection_date = p_collection_date
  ), filtered as (
    select *
    from base
    where public.inspection_company_matches_filters(snapshot, fit_status, outreach_status, p_filters)
  )
  select jsonb_build_object(
    'total_companies', count(*),
    'total_jobs', coalesce(sum(job_count), 0),
    'total_job_description_extracts', coalesce(sum(job_description_extract_count), 0),
    'with_contacts', count(*) filter (where has_contacts),
    'with_job_description_extracts', count(*) filter (where has_job_description_extracts),
    'with_company_enrichment', count(*) filter (where has_company_enrichment),
    'workflows', jsonb_build_object(
      'inspect', count(*) filter (where workflow = 'inspect'),
      'shortlist', count(*) filter (where workflow = 'shortlist'),
      'outreach', count(*) filter (where workflow = 'outreach'),
      'closed', count(*) filter (where workflow = 'closed'),
      'rejected', count(*) filter (where workflow = 'rejected')
    ),
    'fit_statuses', jsonb_build_object(
      'unreviewed', count(*) filter (where fit_status = 'unreviewed'),
      'best_fit', count(*) filter (where fit_status = 'best_fit'),
      'possible_fit', count(*) filter (where fit_status = 'possible_fit'),
      'not_interesting', count(*) filter (where fit_status = 'not_interesting')
    ),
    'outreach_statuses', jsonb_build_object(
      'not_started', count(*) filter (where outreach_status = 'not_started'),
      'message_sent', count(*) filter (where outreach_status = 'message_sent'),
      'follow_up_sent', count(*) filter (where outreach_status = 'follow_up_sent'),
      'active_conversation', count(*) filter (where outreach_status = 'active_conversation'),
      'closed', count(*) filter (where outreach_status = 'closed'),
      'lost_client_rejection', count(*) filter (where outreach_status = 'lost_client_rejection'),
      'lost_no_response', count(*) filter (where outreach_status = 'lost_no_response')
    )
  )
  from filtered, _auth;
$$;

create or replace function public.inspection_list_companies(
  p_collection_date date,
  p_filters jsonb default '{}'::jsonb,
  p_workflow text default 'inspect',
  p_sort_field text default 'job_description_extract_count',
  p_sort_direction text default 'desc',
  p_page integer default 1,
  p_page_size integer default 50
)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_workflow text := lower(coalesce(p_workflow, 'inspect'));
  v_sort_field text := lower(coalesce(p_sort_field, 'job_description_extract_count'));
  v_sort_direction text := lower(coalesce(p_sort_direction, 'desc'));
  v_page integer := greatest(coalesce(p_page, 1), 1);
  v_page_size integer := least(greatest(coalesce(p_page_size, 50), 1), 100);
begin
  perform public.inspection_require_auth();

  if v_workflow not in ('inspect', 'shortlist', 'outreach', 'closed', 'rejected') then
    v_workflow := 'inspect';
  end if;

  if v_sort_field not in (
    'job_description_extract_count',
    'job_count',
    'company',
    'fit_status',
    'outreach_status',
    'company_type',
    'company_size',
    'ai_tech_forward_signal',
    'countries',
    'sources'
  ) then
    v_sort_field := 'job_description_extract_count';
  end if;

  if v_sort_direction not in ('asc', 'desc') then
    v_sort_direction := 'desc';
  end if;

  return (
    with base as (
      select
        s as snapshot,
        s.*,
        coalesce(rs.fit_status, 'unreviewed') as fit_status,
        public.inspection_normalize_outreach_status(coalesce(rs.outreach_status, 'not_started')) as outreach_status,
        rs.last_outreach_date,
        rs.company_key is not null as has_review_state,
        public.inspection_workflow(coalesce(rs.fit_status, 'unreviewed'), coalesce(rs.outreach_status, 'not_started')) as workflow
      from public.inspection_company_snapshots s
      left join public.company_review_state rs on rs.company_key = s.company_key
      where s.collection_date = p_collection_date
    ), filtered as (
      select *
      from base
      where workflow = v_workflow
        and public.inspection_company_matches_filters(snapshot, fit_status, outreach_status, p_filters)
    ), ordered as (
      select *
      from filtered
      order by
        case when v_sort_field = 'job_description_extract_count' and v_sort_direction = 'asc' then job_description_extract_count end asc,
        case when v_sort_field = 'job_description_extract_count' and v_sort_direction = 'desc' then job_description_extract_count end desc,
        case when v_sort_field = 'job_count' and v_sort_direction = 'asc' then job_count end asc,
        case when v_sort_field = 'job_count' and v_sort_direction = 'desc' then job_count end desc,
        case when v_sort_field = 'company' and v_sort_direction = 'asc' then lower(company) end asc,
        case when v_sort_field = 'company' and v_sort_direction = 'desc' then lower(company) end desc,
        case when v_sort_field = 'fit_status' and v_sort_direction = 'asc' then fit_status end asc,
        case when v_sort_field = 'fit_status' and v_sort_direction = 'desc' then fit_status end desc,
        case when v_sort_field = 'outreach_status' and v_sort_direction = 'asc' then outreach_status end asc,
        case when v_sort_field = 'outreach_status' and v_sort_direction = 'desc' then outreach_status end desc,
        case when v_sort_field = 'company_type' and v_sort_direction = 'asc' then company_type end asc nulls last,
        case when v_sort_field = 'company_type' and v_sort_direction = 'desc' then company_type end desc nulls last,
        case when v_sort_field = 'company_size' and v_sort_direction = 'asc' then public.inspection_company_size_rank(company_size) end asc,
        case when v_sort_field = 'company_size' and v_sort_direction = 'desc' then public.inspection_company_size_rank(company_size) end desc,
        case when v_sort_field = 'company_size' and v_sort_direction = 'asc' then company_size end asc nulls last,
        case when v_sort_field = 'company_size' and v_sort_direction = 'desc' then company_size end desc nulls last,
        case when v_sort_field = 'ai_tech_forward_signal' and v_sort_direction = 'asc' then ai_tech_forward_signal end asc nulls last,
        case when v_sort_field = 'ai_tech_forward_signal' and v_sort_direction = 'desc' then ai_tech_forward_signal end desc nulls last,
        case when v_sort_field = 'countries' and v_sort_direction = 'asc' then array_to_string(countries, ', ') end asc,
        case when v_sort_field = 'countries' and v_sort_direction = 'desc' then array_to_string(countries, ', ') end desc,
        case when v_sort_field = 'sources' and v_sort_direction = 'asc' then array_to_string(sources, ', ') end asc,
        case when v_sort_field = 'sources' and v_sort_direction = 'desc' then array_to_string(sources, ', ') end desc,
        lower(company) asc,
        company_key asc
    ), page_rows as (
      select *
      from ordered
      limit v_page_size
      offset (v_page - 1) * v_page_size
    )
    select jsonb_build_object(
      'page', v_page,
      'page_size', v_page_size,
      'total', (select count(*) from filtered),
      'rows', coalesce((
        select jsonb_agg(
          jsonb_build_object(
            'collection_date', collection_date,
            'company_key', company_key,
            'company', company,
            'countries', countries,
            'role_classification', role_classification,
            'sources', sources,
            'workplace_modes', workplace_modes,
            'ai_team_contexts', ai_team_contexts,
            'delivery_contexts', delivery_contexts,
            'company_type', company_type,
            'company_size', company_size,
            'ai_tech_forward_signal', ai_tech_forward_signal,
            'job_count', job_count,
            'job_description_extract_count', job_description_extract_count,
            'has_contacts', has_contacts,
            'has_job_description_extracts', has_job_description_extracts,
            'has_company_enrichment', has_company_enrichment,
            'fit_status', fit_status,
            'outreach_status', outreach_status,
            'last_outreach_date', last_outreach_date,
            'has_review_state', has_review_state,
            'workflow', workflow,
            'follow_up_status', public.inspection_follow_up_status(outreach_status, last_outreach_date)
          )
        )
        from page_rows
      ), '[]'::jsonb)
    )
  );
end;
$$;

create or replace function public.inspection_get_company(
  p_collection_date date,
  p_company_key text
)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_payload jsonb;
begin
  perform public.inspection_require_auth();

  select
    s.detail_payload || jsonb_build_object(
      'fit_status', coalesce(rs.fit_status, 'unreviewed'),
      'outreach_status', public.inspection_normalize_outreach_status(coalesce(rs.outreach_status, 'not_started')),
      'review_notes', coalesce(rs.notes, ''),
      'review_communication_history', coalesce(rs.communication_history, ''),
      'last_outreach_date', rs.last_outreach_date,
      'inspected_at', rs.inspected_at,
      'last_seen_collection_date', rs.last_seen_collection_date,
      'last_reviewed_at', rs.last_updated_at,
      'last_reviewed_by', rs.last_updated_by,
      'has_review_state', rs.company_key is not null,
      'workflow', public.inspection_workflow(coalesce(rs.fit_status, 'unreviewed'), coalesce(rs.outreach_status, 'not_started')),
      'follow_up_status', public.inspection_follow_up_status(coalesce(rs.outreach_status, 'not_started'), rs.last_outreach_date)
    )
  into v_payload
  from public.inspection_company_snapshots s
  left join public.company_review_state rs on rs.company_key = s.company_key
  where s.collection_date = p_collection_date
    and s.company_key = btrim(coalesce(p_company_key, ''));

  if v_payload is null then
    raise exception 'Inspection company not found' using errcode = 'P0002';
  end if;

  return v_payload;
end;
$$;

create or replace function public.inspection_update_status(
  p_collection_date date,
  p_company_key text,
  p_fit_status text,
  p_outreach_status text
)
returns jsonb
language plpgsql
volatile
security definer
set search_path = ''
as $$
declare
  v_company text;
  v_user_id uuid;
  v_reviewer text;
  v_row public.company_review_state;
begin
  v_user_id := public.inspection_require_auth();
  v_reviewer := public.inspection_reviewer_label();

  if coalesce(p_fit_status, '') not in ('unreviewed', 'best_fit', 'possible_fit', 'not_interesting') then
    raise exception 'Invalid fit_status' using errcode = '22023';
  end if;

  if coalesce(p_outreach_status, '') not in ('not_started', 'message_sent', 'follow_up_sent', 'active_conversation', 'closed', 'lost_client_rejection', 'lost_no_response') then
    raise exception 'Invalid outreach_status' using errcode = '22023';
  end if;

  select company into v_company
  from public.inspection_company_snapshots
  where collection_date = p_collection_date
    and company_key = btrim(coalesce(p_company_key, ''));

  if v_company is null then
    raise exception 'Inspection company not found' using errcode = 'P0002';
  end if;

  insert into public.company_review_state (
    company_key,
    company,
    fit_status,
    outreach_status,
    inspected_at,
    last_seen_collection_date,
    last_updated_at,
    last_updated_by
  ) values (
    btrim(p_company_key),
    v_company,
    p_fit_status,
    p_outreach_status,
    case when p_fit_status <> 'unreviewed' then now() else null end,
    p_collection_date,
    now(),
    v_reviewer
  )
  on conflict (company_key) do update set
    company = excluded.company,
    fit_status = excluded.fit_status,
    outreach_status = excluded.outreach_status,
    inspected_at = coalesce(public.company_review_state.inspected_at, excluded.inspected_at),
    last_seen_collection_date = excluded.last_seen_collection_date,
    last_updated_at = now(),
    last_updated_by = excluded.last_updated_by
  returning * into v_row;

  return public.inspection_review_json(v_row);
end;
$$;

create or replace function public.inspection_update_last_outreach(
  p_collection_date date,
  p_company_key text,
  p_last_outreach_date date
)
returns jsonb
language plpgsql
volatile
security definer
set search_path = ''
as $$
declare
  v_company text;
  v_reviewer text;
  v_row public.company_review_state;
begin
  perform public.inspection_require_auth();
  v_reviewer := public.inspection_reviewer_label();

  if p_last_outreach_date is not null and p_last_outreach_date > current_date then
    raise exception 'last_outreach_date cannot be in the future' using errcode = '22023';
  end if;

  select company into v_company
  from public.inspection_company_snapshots
  where collection_date = p_collection_date
    and company_key = btrim(coalesce(p_company_key, ''));

  if v_company is null then
    raise exception 'Inspection company not found' using errcode = 'P0002';
  end if;

  insert into public.company_review_state (
    company_key,
    company,
    last_outreach_date,
    last_seen_collection_date,
    last_updated_at,
    last_updated_by
  ) values (
    btrim(p_company_key),
    v_company,
    p_last_outreach_date,
    p_collection_date,
    now(),
    v_reviewer
  )
  on conflict (company_key) do update set
    company = excluded.company,
    last_outreach_date = excluded.last_outreach_date,
    last_seen_collection_date = excluded.last_seen_collection_date,
    last_updated_at = now(),
    last_updated_by = excluded.last_updated_by
  returning * into v_row;

  return public.inspection_review_json(v_row);
end;
$$;

create or replace function public.inspection_update_notes(
  p_collection_date date,
  p_company_key text,
  p_notes text,
  p_communication_history text
)
returns jsonb
language plpgsql
volatile
security definer
set search_path = ''
as $$
declare
  v_company text;
  v_reviewer text;
  v_row public.company_review_state;
begin
  perform public.inspection_require_auth();
  v_reviewer := public.inspection_reviewer_label();

  select company into v_company
  from public.inspection_company_snapshots
  where collection_date = p_collection_date
    and company_key = btrim(coalesce(p_company_key, ''));

  if v_company is null then
    raise exception 'Inspection company not found' using errcode = 'P0002';
  end if;

  insert into public.company_review_state (
    company_key,
    company,
    notes,
    communication_history,
    last_seen_collection_date,
    last_updated_at,
    last_updated_by
  ) values (
    btrim(p_company_key),
    v_company,
    btrim(coalesce(p_notes, '')),
    btrim(coalesce(p_communication_history, '')),
    p_collection_date,
    now(),
    v_reviewer
  )
  on conflict (company_key) do update set
    company = excluded.company,
    notes = excluded.notes,
    communication_history = excluded.communication_history,
    last_seen_collection_date = excluded.last_seen_collection_date,
    last_updated_at = now(),
    last_updated_by = excluded.last_updated_by
  returning * into v_row;

  return public.inspection_review_json(v_row);
end;
$$;

revoke execute on function public.inspection_require_auth() from public, anon, authenticated;
revoke execute on function public.inspection_reviewer_label() from public, anon, authenticated;
revoke execute on function public.inspection_filter_values(jsonb, text) from public, anon, authenticated;
revoke execute on function public.inspection_filter_text(jsonb, text) from public, anon, authenticated;
revoke execute on function public.inspection_matches_text_array(text[], text[]) from public, anon, authenticated;
revoke execute on function public.inspection_matches_text_value(text, text[]) from public, anon, authenticated;
revoke execute on function public.inspection_normalize_outreach_status(text) from public, anon, authenticated;
revoke execute on function public.inspection_workflow(text, text) from public, anon, authenticated;
revoke execute on function public.inspection_follow_up_status(text, date) from public, anon, authenticated;
revoke execute on function public.inspection_company_size_rank(text) from public, anon, authenticated;
revoke execute on function public.inspection_review_json(public.company_review_state) from public, anon, authenticated;
revoke execute on function public.inspection_company_matches_filters(public.inspection_company_snapshots, text, text, jsonb) from public, anon, authenticated;

revoke execute on function public.inspection_list_collections() from public, anon;
revoke execute on function public.inspection_get_filter_options(date) from public, anon;
revoke execute on function public.inspection_get_counts(date, jsonb) from public, anon;
revoke execute on function public.inspection_list_companies(date, jsonb, text, text, text, integer, integer) from public, anon;
revoke execute on function public.inspection_get_company(date, text) from public, anon;
revoke execute on function public.inspection_update_status(date, text, text, text) from public, anon;
revoke execute on function public.inspection_update_last_outreach(date, text, date) from public, anon;
revoke execute on function public.inspection_update_notes(date, text, text, text) from public, anon;

grant execute on function public.inspection_list_collections() to authenticated;
grant execute on function public.inspection_get_filter_options(date) to authenticated;
grant execute on function public.inspection_get_counts(date, jsonb) to authenticated;
grant execute on function public.inspection_list_companies(date, jsonb, text, text, text, integer, integer) to authenticated;
grant execute on function public.inspection_get_company(date, text) to authenticated;
grant execute on function public.inspection_update_status(date, text, text, text) to authenticated;
grant execute on function public.inspection_update_last_outreach(date, text, date) to authenticated;
grant execute on function public.inspection_update_notes(date, text, text, text) to authenticated;
