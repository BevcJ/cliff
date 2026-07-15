-- Run before deploying the application with the new outreach statuses.
begin;

alter table public.company_review_state
  drop constraint if exists company_review_state_outreach_status_check;

alter table public.company_review_state
  add constraint company_review_state_outreach_status_check
  check (outreach_status in (
    'not_started',
    'message_sent',
    'follow_up_needed',
    'replied',
    'follow_up_sent',
    'active_conversation',
    'closed',
    'lost_client_rejection',
    'lost_no_response'
  ));

commit;
