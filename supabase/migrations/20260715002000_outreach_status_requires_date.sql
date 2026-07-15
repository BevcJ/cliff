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

  if p_outreach_status in ('message_sent', 'follow_up_sent') then
    raise exception 'last_outreach_date is required for outbound outreach statuses' using errcode = '22023';
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

create or replace function public.inspection_update_status_with_last_outreach(
  p_collection_date date,
  p_company_key text,
  p_fit_status text,
  p_outreach_status text,
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

  if coalesce(p_fit_status, '') not in ('unreviewed', 'best_fit', 'possible_fit', 'not_interesting') then
    raise exception 'Invalid fit_status' using errcode = '22023';
  end if;

  if coalesce(p_outreach_status, '') not in ('message_sent', 'follow_up_sent') then
    raise exception 'Invalid outreach_status for Last Outreach update' using errcode = '22023';
  end if;

  if p_last_outreach_date is null then
    raise exception 'last_outreach_date is required for outbound outreach statuses' using errcode = '22023';
  end if;

  if p_last_outreach_date > current_date then
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
    p_last_outreach_date,
    case when p_fit_status <> 'unreviewed' then now() else null end,
    p_collection_date,
    now(),
    v_reviewer
  )
  on conflict (company_key) do update set
    company = excluded.company,
    fit_status = excluded.fit_status,
    outreach_status = excluded.outreach_status,
    last_outreach_date = excluded.last_outreach_date,
    inspected_at = coalesce(public.company_review_state.inspected_at, excluded.inspected_at),
    last_seen_collection_date = excluded.last_seen_collection_date,
    last_updated_at = now(),
    last_updated_by = excluded.last_updated_by
  returning * into v_row;

  return public.inspection_review_json(v_row);
end;
$$;

revoke execute on function public.inspection_update_status_with_last_outreach(date, text, text, text, date) from public, anon;
grant execute on function public.inspection_update_status_with_last_outreach(date, text, text, text, date) to authenticated;
