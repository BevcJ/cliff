begin;

select plan(14);

select is(public.inspection_workflow('unreviewed', 'not_started'), 'inspect', 'unreviewed companies remain in Inspect');
select is(public.inspection_workflow('best_fit', 'not_started'), 'shortlist', 'suitable not-started companies enter Shortlist');
select is(public.inspection_workflow('possible_fit', 'message_sent'), 'outreach', 'sent suitable companies enter Outreach');
select is(public.inspection_workflow('best_fit', 'closed'), 'closed', 'Closed takes precedence');
select is(public.inspection_workflow('not_interesting', 'closed'), 'closed', 'Closed beats rejected fit');
select is(public.inspection_workflow('best_fit', 'lost_no_response'), 'rejected', 'lost outreach is rejected');
select is(public.inspection_workflow('not_interesting', 'not_started'), 'rejected', 'rejected fit is rejected');

select is(public.inspection_follow_up_status('message_sent', current_date), 'fresh', 'same-day outreach is fresh');
select is(public.inspection_follow_up_status('message_sent', current_date - 4), 'due_soon', 'four-day outreach is due soon');
select is(public.inspection_follow_up_status('follow_up_sent', current_date - 6), 'follow_up', 'six-day follow-up needs action');
select is(public.inspection_follow_up_status('message_sent', null), 'date_missing', 'active outreach without date is flagged');
select is(public.inspection_follow_up_status('closed', current_date - 20), '', 'closed outreach suppresses follow-up');

select ok(public.inspection_matches_text_array(array['remote'], array['remote']), 'array filters match overlap');
select ok(public.inspection_matches_text_value(null, array['__missing__']), 'scalar filters match missing sentinel');

select * from finish();

rollback;
