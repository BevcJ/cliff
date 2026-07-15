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

create table if not exists public.inspection_collections (
  collection_date date primary key,
  source_kind text not null,
  snapshot_count integer not null,
  job_count integer not null,
  sync_summary jsonb not null default '{}'::jsonb,
  synced_at timestamptz not null default now(),

  constraint inspection_collections_snapshot_count_check
    check (snapshot_count >= 0),
  constraint inspection_collections_job_count_check
    check (job_count >= 0)
);

create table if not exists public.inspection_company_snapshots (
  collection_date date not null,
  company_key text not null,
  company text not null,
  countries text[] not null default '{}',
  sources text[] not null default '{}',
  workplace_modes text[] not null default '{}',
  ai_team_contexts text[] not null default '{}',
  delivery_contexts text[] not null default '{}',
  role_classification text,
  company_type text,
  company_size text,
  ai_tech_forward_signal text,
  job_count integer not null default 0,
  job_description_extract_count integer not null default 0,
  has_contacts boolean not null default false,
  has_job_description_extracts boolean not null default false,
  has_company_enrichment boolean not null default false,
  search_text text not null default '',
  search_vector tsvector generated always as (
    to_tsvector('simple', search_text)
  ) stored,
  summary_payload jsonb not null,
  detail_payload jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  primary key (collection_date, company_key),
  foreign key (collection_date)
    references public.inspection_collections (collection_date)
    on delete cascade,

  constraint inspection_company_snapshots_job_count_check
    check (job_count >= 0),
  constraint inspection_company_snapshots_jd_count_check
    check (job_description_extract_count >= 0)
);

create index if not exists inspection_company_snapshots_company_key_idx
  on public.inspection_company_snapshots (company_key);

create index if not exists inspection_company_snapshots_company_type_idx
  on public.inspection_company_snapshots (company_type);

create index if not exists inspection_company_snapshots_company_size_idx
  on public.inspection_company_snapshots (company_size);

create index if not exists inspection_company_snapshots_ai_signal_idx
  on public.inspection_company_snapshots (ai_tech_forward_signal);

create index if not exists inspection_company_snapshots_has_contacts_idx
  on public.inspection_company_snapshots (has_contacts);

create index if not exists inspection_company_snapshots_countries_gin_idx
  on public.inspection_company_snapshots using gin (countries);

create index if not exists inspection_company_snapshots_sources_gin_idx
  on public.inspection_company_snapshots using gin (sources);

create index if not exists inspection_company_snapshots_workplace_modes_gin_idx
  on public.inspection_company_snapshots using gin (workplace_modes);

create index if not exists inspection_company_snapshots_ai_team_contexts_gin_idx
  on public.inspection_company_snapshots using gin (ai_team_contexts);

create index if not exists inspection_company_snapshots_delivery_contexts_gin_idx
  on public.inspection_company_snapshots using gin (delivery_contexts);

create index if not exists inspection_company_snapshots_search_idx
  on public.inspection_company_snapshots using gin (search_vector);

comment on table public.inspection_collections is
  'Synced collection dates available to the AI Hiring Radar inspection UI.';

comment on table public.inspection_company_snapshots is
  'Company-centric compact inspection snapshots served to the AI Hiring Radar inspection UI.';
