-- Run after the application with legacy read aliases has been deployed.
begin;

update public.company_review_state
set outreach_status = case outreach_status
  when 'follow_up_needed' then 'follow_up_sent'
  when 'replied' then 'active_conversation'
end
where outreach_status in ('follow_up_needed', 'replied');

alter table public.company_review_state
  drop constraint if exists company_review_state_outreach_status_check;

alter table public.company_review_state
  add constraint company_review_state_outreach_status_check
  check (outreach_status in (
    'not_started',
    'message_sent',
    'follow_up_sent',
    'active_conversation',
    'closed',
    'lost_client_rejection',
    'lost_no_response'
  ));

commit;
