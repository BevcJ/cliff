alter table public.company_review_state
  add column if not exists is_starred boolean not null default false;

comment on column public.company_review_state.is_starred is
  'Shared marker for companies reviewers want to revisit across inspection collections.';

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
    'is_starred', coalesce(p_state.is_starred, false),
    'inspected_at', p_state.inspected_at,
    'last_seen_collection_date', p_state.last_seen_collection_date,
    'created_at', p_state.created_at,
    'last_updated_at', case
      when p_state.inspected_at is null
        and coalesce(p_state.fit_status, 'unreviewed') = 'unreviewed'
        and public.inspection_normalize_outreach_status(p_state.outreach_status) = 'not_started'
        and btrim(coalesce(p_state.notes, '')) = ''
        and btrim(coalesce(p_state.communication_history, '')) = ''
        and p_state.last_outreach_date is null
        and p_state.last_updated_by is null
      then null
      else p_state.last_updated_at
    end,
    'last_updated_by', p_state.last_updated_by
  )
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
      coalesce(rs.is_starred, false) as is_starred,
      public.inspection_workflow(coalesce(rs.fit_status, 'unreviewed'), coalesce(rs.outreach_status, 'not_started')) as workflow
    from public.inspection_company_snapshots s
    left join public.company_review_state rs on rs.company_key = s.company_key
    where s.collection_date = p_collection_date
  ), filtered as (
    select *
    from base
    where public.inspection_company_matches_filters(snapshot, fit_status, outreach_status, p_filters)
      and (
        not (coalesce(p_filters, '{}'::jsonb) @> '{"starred_only": true}'::jsonb)
        or is_starred
      )
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
        coalesce(rs.is_starred, false) as is_starred,
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
        and (
          not (coalesce(p_filters, '{}'::jsonb) @> '{"starred_only": true}'::jsonb)
          or is_starred
        )
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
            'is_starred', is_starred,
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
      'is_starred', coalesce(rs.is_starred, false),
      'inspected_at', rs.inspected_at,
      'last_seen_collection_date', rs.last_seen_collection_date,
      'last_reviewed_at', case
        when rs.inspected_at is null
          and coalesce(rs.fit_status, 'unreviewed') = 'unreviewed'
          and public.inspection_normalize_outreach_status(rs.outreach_status) = 'not_started'
          and btrim(coalesce(rs.notes, '')) = ''
          and btrim(coalesce(rs.communication_history, '')) = ''
          and rs.last_outreach_date is null
          and rs.last_updated_by is null
        then null
        else rs.last_updated_at
      end,
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

create or replace function public.inspection_update_star(
  p_collection_date date,
  p_company_key text,
  p_is_starred boolean
)
returns jsonb
language plpgsql
volatile
security definer
set search_path = ''
as $$
declare
  v_company text;
  v_row public.company_review_state;
begin
  perform public.inspection_require_auth();

  if p_is_starred is null then
    raise exception 'is_starred is required' using errcode = '22023';
  end if;

  select company into v_company
  from public.inspection_company_snapshots
  where collection_date = p_collection_date
    and company_key = btrim(coalesce(p_company_key, ''));

  if v_company is null then
    raise exception 'Inspection company not found' using errcode = 'P0002';
  end if;

  -- A star is a navigation aid, not a review action, so review audit fields stay unchanged.
  insert into public.company_review_state (
    company_key,
    company,
    is_starred
  ) values (
    btrim(p_company_key),
    v_company,
    p_is_starred
  )
  on conflict (company_key) do update set
    company = excluded.company,
    is_starred = excluded.is_starred
  returning * into v_row;

  return public.inspection_review_json(v_row);
end;
$$;

revoke execute on function public.inspection_update_star(date, text, boolean) from public, anon;
grant execute on function public.inspection_update_star(date, text, boolean) to authenticated;
