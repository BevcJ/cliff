# Company AI Investment Radar via Hiring Data

## Goal

Identify companies that are actively investing in AI capabilities, using hiring activity as the primary signal.

The primary use case is **company discovery**, not job searching.

The output should be an evidence-backed company intelligence record that helps answer:

- Which companies are adopting AI internally?
- Which companies are embedding AI into existing products or services?
- Which companies are moving from AI experimentation to AI implementation?
- Which companies may need help with AI engineering, productization, architecture, delivery, or implementation?

---

## Core Thesis

Hiring activity is a practical signal that a company is moving from talking about AI to actually investing in AI capabilities.

Jobs are the signal.

Companies are the entity of interest.

The most interesting companies are often not AI-native companies. They are companies in traditional or established industries that are now hiring AI execution or AI product roles.

Examples:

- Banks and insurers building AI assistants or document automation
- Logistics companies automating planning, routing, or operations
- Retail companies building personalization or support automation
- Construction or manufacturing companies applying AI to workflows and knowledge management
- SaaS companies adding AI features into existing products

---

## Initial Scope

Start narrow and keep the first version simple.

### Geography

Start with:

- Netherlands

The solution should be designed so other countries can be added later without changing the core model.

Future countries:

- Germany
- Denmark
- Austria
- Switzerland

Country-specific configuration should cover:

- Job sources
- Location names
- Language hints
- Currency and salary format
- Local company enrichment sources, if needed

The role taxonomy and AI signal detection should remain reusable across countries.

---

## V1 Role Focus

For the first version, focus on two role groups only.

### 1. AI Execution Roles

These roles suggest that the company is building, integrating, or delivering AI solutions.

Track titles such as:

- AI Engineer
- Applied AI Engineer
- LLM Engineer
- GenAI Engineer
- Generative AI Engineer
- AI Solutions Engineer

Notes:

- `AI Engineer`, `Applied AI Engineer`, `LLM Engineer`, and `GenAI Engineer` are strong builder signals.
- `AI Solutions Engineer` should be treated as context-sensitive because it can mean implementation, consulting, customer success, or pre-sales.

### 2. AI Product Roles

These roles suggest that the company is turning AI into a business capability, product feature, or internal product initiative.

Track titles such as:

- AI Product Manager
- GenAI Product Manager
- AI Product Owner
- AI Solutions Product Manager

---

## Out Of Scope For V1

Avoid starting too broad.

Do not include generic data and classic ML roles in the first discovery logic unless they clearly mention GenAI/application AI in the title or description.

Out of scope for v1:

- Data Scientist
- Data Engineer
- Analytics Engineer
- Generic ML Engineer
- MLOps Engineer
- Computer Vision Engineer
- Forecasting or optimization roles
- Generic BI or analytics roles

These roles may become useful later as secondary signals, but including them too early will create noise.

---

## Simple Role Classification

Keep classification flat in v1.

| Classification | Meaning |
|---|---|
| AI Execution Role | Someone building, integrating, or delivering AI functionality |
| AI Product Role | Someone owning AI use cases, product direction, or business value |
| Both Execution + Product | Company has both builder and product ownership signals |
| Unclear AI Role | Title or description mentions AI but intent is ambiguous |

No complex scoring is needed initially.

---

## Company Type Classification

Classify the company separately from the role.

| Company Type | Meaning |
|---|---|
| Internal AI Adoption | Company appears to use AI to improve internal operations, workflows, support, document handling, or automation |
| AI-Enabled Product | Company appears to be adding AI into an existing product, platform, or service |
| AI-Native Company | Company's core business is AI software, AI tooling, or AI services |
| Unknown | Not enough evidence yet |

The preferred discovery target is usually `Internal AI Adoption` or `AI-Enabled Product`, but AI-native companies can still be relevant depending on the opportunity.

---

## Technology Signals To Extract

Focus on GenAI and application AI signals.

| Category | Examples |
|---|---|
| LLMs | LLM, GPT, Claude, Gemini, Llama, Mistral |
| GenAI Patterns | RAG, agents, copilots, prompt engineering, AI assistants |
| AI APIs And Platforms | OpenAI, Azure OpenAI, Anthropic, AWS Bedrock, Google Vertex AI |
| App Frameworks | LangChain, LlamaIndex, Semantic Kernel |
| Retrieval And Search | vector database, vector search, embeddings, Pinecone, Weaviate, Qdrant, pgvector |
| Use Cases | document automation, knowledge assistant, customer support automation, workflow automation, personalization |

Avoid treating classic ML-specific technologies as strong v1 signals unless they appear together with GenAI/application AI terms.

Lower-priority or excluded v1 technology signals:

- TensorFlow
- PyTorch
- MLflow
- Kubeflow
- SageMaker
- Computer vision tooling
- Forecasting tooling
- Generic analytics tooling

---

## Job Sources

The source strategy should be practical and legally safe.

Potential sources:

| Source Type | Use |
|---|---|
| Job data API or provider | Preferred scalable option if budget allows |
| Google Jobs through a search API/provider | Useful broad discovery layer |
| Public job boards with permitted access | Good MVP input if available |
| Company career pages | High-quality evidence, harder to scale |
| LinkedIn/Indeed manual validation | Useful for validation, not ideal for direct automated scraping |

LinkedIn and Indeed contain valuable data, but direct scraping can create legal and terms-of-service risk. Prefer APIs, permitted providers, or manual validation where needed.

---

## Raw Job Data Storage

Store raw job information first.

Avoid heavy aggregation or scoring at ingestion time. The goal is to preserve flexibility for later analysis.

Example raw job record:

```json
{
  "job_title": "AI Product Manager",
  "company": "Example Company",
  "country": "Netherlands",
  "city": "Amsterdam",
  "remote_policy": "Hybrid",
  "salary": "EUR 80k-100k",
  "description": "...",
  "source": "Job source name",
  "source_url": "https://example.com/job",
  "posting_date": "2026-06-01",
  "collected_at": "2026-06-13"
}
```

---

## Company Intelligence Record

For every discovered company, create a compact intelligence record.

| Field | Description |
|---|---|
| Company Name | Normalized company name |
| Country | Country connected to the hiring signal |
| Headquarters | HQ location if available |
| Industry | Banking, logistics, retail, construction, SaaS, etc. |
| Company Size | Raw employee count if available |
| Company Type | Internal AI Adoption, AI-Enabled Product, AI-Native Company, or Unknown |
| AI Execution Roles | Count and titles |
| AI Product Roles | Count and titles |
| Role Classification | AI Execution Role, AI Product Role, Both Execution + Product, or Unclear AI Role |
| Technology Signals | LLM, RAG, OpenAI, Azure OpenAI, agents, vector search, etc. |
| Use Case Clues | Document automation, support automation, copilots, knowledge assistant, personalization, etc. |
| Language Signals | English, Dutch, German, etc. |
| Remote Policy | Remote, hybrid, office, unknown |
| Salary Ranges | If available |
| Evidence | Job links and relevant excerpts |
| Notes | Why this company may be interesting |

---

## What Makes A Company Interesting

For v1, a company should be considered interesting if it has at least one strong AI adoption or AI productization signal.

Strong signals:

| Signal | Strength |
|---|---|
| AI Product role | Strong |
| LLM or GenAI Engineer role | Strong |
| AI Engineer role with GenAI/application AI terms | Strong |
| Both AI Product and AI Execution roles | Very strong |
| Traditional company with AI execution role | Very strong |
| Existing software/product company hiring AI Product Manager | Strong |

Weak or ambiguous signals:

| Signal | Concern |
|---|---|
| Generic AI mention in company description | May be marketing language |
| Generic data or analytics role | Too broad for v1 |
| AI Solutions Engineer at AI vendor | May be pre-sales rather than implementation |
| Consulting company hiring AI roles | May indicate delivery capacity rather than internal adoption |

---

## Suggested Tags

Use tags rather than a numeric score in the first version.

| Tag | Meaning |
|---|---|
| GenAI Hiring | Job title or description clearly references GenAI/LLMs |
| AI Execution | Company is hiring builder roles |
| AI Productization | Company is hiring AI product roles |
| Execution + Product | Company has both implementation and product ownership signals |
| Internal AI Adoption | AI appears connected to internal operations or workflows |
| AI-Enabled Product | AI appears connected to an existing product or customer-facing feature |
| Traditional Industry AI | Non-tech company hiring AI roles |
| Needs Review | Signal is promising but ambiguous |

---

## Example Company Intelligence Card

```md
Company: Example Logistics Group
Industry: Logistics
Country: Netherlands
Company Size: 5,000 employees
Company Type: Internal AI Adoption

Role Signals:
- AI Product Manager
- Applied AI Engineer

Role Classification:
- Both Execution + Product

Technology Signals:
- Azure OpenAI
- RAG
- AI assistants
- vector search

Use Case Clues:
- Internal knowledge assistant
- Customer support automation
- Workflow automation

Why Interesting:
Traditional logistics company appears to be building practical AI capabilities for internal operations and customer workflows.

Evidence:
- Job posting: AI Product Manager
- Job posting: Applied AI Engineer
- Relevant excerpts from job descriptions
```

---

## MVP Workflow

1. Collect raw job postings for the Netherlands.
2. Match job titles against the v1 AI execution and AI product role taxonomy.
3. Extract GenAI/application AI technology signals from job descriptions.
4. Normalize company names.
5. Deduplicate jobs across sources.
6. Aggregate matching jobs by company.
7. Classify role signals using the flat v1 classification.
8. Add company type classification where enough evidence exists.
9. Enrich promising companies with industry, size, and headquarters.
10. Produce an evidence-backed company list for manual review.

---

## MVP Output

The first useful output can be a spreadsheet, table, or simple internal report.

Recommended columns:

| Column | Description |
|---|---|
| Company | Normalized company name |
| Country | Initially Netherlands |
| Industry | Enriched or manually reviewed |
| Company Size | If available |
| Company Type | Internal AI Adoption, AI-Enabled Product, AI-Native Company, Unknown |
| AI Execution Roles | Count and titles |
| AI Product Roles | Count and titles |
| Role Classification | Flat classification |
| Technology Signals | Extracted GenAI/application AI terms |
| Use Case Clues | Extracted use case hints |
| Evidence Links | Source job URLs |
| Why Interesting | Short human-readable reason |
| Review Status | New, reviewed, relevant, not relevant |

---

## MVP Recommendation

Start with a Netherlands-first company intelligence dataset focused on companies hiring for AI execution and AI product roles.

The first version should:

- Track only AI execution and AI product roles
- Detect GenAI/application AI technology signals
- Exclude generic data, analytics, and classic ML roles from the primary signal set
- Store raw job data and evidence links
- Produce compact company intelligence records
- Use simple tags and flat classifications instead of scoring
- Prioritize companies adopting AI internally or embedding AI into existing products
- Keep country-specific logic configurable so Germany, Denmark, Austria, and Switzerland can be added later

Success for the MVP means producing a reviewed list of companies where the hiring evidence clearly suggests active AI investment.

---

## Future Enhancements

Not required initially.

Potential additions:

- Additional countries
- Trend analysis over time
- Repeated hiring detection
- AI leadership roles
- MLOps and AI platform roles
- Data foundation roles as secondary signals
- Company scoring
- Funding and growth signals
- News and press release signals
- Website AI messaging detection
- CRM export or account prioritization workflow
