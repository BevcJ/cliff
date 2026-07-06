ENRICHMENT_VERSION = "v1"
PROMPT_VERSION = "v5"
DEFAULT_COMPANY_ENRICHMENT_MODEL = "gpt-5.4-mini"
COMPANY_ENRICHMENT_RECORD_TYPE = "company_enrichment_extract"
COMPANY_ENRICHMENT_PROMPT = """Research the company using web search and extract company-level enrichment data.
You must use web search before returning a result for every company.
Use the provided company and hiring context only to identify the correct company and relevant search intent.
First research company-level facts from public web sources. Only after that, use the provided hiring context to support AI/tech-forward signal fields.
Return only information supported by public sources.
Do not guess, estimate, or infer facts from stereotypes.
Do not infer private email addresses from name or domain patterns.
Generic public company inboxes are allowed as fallback contacts with role generic_company_email.
Contact research is required. After identifying the correct company, run targeted web searches for public named contacts responsible for technology, data, AI, ML, engineering, or technical hiring.
Search for combinations such as: "{company} CTO LinkedIn", "{company} Head of AI LinkedIn", "{company} Head of Data Science LinkedIn", "{company} VP Engineering LinkedIn", "{company} machine learning lead LinkedIn", "{company} data engineering lead LinkedIn", "{company} technical founder LinkedIn", "{company} AI team contact", and "{company} leadership team".
Use the job context to guide contact search intent, for example AI Engineer, AI Execution Role, Data Science, ML, or AI team.
Contact research must be two-pass: first find relevant people from official about/team/leadership pages, job context, speaker pages, news, or reputable public pages; then use each discovered name and title as a search lead to find the person's LinkedIn profile URL or public non-generic work email.
For every named lead, search exact combinations such as "{person name}" "{company}" LinkedIn, "{person name}" "{title}" "{company}" LinkedIn, and site:linkedin.com/in "{person name}" "{company}".
Contacts are not limited to email addresses. A LinkedIn person profile URL is a first-class contact result.
Prefer contacts in this order: named relevant person with LinkedIn profile URL; named relevant person with public non-generic work email; named relevant person from official team, leadership, speaker, or reputable public pages; generic company inbox only as fallback.
Return multiple credible contacts when found. Do not stop after the first contact.
Do not stop at an about/team page when it provides only names and titles. Use those names and titles to search for LinkedIn person profiles.
Do not infer LinkedIn URLs from names. Only return LinkedIn person profile URLs that are found in public search results or public pages.
LinkedIn company, jobs, search, or post URLs are not valid contact profile URLs.
Find the official company website and LinkedIn company page when available.
Prefer sources in this order: official company domain, official careers/team/contact pages, LinkedIn company/profile pages surfaced by search, reputable business/funding registries, reputable news/funding pages, other credible public pages.
Avoid low-trust contact aggregator sources such as ContactOut, RocketReach, Apollo, Hunter, and Lusha for named-person emails. Do not return named-person emails from those sources.
Do not use the provided ATS/job-board URL as the only source for company_description, industry, company_size, founded_year, company_type, or funding_summary.
ATS/job-board URLs may support ai_tech_forward_signal and ai_tech_forward_reason, but they are insufficient for core company facts.
Company type guidance:
- Use traditional_company for banks, energy companies, education groups, distributors, resellers, telecom operators, and other incumbents unless public sources show a distinct owned software/SaaS/platform product business.
- Use agency_consulting for consultancies, implementation partners, agencies, data boutiques, professional services, and solution-delivery firms.
- Use product_company for companies whose public sources show owned software, SaaS, hardware, platform, or technology products sold to customers.
- Use ai_native only when AI is core to the company's product, platform, or primary market positioning, not merely because it has AI-related job postings.
Company size must be one of these sortable buckets when supported by public sources: 0-50, 51-100, 101-500, or 501+. Map sourced ranges or exact employee counts into the closest bucket; return null if the public size cannot be confidently mapped.
Every non-null factual field should include source URL(s) where possible.
Every contact should include source URL(s) where possible.
Do not extract job ad age or job posting age.
Do not generate priority, offer recommendation, or outreach reason.
If a field is not present in public sources, return null or an empty list.
""".strip()
