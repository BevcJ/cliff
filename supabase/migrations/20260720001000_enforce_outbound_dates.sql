do $$
declare
  v_invalid_count integer;
begin
  select count(*)
  into v_invalid_count
  from public.company_review_state
  where outreach_status in ('message_sent', 'follow_up_sent')
    and last_outreach_date is null;

  if v_invalid_count > 0 then
    raise exception '% review row(s) have an outbound status without last_outreach_date; correct them before applying this migration', v_invalid_count;
  end if;
end;
$$;

alter table public.company_review_state
  drop constraint if exists company_review_state_outbound_date_check;

alter table public.company_review_state
  add constraint company_review_state_outbound_date_check
  check (
    outreach_status not in ('message_sent', 'follow_up_sent')
    or last_outreach_date is not null
  );

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
  v_existing_last_outreach_date date;
  v_reviewer text;
  v_row public.company_review_state;
begin
  perform public.inspection_require_auth();
  v_reviewer := public.inspection_reviewer_label();

  if coalesce(p_fit_status, '') not in ('unreviewed', 'best_fit', 'possible_fit', 'not_interesting') then
    raise exception 'Invalid fit_status' using errcode = '22023';
  end if;

  if coalesce(p_outreach_status, '') not in ('not_started', 'message_sent', 'follow_up_sent', 'active_conversation', 'closed', 'lost_client_rejection', 'lost_no_response') then
    raise exception 'Invalid outreach_status' using errcode = '22023';
  end if;

  select s.company, rs.last_outreach_date
  into v_company, v_existing_last_outreach_date
  from public.inspection_company_snapshots s
  left join public.company_review_state rs on rs.company_key = s.company_key
  where s.collection_date = p_collection_date
    and s.company_key = btrim(coalesce(p_company_key, ''));

  if v_company is null then
    raise exception 'Inspection company not found' using errcode = 'P0002';
  end if;

  if p_outreach_status in ('message_sent', 'follow_up_sent')
    and v_existing_last_outreach_date is null then
    raise exception 'last_outreach_date is required for outbound outreach statuses' using errcode = '22023';
  end if;

  insert into public.company_review_state (
    company_key,
    company,
    fit_status,
    outreach_status,
    last_outreach_date,
    inspected_at,
    last_seen_collection_date,
    last_updated_at,
    last_updated_by
  ) values (
    btrim(p_company_key),
    v_company,
    p_fit_status,
    p_outreach_status,
    v_existing_last_outreach_date,
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
  v_outreach_status text;
  v_reviewer text;
  v_row public.company_review_state;
begin
  perform public.inspection_require_auth();
  v_reviewer := public.inspection_reviewer_label();

  if p_last_outreach_date is not null and p_last_outreach_date > current_date then
    raise exception 'last_outreach_date cannot be in the future' using errcode = '22023';
  end if;

  select s.company, public.inspection_normalize_outreach_status(coalesce(rs.outreach_status, 'not_started'))
  into v_company, v_outreach_status
  from public.inspection_company_snapshots s
  left join public.company_review_state rs on rs.company_key = s.company_key
  where s.collection_date = p_collection_date
    and s.company_key = btrim(coalesce(p_company_key, ''));

  if v_company is null then
    raise exception 'Inspection company not found' using errcode = 'P0002';
  end if;

  if p_last_outreach_date is null
    and v_outreach_status in ('message_sent', 'follow_up_sent') then
    raise exception 'last_outreach_date cannot be cleared while outreach status is outbound' using errcode = '22023';
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
