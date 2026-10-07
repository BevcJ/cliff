-- Read-only export for the one-time contact email provider evaluation.
--
-- Run this in the Supabase SQL Editor, then download the result as CSV.
-- It uses the latest inspection collection and includes companies currently in
-- either the Shortlist or Outreach workflow. One named contact is selected per
-- company, prioritizing technical leaders. Companies without a named contact
-- remain in the export so the evaluation can report that gap.

with latest_collection as (
  select max(collection_date) as collection_date
  from public.inspection_collections
), eligible_companies as (
  select
    s.collection_date,
    s.company_key,
    s.company,
    s.countries,
    s.detail_payload,
    coalesce(rs.fit_status, 'unreviewed') as fit_status,
    public.inspection_normalize_outreach_status(
      coalesce(rs.outreach_status, 'not_started')
    ) as outreach_status,
    public.inspection_workflow(
      coalesce(rs.fit_status, 'unreviewed'),
      coalesce(rs.outreach_status, 'not_started')
    ) as workflow
  from public.inspection_company_snapshots s
  join latest_collection latest
    on latest.collection_date = s.collection_date
  left join public.company_review_state rs
    on rs.company_key = s.company_key
), selected as (
  select
    company.*,
    contact.value as contact
  from eligible_companies company
  left join lateral (
    select value
    from jsonb_array_elements(
      coalesce(company.detail_payload -> 'contacts', '[]'::jsonb)
    ) as contacts(value)
    where nullif(btrim(value ->> 'name'), '') is not null
    order by
      case
        when value ->> 'role' = 'cto'
          or lower(coalesce(value ->> 'title', '')) ~ '(chief technology|\mcto\M)'
          then 1
        when value ->> 'role' = 'head_of_ai_data_engineering'
          or lower(coalesce(value ->> 'title', '')) ~
            '(head of (ai|data|engineering)|vp of (ai|data|engineering)|director of (ai|data|engineering))'
          then 2
        when value ->> 'role' = 'hiring_manager' then 3
        when value ->> 'role' = 'ceo_founder' then 4
        when value ->> 'role' = 'recruiter' then 5
        else 6
      end,
      lower(value ->> 'name')
    limit 1
  ) contact on true
  where company.workflow in ('shortlist', 'outreach')
)
select
  collection_date,
  company_key,
  company,
  to_json(countries)::text as countries,
  fit_status,
  outreach_status,
  workflow,
  contact ->> 'name' as contact_name,
  contact ->> 'role' as contact_role,
  contact ->> 'title' as contact_title,
  contact ->> 'email' as existing_email,
  contact ->> 'linkedin_url' as contact_linkedin_url,
  coalesce(contact -> 'source_urls', '[]'::jsonb)::text as contact_source_urls,
  coalesce(detail_payload -> 'company_source_urls', '[]'::jsonb)::text as company_source_urls
from selected
order by
  case workflow when 'shortlist' then 1 else 2 end,
  lower(company),
  company_key;
