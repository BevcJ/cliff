create table if not exists public.company_review_state (
  company_key text primary key,
  company text not null,
  fit_status text not null default 'unreviewed',
  outreach_status text not null default 'not_started',
  notes text not null default '',
  communication_history text not null default '',
  last_outreach_date date,
  inspected_at timestamptz,
  last_seen_collection_date date,
  created_at timestamptz not null default now(),
  last_updated_at timestamptz not null default now(),
  last_updated_by text,

  constraint company_review_state_fit_status_check
    check (fit_status in ('unreviewed', 'best_fit', 'possible_fit', 'not_interesting')),

  constraint company_review_state_outreach_status_check
    check (outreach_status in (
      'not_started',
      'message_sent',
      'follow_up_sent',
      'active_conversation',
      'closed',
      'lost_client_rejection',
      'lost_no_response'
    ))
);

alter table public.company_review_state
  add column if not exists communication_history text not null default '';

alter table public.company_review_state
  add column if not exists last_outreach_date date;

create index if not exists company_review_state_fit_status_idx
  on public.company_review_state (fit_status);

create index if not exists company_review_state_outreach_status_idx
  on public.company_review_state (outreach_status);

comment on table public.company_review_state is
  'Shared current-state review data for AI Hiring Radar company inspection.';

comment on column public.company_review_state.last_outreach_date is
  'Calendar date of the most recent manually recorded outbound message.';

-- Least-privilege app role guidance:
-- 1. Create a dedicated database user/role for the Streamlit app in Supabase.
-- 2. Replace app_review_state_user below with that role name.
-- 3. Run the grants with a privileged database role.
--
-- grant usage on schema public to app_review_state_user;
-- grant select, insert, update on public.company_review_state to app_review_state_user;
