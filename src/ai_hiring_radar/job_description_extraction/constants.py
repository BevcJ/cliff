EXTRACTION_VERSION = "v1"
PROMPT_VERSION = "v2"
DEFAULT_JOB_DESCRIPTION_EXTRACTION_MODEL = "openai:gpt-5-mini"
DEFAULT_JOB_DESCRIPTION_EXTRACTION_PROVIDER = "default"
JOB_DESCRIPTION_EXTRACT_RECORD_TYPE = "job_description_extract"
JOB_DESCRIPTION_EXTRACTION_PROMPT = """Extract structured information from the provided job data.
Be conservative: null is better than a guessed value.

General rules:
- Use all provided fields, not only the job description.
- Return only information explicitly present in the provided job data.
- Do not use external knowledge.
- Do not infer from company name, industry assumptions, or general role stereotypes.
- Do not classify from the job title alone unless the title contains an explicit signal
  for that exact field, such as "Remote" or "Hybrid".
- If a field is not clearly supported, return null or an empty list.

workplace_mode values:
- remote: only when the data explicitly says remote, remote-first, work remotely,
  work from anywhere, Germany-wide remote, or similar.
- hybrid: only when the data explicitly says hybrid, a location field contains a
  hybrid marker, or the description states an office cadence such as 2 days per
  week in the office.
- onsite: only when the data explicitly says onsite, on-site, in-office, office
  based, or no remote/hybrid option.
- Return null when the only evidence is a city, country, office name, or normal
  job location such as Berlin, Hamburg, Barcelona, Mexico City, or US (New York).
- If signals conflict, prefer the most explicit work-arrangement statement in the
  description or workplace_type. For example, "remote-first culture" is remote
  even when optional office locations are listed.

ai_team_context values:
- existing_ai_team: use when the data explicitly mentions an existing AI, ML,
  data science, AI platform, AI product, AI operations, or engineering team, or
  collaboration with such teams.
- existing_ai_team also applies when the company is already building or operating
  a named AI product/platform and the role joins or works on it.
- first_ai_person: use only when the data explicitly says this is the first AI hire,
  first dedicated AI person, first AI role/function, or equivalent.
- Do not use first_ai_person merely because the role will "build from the ground
  up" or join a "new team" if the same data mentions existing AI platform/team,
  AI product, AI operations, or AI specialists.
- Return null when only the title, team name, department, or role search term
  hints at AI.

delivery_context values:
- internal: the role builds, operates, manages, or enables AI for the employer's
  own product, teams, workflows, support, marketing, GTM, operations, or business
  decisions.
- external_clients: the role delivers AI work to external customers, clients, or client accounts.
  This includes consulting, implementation, solution architecture,
  client deployments, customer integrations, or professional services.
- mixed: use only when there is explicit evidence of both internal product/team
  work and external client/customer delivery.
- Return null for title-only records or when the audience of the work is unclear.

contacts:
- Contacts must only include people or contact details present in the provided job
  data.
- Do not invent names, titles, emails, LinkedIn URLs, or roles.
- Generic recruiting emails are allowed when explicitly present.
- Use the most specific contact role supported by the text. Use other for a named
  contact with no matching role. Leave role null when only a generic email is
  present.

posted_at and updated_at:
- Use normalized_source_dates.posted_at exactly when present for posted_at.
- Use normalized_source_dates.updated_at exactly when present for updated_at.
- Otherwise use source_created_at for posted_at and source_updated_at for
  updated_at when they are explicit source date fields.
- Otherwise use only explicit posted/updated dates from the job text.
- Never use collected_at as posted_at or updated_at; collected_at is crawl time.
- Do not estimate job age or derive posted/updated dates from "today", freshness,
  collection time, or surrounding context.
""".strip()
