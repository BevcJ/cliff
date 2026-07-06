# Netherlands AI Hiring Market Research Methodology

Research date: 2026-06-13

## Objective

Assess the Netherlands market for companies investing in AI capabilities using hiring activity as the primary signal. The goal is company discovery, not job search.

## Scope

Geography: Netherlands, including Netherlands-based roles, Netherlands office roles, and remote-Europe roles only when the posting explicitly includes a Netherlands location or Amsterdam/Rotterdam eligibility.

Primary signal types:

- AI execution roles: AI Engineer, Applied AI Engineer, LLM Engineer, GenAI Engineer, Generative AI Engineer, AI Solutions Engineer.
- AI product roles: AI Product Manager, GenAI Product Manager, AI Product Owner, AI Solutions Product Manager.
- Dutch equivalents were included when clearly equivalent, for example AI Product Owner, generatieve AI engineer, or AI platform product owner.

Secondary signals:

- Adjacent AI roles were included only when the job text clearly made AI, GenAI, LLMs, agents, RAG, or AI systems central to the role.
- Examples: Machine Learning Engineer with LLM/vLLM/LangGraph/MCP evidence, Product Owner Data Science and AI Platformen, Agentic AI Lead.

Excluded or downgraded signals:

- Generic Data Scientist, Data Engineer, BI, analytics, classic ML, MLOps, computer vision, forecasting, and platform roles unless GenAI/application AI was explicit.
- Consulting and systems-integration roles are treated as delivery-capacity signals, not proof of the employer's own internal adoption.
- Internships are kept as evidence but not weighted the same as full-time roles.
- Closed jobs are marked as recent/closed and used only as trend support.
- Aggregator-only results were excluded unless corroborated by a first-party or ATS page.

## Source Policy

Used:

- First-party company career pages.
- Public ATS pages and APIs such as Greenhouse, Recruitee, Lever, Workday, SmartRecruiters, SuccessFactors, Teamtailor, Workable, and company-hosted job pages.
- Public sector job sites, especially Werken bij de Overheid and first-party government organization pages.
- Official statistics and policy sources: CBS, Eurostat via CBS, European Commission AI Watch, European Commission DESI/Digital Decade pages.
- Public job-board pages where accessible and legally safer, for example Welcome to the Jungle and Banken.nl.

Avoided:

- Direct automated scraping of LinkedIn and Indeed.
- CAPTCHA-protected search-result scraping.
- Login-gated job boards.
- Sites that returned 403, 404, or 410 for the target role.

## Evidence Grades

High confidence:

- First-party employer or ATS page is accessible.
- Role title or description directly matches the taxonomy.
- Netherlands location is explicit or strongly evidenced.

Medium-high confidence:

- First-party or public-sector page is accessible, but the title is adjacent rather than exact.
- The description clearly centers GenAI/application AI.

Medium confidence:

- Posting is third-party but reputable, or exact title is visible on a careers listing but direct role page was unavailable.
- Netherlands eligibility is present but less direct.

Low confidence:

- Aggregator-only or stale search result. Low-confidence items are generally excluded from company records.

## Representativeness Controls

This is not a statistically representative crawl of all Dutch vacancies. It is a representative research sample for the narrow V1 objective: identifying companies with strong AI hiring signals.

Controls used:

- Sector pass across finance, healthcare, energy, retail, telecom, logistics, manufacturing, public sector, and SaaS/product companies.
- Separate treatment of consulting delivery capacity versus internal/product adoption.
- Negative evidence log for large employers and stale leads.
- Official CBS AI adoption and AI vacancy statistics to benchmark the posting sample.

Known biases:

- Public job postings overrepresent large employers, English-language technology roles, and companies with modern ATS systems.
- Small firms, Dutch-only postings, recruiter-hidden roles, and roles filled via agencies are underrepresented.
- Current open postings miss companies that already hired AI teams or paused hiring.
- V1 taxonomy intentionally excludes many classic data/ML roles, so it undercounts broader AI adoption.
- Consulting firms appear heavily because they use explicit AI titles; this can distort the view if not segmented.

## Interpretation Rule

Hiring evidence should be read as a directional investment signal, not a full market census. A company with both an AI product owner/manager and AI engineering roles is a stronger company-discovery target than a company with only broad AI marketing language or only consulting delivery roles.
