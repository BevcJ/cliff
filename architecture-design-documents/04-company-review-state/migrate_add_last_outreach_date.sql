alter table public.company_review_state
  add column if not exists last_outreach_date date;

comment on column public.company_review_state.last_outreach_date is
  'Calendar date of the most recent manually recorded outbound message.';
