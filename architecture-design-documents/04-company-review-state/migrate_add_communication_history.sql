begin;

alter table public.company_review_state
  add column if not exists communication_history text not null default '';

commit;
