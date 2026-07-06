# Netherlands AI Hiring Market Report

Research date: 2026-06-13

## Executive Summary

The Netherlands is a strong AI adoption market, but explicit AI hiring is still concentrated. Official CBS data shows broad AI usage rising quickly, while AI-specific vacancies remain a small share of all vacancies. This creates an important distinction for company discovery:

- Many Dutch companies now use AI tools, but only a smaller set is hiring dedicated AI builders or AI product owners.
- The best discovery targets are companies with both product ownership and engineering execution signals, or traditional companies hiring explicit AI execution roles.
- The strongest active non-consulting signals found in this research are Rabobank, Philips, HeadFirst Group, Channable, OpenUp, Tellent, Serrala, Toku, Creative Clicks, and selected public-sector organizations.
- Consulting and AI services firms are highly active, especially Accenture, ML6, Xebia, Sogeti, Capgemini, EY, Macaw, Conclusion, DataNorth, and others. These should be treated as delivery-capacity and ecosystem-demand signals, not as direct evidence that those firms are adopting AI internally.
- The strongest use-case patterns are agentic workflows, internal productivity, customer interaction automation, product feature AI, finance automation, HR/recruitment agents, healthcare/clinical AI, and public-sector operational AI.

The dataset produced with this report contains 32 company/organization intelligence records and 49 role-level findings. Not all findings are equally strong: the cleanest V1 targets are separated from internships, closed roles, consulting delivery roles, and adjacent AI roles.

## Files Produced

| File | Purpose |
|---|---|
| `market_report.md` | This analytical report. |
| `company_intelligence_records.csv` | Company-level structured dataset. |
| `evidence_log.md` | Role-level evidence, excerpts, URLs, confidence, and caveats. |
| `raw_findings.jsonl` | Machine-readable role-level findings. |
| `source_inventory.md` | Sources checked, blocked sources, non-matches, and coverage notes. |
| `methodology.md` | Inclusion/exclusion criteria and representativeness controls. |

## Official Market Baseline

### Business AI Adoption Is Rising Fast

CBS reported that in 2024, 22.7 percent of Dutch companies with 10 or more employed persons used at least one AI technology. That was up from 14.0 percent in 2023. The most common 2024 technologies were text mining at 13.5 percent and natural language generation at 12.3 percent.

CBS also reported 2025 figures using a broader denominator of companies with 2 or more employed persons. On that basis, 17 percent of Dutch companies used AI in 2025, up from 13 percent in 2024 and 8 percent in 2023. Larger companies are much more active: 66 percent of companies with 250+ employees used AI in 2025, compared with 14 percent of companies with 2 to 9 employees.

Interpretation: the adoption curve is real, but company size matters. Hiring-based discovery will overrepresent larger companies because they are more likely to formalize AI activity into named roles.

### Sector Adoption Pattern

CBS 2025 sector figures show the strongest AI use in information and communication, specialized business services, and financial services:

| Sector | AI Use In 2025 |
|---|---:|
| Information and communication | 54% |
| Specialized business services | 31% |
| Financial services | 28% |
| Real estate activities | 21% |
| Energy, water and waste management | 18% |
| Manufacturing | 16% |
| Health care and social care | 16% |
| Trade | 12% |
| Transportation and storage | 7% |
| Construction | 7% |
| Accommodation and food services | 6% |

This pattern matches the hiring evidence. Most explicit GenAI/agent roles appear in SaaS, consulting, finance, healthtech, public sector, and business services. Logistics, construction, and broad retail showed weaker visible V1 hiring evidence in this pass, despite likely operational AI opportunities.

### AI Use Cases In Dutch Companies

CBS 2025 figures show that among companies using AI:

| Purpose | Share Of AI-Using Companies |
|---|---:|
| Marketing or sales | 35% |
| Business administration or management | 32% |
| R&D or innovation | 25% |
| Production or service processes | 18% |
| Accountancy or financial administration | 17% |
| ICT security | 11% |
| Logistics | 4% |

Interpretation: the official use-case distribution supports the hiring signals found here. Many visible roles cluster around product/customer interaction, internal management workflows, business process automation, and R&D/product innovation rather than logistics optimization.

### AI Vacancies Are Still Rare Nationally

CBS AI Monitor 2024 used Textkernel vacancy data from Q1 2018 through Q2 2024 and found 9,430 online AI job ads corresponding to 8,725 weighted AI vacancies. AI vacancies ranged from 0.05 to 0.13 percent of all Dutch vacancies across the period. The model found roughly 425 AI vacancies in Q2 2024.

Important characteristics from CBS:

- AI vacancies are geographically concentrated: Noord-Holland, Zuid-Holland, Noord-Brabant, Utrecht, and Gelderland account for much of the total.
- About 75 percent of AI vacancies were written in English, compared with 16 percent English across all vacancies.
- More than 72 percent were skill level 4 roles requiring higher or academic education; about 23 percent were skill level 3.
- Education, information and communication, specialized business services, trade, manufacturing, and financial services were the largest sectors by AI vacancy count.
- Universities are a major part of the official AI vacancy picture: seven of the top ten organizations by AI vacancies were Dutch universities.

Interpretation: official AI-vacancy counts are broader than this V1 GenAI/application-AI taxonomy and include education/research. For company discovery, universities and classic research roles should usually be separated from commercial implementation/productization signals.

## Confirmed Market Segments

### Segment 1: Traditional Or Established Companies Adopting AI Internally

These are the most interesting discovery targets because they indicate AI moving from discussion to implementation inside existing businesses.

| Company | Evidence Strength | Why It Matters |
|---|---|---|
| Rabobank | Very strong | Active agentic SDLC engineering and conversational AI engineering roles, plus recent GenAI product owner evidence. This suggests both internal productivity and customer-interaction AI. |
| Philips | Very strong | Multiple signals around agentic AI, LLMs, RAG, chatbots, AI use-case roadmap, pilots, and scaling. Shows both healthtech product context and internal services/process AI. |
| HeadFirst Group | Very strong | Active AI Product Manager, Applied AI Engineer, and AI Solutions Engineer. Clear product plus execution signal in a non-AI-native business services company. |
| Eneco | Medium | AI Risk Assistant internship suggests internal workflow automation in energy/utilities, but internship status makes it weaker than full-time hiring. |
| IND | Strong | Public-sector ML Engineer role explicitly references LLM inference, vLLM, Langfuse, MCP, LangGraph, and agentic AI. This is unusually concrete public-sector GenAI stack evidence. |
| Rijkswaterstaat | Medium-high | Generic data scientist title, but role text focuses on generative AI applications for public infrastructure use cases. |
| Ministerie van Defensie | Strong | Product Owner for Data Science and AI platforms suggests institutionalized AI platform ownership. |
| UMCG | Strong | Exact AI Engineer role for medical imaging and clinical AI solutions. Not GenAI-specific, but a strong applied-AI hiring signal. |
| Douane | Medium | Edge/IoT role integrating AI models and AI BOX technology. Operational AI signal, but title is not a V1 AI role. |

Key pattern: internal AI adoption roles increasingly use agentic language. The most mature signals mention production, scaling, platforms, core systems, roadmap ownership, or operational deployment.

### Segment 2: SaaS And Product Companies Embedding AI Into Existing Products

This is the clearest commercial productization segment.

| Company | Evidence Strength | Why It Matters |
|---|---|---|
| Channable | Strong | AI Engineer role for customer-facing AI features in a B2B SaaS product-data workflow platform. |
| OpenUp | Strong | Senior AI Engineer for AI Guide, multi-agent architecture, RAG, and grounded AI product experiences in digital mental wellbeing. |
| Tellent | Strong | Senior Product Manager, AI & Agents for a unified AI layer and MCP/specialist agents across HR/recruitment products. |
| JetBrains | Strong | Amsterdam-eligible AI Lead for Python tools, MCP integrations, agent workflows, and making tools AI-native. |
| Creative Clicks | Medium-high | Exact AI Product Owner role with AI roadmap and AI-driven solutions in marketing/adtech. |
| Serrala | Strong | AI Product Owner for finance automation and agent-driven finance execution. |
| Toku | Strong | Applied AI Engineer for LLM/NLP, RAG, speech-to-text, and production AI, with Rotterdam location signal. |
| Workwize | Medium | AI Product Manager on Welcome to the Jungle with strong AI agents/automation language, but not visible on current first-party board during validation. |
| Insider One | Strong | AI Product Manager role with GenAI fundamentals, LLMs, prompt engineering, RAG, OpenAI, Claude, and Mistral. More AI-core than traditional. |

Key pattern: product companies are hiring either AI product managers to define the AI layer or senior AI engineers to turn AI into production product features. The language is more specific than generic AI marketing: RAG, multi-agent architecture, MCP, AI guides, finance automation, and LLM APIs.

### Segment 3: Consulting, Systems Integration, And AI Services Capacity

This segment is very active but should not be confused with internal adoption by end-user companies.

| Company | Evidence Strength | Signal Type |
|---|---|---|
| Accenture | Strong | GenAI Engineer in Amsterdam, LLM prototypes and agentic workflows. |
| ML6 | Very strong | Multiple GenAI/AI engineering roles across Amsterdam/Eindhoven. Strong AI services capacity. |
| Xebia | Strong | Gen AI Engineer and AI Engineer roles for AI agents, GenAI tooling, and agentic AI systems. |
| Sogeti | Strong | AI Engineer and Agentic AI Lead roles in Utrecht with production AI and LLM/multi-agent language. |
| Capgemini | Strong | AI Engineer and Agentic AI Engineer roles in Utrecht. |
| EY | Strong | AI Engineer in Amsterdam, plus broader AI search context. |
| Sopra Steria / Ordina | Medium-high | Practice Lead Data Science & A.I. and adjacent ML role. Strong practice signal but less clean V1 fit. |
| Macaw | Medium-high | Solution Architect AI & Digital Products plus AI Developer listing. Microsoft-oriented AI delivery signal. |
| Conclusion | Medium-high | AI strategy and Data & AI business roles. Strong market demand signal, weaker engineering evidence. |
| Sia Partners | Medium-high | Machine Learning Engineer in Amsterdam for production ML/AI solutions. Broader than GenAI. |
| KPMG | Medium-high | AI & Data architecture role with generative AI language. Advisory signal. |
| DataNorth | Strong | AI consultant roles for client AI questions, PoCs, and complete solutions. |
| Levy Professionals | Medium | AI Engineer / Senior GenAI and MLOps role via staffing intermediary. Useful demand signal, but client attribution unclear. |

Key pattern: services firms are using explicit GenAI and agentic titles faster than many end-user companies. This means a naive job-title crawl will over-rank consultancies unless the company-type classifier separates delivery capacity from adoption/productization.

## Technology Signal Analysis

### Strongest Repeated Signals

| Signal | Where It Appeared | Interpretation |
|---|---|---|
| Agentic AI / AI agents | Rabobank, Philips, HeadFirst, OpenUp, Tellent, JetBrains, Serrala, Xebia, Sogeti, Capgemini, ML6 | Agents are now a mainstream hiring-language signal, not just experimental language. |
| RAG / grounding | Philips, OpenUp, Toku, Insider One, ML6 | Retrieval-grounded GenAI is a common production pattern. |
| MCP | Tellent, JetBrains, IND, ML6 | MCP appears in advanced product/platform contexts and should be tracked as a high-signal term. |
| LLM APIs/model vendors | Insider One, Philips, Toku, Accenture, IND | OpenAI, Claude, Mistral and LLM API familiarity show productization intent. |
| AI platforms | Ministerie van Defensie, Philips, ML6, Xebia | Platform language suggests organizational scaling beyond one-off PoCs. |
| Conversational AI/chatbots | Rabobank, Philips | Customer interaction and internal assistant use cases remain prominent. |
| Databricks | HeadFirst Group | Enterprise data platform plus AI applications signal. |
| vLLM/LangGraph/Langfuse | IND | Strong public-sector technical maturity signal. |

### Terms Worth Adding To V1 Detection

The original taxonomy is good, but Netherlands evidence suggests adding these as high-signal description terms:

- Agentic AI
- AI agents
- MCP / Model Context Protocol
- RAG / retrieval-augmented generation
- Grounding systems
- AI Guide / assistant / copilot
- LLM inference
- vLLM
- LangGraph
- Langfuse
- AI platform
- AI use-case roadmap
- GenAI roadmap

## Use-Case Analysis

| Use Case | Companies/Organizations | Market Meaning |
|---|---|---|
| Developer productivity / SDLC agents | Rabobank, JetBrains, ML6, Xebia | Strong internal and product AI area. Often tied to agents and MCP. |
| Customer interaction automation | Rabobank, Philips, OpenUp, Toku | High-value area where AI must connect to core systems or sensitive workflows. |
| Internal workflow automation | HeadFirst, Eneco, Philips, public sector | Practical adoption path for traditional organizations. |
| Product AI layer | Tellent, Channable, Serrala, Workwize, JetBrains | Strong AI-enabled product segment. |
| Finance/accounting automation | Serrala, Rabobank, KPMG | Aligns with CBS finding that business administration and financial administration are common AI purposes. |
| Healthcare/clinical AI | Philips, UMCG, OpenUp | High-value but governance-heavy segment. |
| Public-sector operational AI | IND, Rijkswaterstaat, Defensie, Douane | Clear movement from policy into operational AI systems. |

## Company Priority Tiers

### Tier 1: Highest-Priority Discovery Targets

These companies show either both product and execution signals, traditional-industry AI investment, or highly concrete GenAI production language.

| Company | Reason |
|---|---|
| HeadFirst Group | Active AI Product Manager plus Applied AI Engineer plus AI Solutions Engineer. Very clean execution plus product signal. |
| Rabobank | Traditional bank with active agentic engineering and conversational AI integration into core banking. |
| Philips | Multiple AI roles across agentic AI, roadmap, pilots, RAG, chatbots, and AI apps. |
| Tellent | AI product manager owning agents and unified AI layer in HR SaaS. |
| OpenUp | AI engineer for multi-agent/RAG product experiences in a sensitive domain. |
| Channable | AI Engineer directly tied to customer-facing SaaS product features. |
| Serrala | AI Product Owner for agent-driven finance automation. |
| Toku | Applied AI Engineer with explicit LLM/RAG/NLP production scope. |
| IND | Public-sector role with highly concrete LLM/agentic infrastructure stack. |
| Ministerie van Defensie | AI platform product ownership signal. |

### Tier 2: Relevant But Needs Review

| Company | Reason |
|---|---|
| Creative Clicks | Exact AI Product Owner role, but market/adtech context needs use-case review. |
| Workwize | Strong AI PM language, but currently validated only through third-party page. |
| Eneco | Good internal AI workflow signal, but internship-level. |
| Rijkswaterstaat | Strong GenAI description but generic data scientist title. |
| UMCG | Exact AI Engineer role, but medical imaging/classic applied AI rather than GenAI. |
| Douane | Operational AI deployment signal, but role title is Edge & IoT Engineer. |
| CLEVR | Strong AI Solutions Engineer role, but consulting/delivery classification reduces end-user adoption value. |
| Insider One | Strong AI product role but more AI-core and Europe-remote than Netherlands-specific end-user adoption. |

### Tier 3: Ecosystem And Partner Signals

Consultancies and AI services firms are valuable for understanding demand, partnerships, and competition, but they should not dominate the company-discovery output.

High-signal providers: ML6, Xebia, Accenture, Sogeti, Capgemini, EY, Macaw, DataNorth.

Advisory/strategy providers: KPMG, Conclusion, Sopra Steria/Ordina, Sia Partners.

Intermediary signal: Levy Professionals.

## Representativeness Assessment

### What This Report Represents Well

This report is representative of visible, public, evidence-backed Netherlands AI hiring signals for the narrow V1 taxonomy. It is strongest for:

- Companies using modern ATS systems.
- English-language AI roles.
- Amsterdam, Utrecht, Eindhoven, Hoofddorp, Rotterdam, and national public-sector roles.
- GenAI, LLM, RAG, agents, AI product, and AI platform roles.
- Larger companies and SaaS/product companies that publish detailed job descriptions.

### What This Report Underrepresents

The report likely underrepresents:

- Small and mid-sized companies using AI through vendors or existing SaaS tools without hiring dedicated AI roles.
- Dutch-only job postings that do not use English AI titles.
- Roles filled through recruiters, staffing agencies, or LinkedIn-only workflows.
- Companies that already hired AI teams and currently have no open postings.
- Classic AI/ML work in manufacturing, logistics, mobility, computer vision, forecasting, and optimization because V1 intentionally filters much of that out.
- Universities and research institutes, which are important in official AI vacancy statistics but less relevant to the commercial company-discovery use case.

### Why Search Results Alone Would Be Misleading

Search-engine scraping was not reliable in this environment because DuckDuckGo showed CAPTCHA challenges and other search surfaces were reported as blocked or rate-limited. More importantly, broad search results produce many stale, aggregator-only, and non-Netherlands roles. First-party and ATS validation removed several false positives, including flatexDEGIRO, Infosys Consulting, Jobortunity, Enexis, Celonis, and old NS/Radboudumc roles.

### Comparison With CBS

CBS shows that AI vacancies are a small share of all vacancies and heavily concentrated in higher-skilled, English-language roles. This validated the observed pattern: the public evidence is dense in English-language technology roles and sparse in sectors where AI adoption may happen through tools, vendors, or consulting projects rather than direct hiring.

## Market Conclusions

1. The Netherlands has moved beyond AI awareness into practical AI implementation, but hiring evidence is still concentrated in a narrow group of companies.
2. GenAI and agentic AI are now visible in actual job descriptions, especially in banking, healthtech, SaaS, public sector, and consulting.
3. The most commercially useful discovery signal is not generic AI adoption, but the combination of AI product ownership and AI engineering execution.
4. Consulting firms are a large part of visible AI hiring. They are important for market demand but should be separated from end-user adoption targets.
5. Public-sector AI hiring is more concrete than expected, with explicit LLM infrastructure, AI platform ownership, and operational AI deployment signals.
6. Product companies are embedding AI into existing workflows rather than creating standalone AI products: HR agents, finance automation, ecommerce/product-data AI, mental-health guides, developer tools, and voice/NLP workflows.
7. Retail, logistics, construction, and manufacturing appear underrepresented in V1 hiring evidence despite official AI adoption and clear operational opportunity areas. This is a discovery gap, not proof of low AI activity.

## Recommendations For The Company Intelligence Idea

### Keep The V1 Role Scope Narrow

The original plan is directionally correct. Keep AI execution and AI product roles as primary signals. Add only high-signal GenAI/application-AI terms to descriptions. Do not broaden too early into all data science and ML roles.

### Add A Consulting/Delivery-Capacity Segment

Without this, the dataset will be flooded by consultancies and systems integrators. Recommended additional company segment:

- AI Services / Delivery Capacity

This segment should be useful, but should not be mixed with Internal AI Adoption and AI-Enabled Product in lead prioritization.

### Add Dutch Search Terms

Useful Dutch terms from this research:

- kunstmatige intelligentie
- generatieve AI
- AI toepassingen
- AI-oplossingen
- AI platformen
- Product Owner Data Science en AI
- AI-gedreven workflows
- AI-modellen
- agentic AI toepassingen

### Track Role Status

The system should store status because closed jobs are still useful trend evidence but should not be counted as active hiring. Suggested statuses:

- Active
- Active internship
- Recent closed
- Aggregator-only
- Excluded
- Needs validation

### Track Evidence Quality

Recommended evidence tiers:

- First-party employer or ATS page: high.
- Public-sector official page: high.
- Reputable job board with exact role and location: medium.
- Aggregator-only/search-result-only: low or excluded.
- LinkedIn/Indeed-only: manual validation only, not automated ingestion.

### Suggested MVP Prioritization Logic

Prioritize companies in this order:

1. Non-AI-native company with both AI product and AI execution roles.
2. Traditional company with explicit GenAI/LLM/agent engineering role.
3. SaaS/product company with AI Product Manager or AI Product Owner.
4. SaaS/product company with AI Engineer tied to product features.
5. Public-sector or regulated-sector organization with concrete LLM/platform/agent infrastructure.
6. Consulting/service provider roles as ecosystem signal, not core target.
7. Internships and adjacent roles as weak supporting signals.

## Suggested Initial Target List

For immediate manual review, start with:

| Priority | Company | Why |
|---|---|---|
| 1 | HeadFirst Group | Both product and execution roles; clear business-solutions AI. |
| 2 | Rabobank | Traditional bank with agentic SDLC and conversational AI engineering. |
| 3 | Philips | Multiple GenAI/agentic AI signals across healthcare/product/process contexts. |
| 4 | Tellent | AI product ownership for agents and unified AI layer. |
| 5 | OpenUp | Senior AI engineering for RAG/multi-agent product experience. |
| 6 | Channable | AI engineering for customer-facing SaaS features. |
| 7 | Serrala | AI Product Owner for finance automation. |
| 8 | Toku | Applied LLM/NLP/RAG engineer with Netherlands signal. |
| 9 | IND | Concrete public-sector LLM/agentic stack. |
| 10 | Ministerie van Defensie | Product ownership of AI/data-science platforms. |

For ecosystem mapping and potential partner/competitor tracking, separately monitor ML6, Xebia, Accenture, Sogeti, Capgemini, EY, Macaw, DataNorth, and Conclusion.

## References

| Source | URL |
|---|---|
| CBS, Increasing use of AI by business | https://www.cbs.nl/en-gb/news/2025/09/increasing-use-of-ai-by-business |
| CBS, Dutch article with 2024 AI use and EU comparison | https://www.cbs.nl/nl-nl/nieuws/2025/09/gebruik-kunstmatige-intelligentie--ai---door-bedrijven-neemt-toe |
| CBS, Companies using AI above all for marketing or sales | https://www.cbs.nl/en-gb/news/2025/50/companies-using-ai-above-all-for-marketing-or-sales |
| CBS, Dutch AI Monitor 2024 | https://www.cbs.nl/en-gb/longread/aanvullende-statistische-diensten/2025/ai-monitor-2024 |
| CBS, Demand for workers with AI skills | https://www.cbs.nl/en-gb/longread/aanvullende-statistische-diensten/2025/ai-monitor-2024/6-demand-for-workers-with-ai-skills |
| European Commission AI Watch, Netherlands AI Strategy Report | https://ai-watch.ec.europa.eu/countries/netherlands/netherlands-ai-strategy-report_en |
| European Commission DESI Netherlands | https://digital-strategy.ec.europa.eu/en/policies/desi-netherlands |

Role-level source URLs are listed in `evidence_log.md` and `raw_findings.jsonl`.
