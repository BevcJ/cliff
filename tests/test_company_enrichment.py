from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from ai_hiring_radar.company_enrichment import (
    COMPANY_ENRICHMENT_PROMPT,
    DEFAULT_COMPANY_ENRICHMENT_MODEL,
    PROMPT_VERSION,
    AiTechForwardSignal,
    CompanyContact,
    CompanyContactRole,
    CompanyEnrichment,
    CompanySizeRange,
    CompanyType,
    PydanticAICompanyEnrichmentExtractor,
    build_enrichment_input,
    build_enrichment_record,
    enrichment_quality_error,
    group_candidate_records_by_company,
    needs_quality_retry,
    normalize_source_urls,
    prepare_enrichment_for_record,
    run_company_enrichment,
    sanitize_low_trust_named_contact_emails,
)
from ai_hiring_radar.company_enrichment.text import is_ats_url
from ai_hiring_radar.llm_usage import LLMCallResult, LLMUsage
from ai_hiring_radar.storage_json import read_jsonl, write_processed_jsonl


def _company(**overrides: Any) -> dict[str, Any]:
    company = {
        "record_type": "company_intelligence_title_only",
        "company": "Acme AI",
        "countries": ["Netherlands"],
        "role_classification": "AI Execution Role",
        "ai_execution_titles": ["AI Engineer"],
        "ai_product_titles": [],
        "ai_role_title_counts": [{"title": "AI Engineer", "count": 1}],
        "matched_search_terms": ["AI Engineer"],
        "evidence_urls": ["https://jobs.example.com/ai-engineer"],
        "sources": ["lever"],
        "evidence_quality": ["title_only_ats_listing"],
        "why_interesting": "Title-only signal.",
    }
    company.update(overrides)
    return company


def _candidate(**overrides: Any) -> dict[str, Any]:
    candidate = {
        "record_type": "job_candidate",
        "job_id": "job-123",
        "source": "lever",
        "platform": "lever",
        "platform_company_slug": "acme-ai",
        "platform_job_id": "job-ai-engineer",
        "company_normalized": "Acme AI",
        "job_title_raw": "Senior AI Engineer",
        "job_title_normalized": "AI Engineer",
        "role_group": "AI Execution Role",
        "source_url": "https://jobs.example.com/ai-engineer",
        "job_url": "https://jobs.example.com/ai-engineer",
        "team": "Engineering",
        "department": "AI",
        "location": "Amsterdam, Netherlands",
        "description": "Full description must not be sent for company enrichment.",
        "description_plain": "Full plain description must not be sent.",
        "job_description_sections": [{"name": "About", "value": "Full text."}],
        "lists": [{"text": "Responsibilities", "content": "Full text."}],
    }
    candidate.update(overrides)
    return candidate


def test_company_enrichment_accepts_enum_values() -> None:
    enrichment = CompanyEnrichment.model_validate(
        {
            "company_type": "product_company",
            "ai_tech_forward_signal": "moderate",
            "contacts": [
                {
                    "name": "Ada Lovelace",
                    "role": "cto",
                    "title": "CTO",
                    "source_urls": ["https://example.com/team"],
                }
            ],
        }
    )

    assert enrichment.company_type is CompanyType.PRODUCT_COMPANY
    assert enrichment.ai_tech_forward_signal is AiTechForwardSignal.MODERATE
    assert enrichment.contacts == [
        CompanyContact(
            name="Ada Lovelace",
            role=CompanyContactRole.CTO,
            title="CTO",
            source_urls=["https://example.com/team"],
        )
    ]


def test_company_enrichment_rejects_invalid_enum_values() -> None:
    try:
        CompanyEnrichment.model_validate({"company_type": "spaceship"})
    except ValidationError:
        return

    raise AssertionError("Invalid enum value should fail validation.")


def test_company_enrichment_defaults_missing_values_and_generic_contact() -> None:
    enrichment = CompanyEnrichment.model_validate(
        {
            "company_description": " ",
            "founded_year": "",
            "company_type": "",
            "ai_tech_forward_signal": " ",
            "company_description_source_urls": None,
            "contacts": [
                {
                    "name": "",
                    "role": "generic_company_email",
                    "title": " ",
                    "email": "info@example.com",
                    "source_urls": ["https://example.com/contact"],
                }
            ],
        }
    )

    assert enrichment.company_description is None
    assert enrichment.founded_year is None
    assert enrichment.company_type is None
    assert enrichment.ai_tech_forward_signal is None
    assert enrichment.company_description_source_urls == []
    assert enrichment.contacts == [
        CompanyContact(
            role=CompanyContactRole.GENERIC_COMPANY_EMAIL,
            email="info@example.com",
            source_urls=["https://example.com/contact"],
        )
    ]


def test_company_enrichment_prompt_contains_locked_rules() -> None:
    assert PROMPT_VERSION == "v5"
    assert DEFAULT_COMPANY_ENRICHMENT_MODEL == "gpt-5.4-mini"
    assert "You must use web search" in COMPANY_ENRICHMENT_PROMPT
    assert "Contact research is required" in COMPANY_ENRICHMENT_PROMPT
    assert "Contact research must be two-pass" in COMPANY_ENRICHMENT_PROMPT
    assert "Return multiple credible contacts" in COMPANY_ENRICHMENT_PROMPT
    assert "Do not stop at an about/team page" in COMPANY_ENRICHMENT_PROMPT
    assert "LinkedIn person profile URL is a first-class contact result" in (
        COMPANY_ENRICHMENT_PROMPT
    )
    assert "Company size must be one of these sortable buckets" in (
        COMPANY_ENRICHMENT_PROMPT
    )
    assert "Do not guess" in COMPANY_ENRICHMENT_PROMPT
    assert "Do not infer private email addresses" in COMPANY_ENRICHMENT_PROMPT
    assert "generic_company_email" in COMPANY_ENRICHMENT_PROMPT
    assert "Use traditional_company for banks" in COMPANY_ENRICHMENT_PROMPT
    assert "Use agency_consulting for consultancies" in COMPANY_ENRICHMENT_PROMPT
    assert "Use ai_native only when AI is core" in COMPANY_ENRICHMENT_PROMPT
    assert "ATS/job-board URLs may support ai_tech_forward_signal" in (
        COMPANY_ENRICHMENT_PROMPT
    )
    assert "Do not extract job ad age" in COMPANY_ENRICHMENT_PROMPT
    assert "Do not generate priority" in COMPANY_ENRICHMENT_PROMPT


def test_normalize_source_urls_removes_blank_malformed_and_duplicate_values() -> None:
    assert normalize_source_urls(
        [
            " https://example.com/about ",
            "",
            "https://example.com/about",
            "ftp://example.com/file",
            "not-a-url",
            123,
        ]
    ) == ["https://example.com/about"]


def test_company_enrichment_repairs_common_source_field_aliases() -> None:
    enrichment = CompanyEnrichment.model_validate(
        {
            "industry": "IoT connectivity software",
            "industry_sourceurls": ["https://www.1nce.com/"],
            "funding_summary": "Raised funding.",
            "funding_source_urls": ["https://example.com/funding"],
        }
    )

    assert enrichment.industry_source_urls == ["https://www.1nce.com/"]
    assert enrichment.funding_summary_source_urls == ["https://example.com/funding"]


def test_company_contact_sanitizes_invalid_email_and_linkedin_url() -> None:
    contact = CompanyContact.model_validate(
        {
            "role": "generic_company_email",
            "email": "https://aionbank.jobs.personio.com",
            "linkedin_url": "https://example.com/not-linkedin",
        }
    )

    assert contact.email is None
    assert contact.linkedin_url is None


def test_company_contact_keeps_valid_linkedin_url() -> None:
    contact = CompanyContact.model_validate(
        {"linkedin_url": "https://www.linkedin.com/in/ada-lovelace"}
    )

    assert contact.linkedin_url == "https://www.linkedin.com/in/ada-lovelace"
    assert contact.source_urls == ["https://www.linkedin.com/in/ada-lovelace"]


def test_company_contact_rejects_non_person_linkedin_url() -> None:
    contact = CompanyContact.model_validate(
        {"linkedin_url": "https://www.linkedin.com/company/acme-ai"}
    )

    assert contact.linkedin_url is None


def test_company_size_normalizes_to_sortable_bucket() -> None:
    assert (
        CompanyEnrichment(company_size="86 employees").company_size
        is CompanySizeRange.FROM_51_TO_100
    )
    assert (
        CompanyEnrichment(company_size="51-200 employees").company_size
        is CompanySizeRange.FROM_101_TO_500
    )
    assert (
        CompanyEnrichment(company_size="1,001-5,000 employees").company_size
        is CompanySizeRange.FROM_501_UP
    )
    assert CompanyEnrichment(company_size="unknown").company_size is None


def test_company_contact_downgrades_cto_role_when_title_is_finance() -> None:
    contact = CompanyContact.model_validate(
        {"name": "Niels", "role": "cto", "title": "Chief Financial Officer"}
    )

    assert contact.role is CompanyContactRole.OTHER


def test_build_enrichment_input_includes_compact_company_and_candidate_context() -> None:
    candidates_by_company = group_candidate_records_by_company([_candidate()])
    enrichment_input = build_enrichment_input(
        _company(),
        candidates_by_company["acme ai"],
    )

    assert enrichment_input is not None
    assert enrichment_input["company"] == "Acme AI"
    assert enrichment_input["countries"] == ["Netherlands"]
    assert enrichment_input["role_classification"] == "AI Execution Role"
    assert enrichment_input["ai_execution_titles"] == ["AI Engineer"]
    assert enrichment_input["ai_role_title_counts"] == [
        {"title": "AI Engineer", "count": 1}
    ]
    assert enrichment_input["evidence_urls"] == [
        "https://jobs.example.com/ai-engineer"
    ]
    assert enrichment_input["sources"] == ["lever"]
    assert enrichment_input["candidate_context"] == [
        {
            "job_title_raw": "Senior AI Engineer",
            "job_url": "https://jobs.example.com/ai-engineer",
            "platform": "lever",
            "location": "Amsterdam, Netherlands",
            "team": "Engineering",
            "department": "AI",
        }
    ]
    assert "description" not in enrichment_input["candidate_context"][0]
    assert "description_plain" not in enrichment_input["candidate_context"][0]
    assert "job_description_sections" not in enrichment_input["candidate_context"][0]
    assert "lists" not in enrichment_input["candidate_context"][0]


def test_build_enrichment_input_skips_company_without_name() -> None:
    assert build_enrichment_input(_company(company=" ")) is None


def test_build_enrichment_record_excludes_raw_content_and_unions_source_urls() -> None:
    record = build_enrichment_record(
        company_record=_company(raw_search_results=[{"title": "raw"}]),
        enrichment=CompanyEnrichment(
            company_description="Acme AI builds logistics automation software.",
            company_description_source_urls=["https://example.com/about"],
            company_size="51-200 employees",
            company_size_source_urls=["https://www.linkedin.com/company/acme-ai"],
            contacts=[
                CompanyContact(
                    name="Ada Lovelace",
                    role=CompanyContactRole.CTO,
                    title="CTO",
                    linkedin_url="https://www.linkedin.com/in/ada-lovelace",
                    source_urls=["https://example.com/team"],
                ),
                CompanyContact(
                    role=CompanyContactRole.GENERIC_COMPANY_EMAIL,
                    email="info@example.com",
                    source_urls=["https://example.com/contact"],
                ),
            ],
            source_urls=["https://example.com/about", "https://example.com/news"],
        ),
        model="gpt-5-mini",
        enriched_at="2026-07-02T10:00:00Z",
    )

    assert record["record_type"] == "company_enrichment_extract"
    assert record["model"] == "gpt-5-mini"
    assert record["company"] == "Acme AI"
    assert record["company_key"] == "acme-ai"
    assert record["company_description"] == (
        "Acme AI builds logistics automation software."
    )
    assert record["company_size"] == "101-500"
    assert record["contacts"][1]["role"] == "generic_company_email"
    assert record["source_urls"] == [
        "https://example.com/about",
        "https://www.linkedin.com/company/acme-ai",
        "https://example.com/team",
        "https://example.com/contact",
        "https://example.com/news",
    ]
    assert record["quality_warnings"] == []
    assert "raw_search_results" not in record
    assert "raw_llm_response" not in record
    assert "search_result_dump" not in record
    assert "description" not in record
    assert "job_description_sections" not in record


def test_quality_error_rejects_core_facts_with_only_ats_sources() -> None:
    enrichment = CompanyEnrichment(
        company_description="AstrAfy has public AI hiring activity.",
        company_description_source_urls=["https://astrafy.jobs.personio.com"],
        source_urls=["https://astrafy.jobs.personio.com"],
    )

    assert enrichment_quality_error(company_record=_company(), enrichment=enrichment) == (
        "company_description is populated but has no non-ATS source URL; "
        "company facts require web sources beyond job boards."
    )


def test_quality_error_rejects_empty_job_board_only_results() -> None:
    enrichment = CompanyEnrichment(
        ai_tech_forward_signal=AiTechForwardSignal.MODERATE,
        ai_tech_forward_reason="Hiring context shows AI roles.",
        ai_tech_forward_source_urls=["https://astrafy.jobs.personio.com"],
        source_urls=["https://astrafy.jobs.personio.com"],
    )

    assert enrichment_quality_error(company_record=_company(), enrichment=enrichment) == (
        "No non-ATS source URL returned; web search likely did not verify "
        "company-level facts."
    )


def test_teamtailor_urls_are_ats_urls() -> None:
    assert is_ats_url("https://acme.teamtailor.com/jobs/123-ai-engineer") is True


def test_quality_retry_requests_contact_research_for_name_only_contacts() -> None:
    enrichment = CompanyEnrichment(
        company_description="Acme AI builds software.",
        company_description_source_urls=["https://example.com/about"],
        contacts=[
            CompanyContact(
                name="Ada Lovelace",
                role=CompanyContactRole.CTO,
                title="CTO",
                source_urls=["https://example.com/team"],
            )
        ],
        source_urls=["https://example.com/about"],
    )

    retry_reason = needs_quality_retry(enrichment)

    assert retry_reason is not None
    assert "LinkedIn profile or non-generic public work email" in retry_reason


def test_quality_retry_requests_contact_research_for_generic_only_contacts() -> None:
    enrichment = CompanyEnrichment(
        company_description="Acme AI builds software.",
        company_description_source_urls=["https://example.com/about"],
        contacts=[
            CompanyContact(
                role=CompanyContactRole.GENERIC_COMPANY_EMAIL,
                email="info@example.com",
                source_urls=["https://example.com/contact"],
            )
        ],
        source_urls=["https://example.com/about"],
    )

    assert needs_quality_retry(enrichment) is not None


def test_quality_retry_accepts_named_linkedin_or_non_generic_email_contact() -> None:
    linkedin_enrichment = CompanyEnrichment(
        company_description="Acme AI builds software.",
        company_description_source_urls=["https://example.com/about"],
        contacts=[
            CompanyContact(
                name="Ada Lovelace",
                linkedin_url="https://www.linkedin.com/in/ada-lovelace",
            )
        ],
        source_urls=["https://example.com/about"],
    )
    email_enrichment = CompanyEnrichment(
        company_description="Acme AI builds software.",
        company_description_source_urls=["https://example.com/about"],
        contacts=[CompanyContact(name="Ada Lovelace", email="ada@example.com")],
        source_urls=["https://example.com/about"],
    )

    assert needs_quality_retry(linkedin_enrichment) is None
    assert needs_quality_retry(email_enrichment) is None


def test_prepare_enrichment_removes_ats_only_core_fields_but_keeps_ai_signal() -> None:
    prepared = prepare_enrichment_for_record(
        company_record=_company(company="AstrAfy"),
        enrichment=CompanyEnrichment(
            company_description="AstrAfy has public AI hiring activity.",
            company_description_source_urls=["https://astrafy.jobs.personio.com"],
            ai_tech_forward_signal=AiTechForwardSignal.STRONG,
            ai_tech_forward_reason="Hiring context includes GenAI roles.",
            ai_tech_forward_source_urls=["https://astrafy.jobs.personio.com"],
            source_urls=["https://astrafy.jobs.personio.com"],
        ),
    )

    assert prepared.enrichment is not None
    assert prepared.enrichment.company_description is None
    assert prepared.enrichment.company_description_source_urls == []
    assert prepared.enrichment.ai_tech_forward_signal is AiTechForwardSignal.STRONG
    assert prepared.failed is False
    assert prepared.quality_warnings == (
        "Removed company_description because it was supported only by ATS/job-board sources.",
    )


def test_low_trust_named_contact_email_is_removed() -> None:
    enrichment = sanitize_low_trust_named_contact_emails(
        CompanyEnrichment(
            company_description="Acme AI builds software.",
            company_description_source_urls=["https://example.com/about"],
            contacts=[
                CompanyContact(
                    name="Ada Lovelace",
                    role=CompanyContactRole.CTO,
                    email="ada@example.com",
                    source_urls=["https://contactout.com/company/acme"],
                ),
                CompanyContact(
                    role=CompanyContactRole.GENERIC_COMPANY_EMAIL,
                    email="info@example.com",
                    source_urls=["https://example.com/contact"],
                ),
            ],
        )
    )

    assert enrichment.contacts[0].email is None
    assert enrichment.contacts[1].email == "info@example.com"


def test_prepare_enrichment_removes_empty_contacts() -> None:
    prepared = prepare_enrichment_for_record(
        company_record=_company(),
        enrichment=CompanyEnrichment(
            company_description="Acme AI builds software.",
            company_description_source_urls=["https://example.com/about"],
            contacts=[CompanyContact(role=CompanyContactRole.GENERIC_COMPANY_EMAIL)],
            source_urls=["https://example.com/about"],
        ),
    )

    assert prepared.enrichment is not None
    assert prepared.enrichment.contacts == []
    assert prepared.quality_warnings == (
        "Removed generic company email contact without a valid email.",
    )


def test_prepare_enrichment_keeps_low_trust_company_facts_with_warning() -> None:
    prepared = prepare_enrichment_for_record(
        company_record=_company(),
        enrichment=CompanyEnrichment(
            company_size="86 employees",
            company_size_source_urls=[
                "https://rocketreach.co/certify360-edtech-group-profile_b697a9adc97d9930"
            ],
            source_urls=[
                "https://rocketreach.co/certify360-edtech-group-profile_b697a9adc97d9930"
            ],
        ),
    )

    assert prepared.enrichment is not None
    assert prepared.enrichment.company_size is CompanySizeRange.FROM_51_TO_100
    assert prepared.quality_warnings == (
        "Kept company_size although it is supported only by low-trust directory sources.",
    )


def test_prepare_enrichment_warns_for_named_contact_from_low_trust_source() -> None:
    prepared = prepare_enrichment_for_record(
        company_record=_company(),
        enrichment=CompanyEnrichment(
            company_description="Certify360 is an EdTech group.",
            company_description_source_urls=["https://certify360.com/"],
            contacts=[
                CompanyContact(
                    name="Ada Lovelace",
                    title="CEO",
                    source_urls=["https://rocketreach.co/example-management"],
                )
            ],
            source_urls=["https://certify360.com/"],
        ),
    )

    assert prepared.enrichment is not None
    assert prepared.enrichment.contacts[0].name == "Ada Lovelace"
    assert prepared.quality_warnings == (
        "Kept named contact supported only by low-trust directory sources.",
    )


def test_run_company_enrichment_writes_jsonl_with_fake_extractor(tmp_path) -> None:
    write_processed_jsonl(
        "companies_2026-07-02.jsonl",
        [_company()],
        data_dir=tmp_path,
    )
    write_processed_jsonl(
        "job_candidates_2026-07-02.jsonl",
        [_candidate()],
        data_dir=tmp_path,
    )

    def fake_extractor(
        enrichment_input: dict[str, Any],
    ) -> LLMCallResult[CompanyEnrichment]:
        assert enrichment_input["company"] == "Acme AI"
        assert enrichment_input["candidate_context"][0]["job_title_raw"] == (
            "Senior AI Engineer"
        )
        return LLMCallResult(
            output=CompanyEnrichment(
                company_type=CompanyType.PRODUCT_COMPANY,
                company_type_source_urls=["https://example.com/about"],
                contacts=[
                    CompanyContact(
                        name="Ada Lovelace",
                        linkedin_url="https://www.linkedin.com/in/ada-lovelace",
                    )
                ],
                source_urls=["https://example.com/about"],
            ),
            usage=LLMUsage(
                input_tokens=2_000,
                cache_read_tokens=500,
                output_tokens=1_000,
                requests=1,
                tool_calls=1,
            ),
        )

    result = run_company_enrichment(
        "2026-07-02",
        extractor=fake_extractor,
        model="gpt-5-mini",
        data_dir=tmp_path,
        clock=lambda: "2026-07-02T10:00:00Z",
        show_progress=False,
    )

    assert result.companies_read == 1
    assert result.processable_count == 1
    assert result.enriched_count == 1
    assert result.skipped_count == 0
    assert result.validation_error_count == 0
    assert result.llm_error_count == 0
    assert result.quality_error_count == 0
    assert result.llm_usage.input_tokens == 2_000
    assert result.llm_usage.cache_read_tokens == 500
    assert result.llm_usage.output_tokens == 1_000
    assert result.llm_usage.tool_calls == 1
    assert result.llm_estimated_cost_usd == 0.0123875
    records = read_jsonl(result.output_path)
    assert records[0]["company_type"] == "product_company"
    assert records[0]["enriched_at"] == "2026-07-02T10:00:00Z"
    assert records[0]["llm_usage"]["tool_calls"] == 1
    assert records[0]["llm_pricing_model"] == "gpt-5-mini"
    assert records[0]["llm_estimated_cost_usd"] == 0.0123875


def test_run_company_enrichment_counts_skips_and_errors(tmp_path) -> None:
    write_processed_jsonl(
        "companies_2026-07-02.jsonl",
        [
            _company(company="Valid Co"),
            _company(company="Invalid Output Co"),
            _company(company="LLM Error Co"),
            _company(company=" "),
            "not-a-dict",  # type: ignore[list-item]
        ],
        data_dir=tmp_path,
    )

    def fake_extractor(enrichment_input: dict[str, Any]) -> dict[str, Any]:
        if enrichment_input["company"] == "Invalid Output Co":
            return {"company_type": "spaceship"}
        if enrichment_input["company"] == "LLM Error Co":
            raise RuntimeError("model unavailable")
        return {
            "company_type": "product_company",
            "company_type_source_urls": ["https://example.com/about"],
            "contacts": [
                {
                    "name": "Ada Lovelace",
                    "linkedin_url": "https://www.linkedin.com/in/ada-lovelace",
                }
            ],
            "source_urls": ["https://example.com/about"],
        }

    result = run_company_enrichment(
        "2026-07-02",
        extractor=fake_extractor,
        model="gpt-5-mini",
        data_dir=tmp_path,
        clock=lambda: "2026-07-02T10:00:00Z",
        show_progress=False,
    )

    assert result.companies_read == 5
    assert result.processable_count == 3
    assert result.enriched_count == 1
    assert result.skipped_count == 2
    assert result.validation_error_count == 1
    assert result.llm_error_count == 1
    assert result.quality_error_count == 0
    assert result.validation_error_samples[0].company == "Invalid Output Co"
    assert result.llm_error_samples[0].company == "LLM Error Co"
    assert len(read_jsonl(result.output_path)) == 1


def test_run_company_enrichment_resumes_existing_output(tmp_path) -> None:
    done_company = _company(company="Acme AI")
    new_company = _company(company="Beta AI")
    write_processed_jsonl(
        "companies_2026-07-02.jsonl",
        [done_company, new_company],
        data_dir=tmp_path,
    )
    write_processed_jsonl(
        "company_enrichment_extracts_2026-07-02.jsonl",
        [
            build_enrichment_record(
                company_record=done_company,
                enrichment=CompanyEnrichment(company_type=CompanyType.PRODUCT_COMPANY),
                model="old-model",
                enriched_at="2026-07-01T10:00:00Z",
            )
        ],
        data_dir=tmp_path,
    )
    calls: list[str] = []

    def fake_extractor(enrichment_input: dict[str, Any]) -> dict[str, Any]:
        calls.append(enrichment_input["company"])
        return {
            "company_type": "product_company",
            "company_type_source_urls": ["https://example.com/about"],
            "contacts": [
                {
                    "name": "Ada Lovelace",
                    "linkedin_url": "https://www.linkedin.com/in/ada-lovelace",
                }
            ],
            "source_urls": ["https://example.com/about"],
        }

    result = run_company_enrichment(
        "2026-07-02",
        extractor=fake_extractor,
        model="test-model",
        data_dir=tmp_path,
        clock=lambda: "2026-07-02T10:00:00Z",
        show_progress=False,
    )

    assert calls == ["Beta AI"]
    assert result.companies_read == 2
    assert result.already_processed_count == 1
    assert result.enriched_count == 1
    records = read_jsonl(result.output_path)
    assert [record["company_key"] for record in records] == ["acme-ai", "beta-ai"]


def test_run_company_enrichment_filters_by_any_country_before_limit(tmp_path) -> None:
    write_processed_jsonl(
        "companies_2026-07-02.jsonl",
        [
            _company(company="UK AI", countries=["United Kingdom"]),
            _company(company="Nordic AI", countries=["United Kingdom", "Denmark"]),
            _company(company="Dutch AI", countries=["Netherlands"]),
        ],
        data_dir=tmp_path,
    )
    calls: list[str] = []

    def fake_extractor(enrichment_input: dict[str, Any]) -> dict[str, Any]:
        calls.append(enrichment_input["company"])
        return {
            "company_type": "product_company",
            "company_type_source_urls": ["https://example.com/about"],
            "contacts": [
                {
                    "name": "Ada Lovelace",
                    "linkedin_url": "https://www.linkedin.com/in/ada-lovelace",
                }
            ],
            "source_urls": ["https://example.com/about"],
        }

    result = run_company_enrichment(
        "2026-07-02",
        extractor=fake_extractor,
        model="test-model",
        data_dir=tmp_path,
        country_names=["Denmark", "Netherlands"],
        limit=1,
        clock=lambda: "2026-07-02T10:00:00Z",
        show_progress=False,
    )

    assert calls == ["Nordic AI"]
    assert result.companies_read == 1
    assert result.processable_count == 1
    assert result.enriched_count == 1
    records = read_jsonl(result.output_path)
    assert [record["company"] for record in records] == ["Nordic AI"]


def test_run_company_enrichment_retries_name_only_contacts_and_merges_linkedin(
    tmp_path,
) -> None:
    write_processed_jsonl(
        "companies_2026-07-02.jsonl",
        [_company(company="Acme AI")],
        data_dir=tmp_path,
    )
    calls: list[dict[str, Any]] = []

    def fake_extractor(enrichment_input: dict[str, Any]) -> dict[str, Any]:
        calls.append(enrichment_input)
        if len(calls) == 1:
            return {
                "company_description": "Acme AI builds logistics automation software.",
                "company_description_source_urls": ["https://example.com/about"],
                "company_type": "product_company",
                "company_type_source_urls": ["https://example.com/about"],
                "contacts": [
                    {
                        "name": "Ada Lovelace",
                        "role": "cto",
                        "title": "CTO",
                        "source_urls": ["https://example.com/team"],
                    }
                ],
                "source_urls": ["https://example.com/about"],
            }
        assert calls[1]["quality_retry"]["previous_contacts"] == [
            {
                "name": "Ada Lovelace",
                "title": "CTO",
                "role": "cto",
                "source_urls": ["https://example.com/team"],
            }
        ]
        assert "LinkedIn" in calls[1]["quality_retry"]["instructions"]
        return {
            "contacts": [
                {
                    "name": "Ada Lovelace",
                    "role": "cto",
                    "title": "CTO",
                    "linkedin_url": "https://www.linkedin.com/in/ada-lovelace",
                }
            ]
        }

    result = run_company_enrichment(
        "2026-07-02",
        extractor=fake_extractor,
        model="test-model",
        data_dir=tmp_path,
        clock=lambda: "2026-07-02T10:00:00Z",
        show_progress=False,
    )

    assert len(calls) == 2
    assert result.enriched_count == 1
    records = read_jsonl(result.output_path)
    assert records[0]["company_description"] == (
        "Acme AI builds logistics automation software."
    )
    assert records[0]["company_type"] == "product_company"
    assert records[0]["contacts"] == [
        {
            "email": None,
            "linkedin_url": "https://www.linkedin.com/in/ada-lovelace",
            "name": "Ada Lovelace",
            "role": "cto",
            "source_urls": ["https://www.linkedin.com/in/ada-lovelace"],
            "title": "CTO",
        }
    ]
    assert records[0]["quality_warnings"] == []


def test_run_company_enrichment_warns_when_contact_retry_still_has_no_linkedin(
    tmp_path,
) -> None:
    write_processed_jsonl(
        "companies_2026-07-02.jsonl",
        [_company(company="Acme AI")],
        data_dir=tmp_path,
    )

    def fake_extractor(enrichment_input: dict[str, Any]) -> dict[str, Any]:
        return {
            "company_description": "Acme AI builds logistics automation software.",
            "company_description_source_urls": ["https://example.com/about"],
            "contacts": [
                {
                    "name": "Ada Lovelace",
                    "role": "cto",
                    "title": "CTO",
                    "source_urls": ["https://example.com/team"],
                }
            ],
            "source_urls": ["https://example.com/about"],
        }

    result = run_company_enrichment(
        "2026-07-02",
        extractor=fake_extractor,
        model="test-model",
        data_dir=tmp_path,
        clock=lambda: "2026-07-02T10:00:00Z",
        show_progress=False,
    )

    assert result.enriched_count == 1
    records = read_jsonl(result.output_path)
    assert records[0]["quality_warnings"] == [
        "No named contact with LinkedIn profile or non-generic public work email found after contact retry."
    ]


def test_run_company_enrichment_counts_quality_errors(tmp_path) -> None:
    write_processed_jsonl(
        "companies_2026-07-02.jsonl",
        [_company(company="AstrAfy")],
        data_dir=tmp_path,
    )

    def fake_extractor(enrichment_input: dict[str, Any]) -> dict[str, Any]:
        return {
            "company_description": "AstrAfy has public hiring activity.",
            "company_description_source_urls": ["https://astrafy.jobs.personio.com"],
            "source_urls": ["https://astrafy.jobs.personio.com"],
        }

    result = run_company_enrichment(
        "2026-07-02",
        extractor=fake_extractor,
        model="gpt-5.4-mini",
        data_dir=tmp_path,
        clock=lambda: "2026-07-02T10:00:00Z",
        show_progress=False,
    )

    assert result.enriched_count == 0
    assert result.quality_error_count == 1
    assert result.quality_error_samples[0].company == "AstrAfy"
    assert not read_jsonl(result.output_path)


def test_run_company_enrichment_writes_partial_salvaged_records(tmp_path) -> None:
    write_processed_jsonl(
        "companies_2026-07-02.jsonl",
        [_company(company="AstrAfy")],
        data_dir=tmp_path,
    )

    calls = 0

    def fake_extractor(enrichment_input: dict[str, Any]) -> LLMCallResult[dict[str, Any]]:
        nonlocal calls
        calls += 1
        assert calls == 1 or "quality_retry" in enrichment_input
        return LLMCallResult(
            output={
                "company_description": "AstrAfy has public AI hiring activity.",
                "company_description_source_urls": [
                    "https://astrafy.jobs.personio.com"
                ],
                "ai_tech_forward_signal": "strong",
                "ai_tech_forward_reason": "Hiring context includes GenAI roles.",
                "ai_tech_forward_source_urls": ["https://astrafy.jobs.personio.com"],
                "source_urls": ["https://astrafy.jobs.personio.com"],
            },
            usage=LLMUsage(
                input_tokens=1_000,
                output_tokens=100,
                requests=1,
                tool_calls=1,
            ),
        )

    result = run_company_enrichment(
        "2026-07-02",
        extractor=fake_extractor,
        model="gpt-5.4-mini",
        data_dir=tmp_path,
        clock=lambda: "2026-07-02T10:00:00Z",
        show_progress=False,
    )

    assert calls == 2
    assert result.enriched_count == 1
    assert result.quality_error_count == 0
    assert result.llm_usage.requests == 2
    assert result.llm_usage.tool_calls == 2
    assert result.llm_estimated_cost_usd == 0.0224
    records = read_jsonl(result.output_path)
    assert records[0]["company_description"] is None
    assert records[0]["ai_tech_forward_signal"] == "strong"
    assert records[0]["llm_usage"]["requests"] == 2
    assert records[0]["llm_usage"]["tool_calls"] == 2
    assert records[0]["llm_estimated_cost_usd"] == 0.0224
    assert records[0]["quality_warnings"] == [
        "Removed company_description because it was supported only by ATS/job-board sources."
    ]


def test_run_company_enrichment_dry_run_does_not_write_or_call_model(tmp_path) -> None:
    write_processed_jsonl(
        "companies_2026-07-02.jsonl",
        [_company()],
        data_dir=tmp_path,
    )

    result = run_company_enrichment(
        "2026-07-02",
        extractor=None,
        model="gpt-5-mini",
        data_dir=tmp_path,
        dry_run=True,
        show_progress=False,
    )

    assert result.dry_run is True
    assert result.processable_count == 1
    assert result.enriched_count == 0
    assert not result.output_path.exists()


def test_pydantic_ai_company_adapter_constructs_agent_with_web_search() -> None:
    calls: list[dict[str, Any]] = []

    class FakeAgent:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            calls.append({"args": args, "kwargs": kwargs})

        def run_sync(self, prompt: str) -> Any:
            assert "Company data:" in prompt

            class Result:
                output = CompanyEnrichment(company_type=CompanyType.PRODUCT_COMPANY)

            return Result()

    extractor = PydanticAICompanyEnrichmentExtractor(
        model="test-model",
        agent_factory=FakeAgent,
        native_tool_factory=lambda tool: {"native_tool": tool},
        web_search_tool_factory=lambda: {"tool": "web_search"},
    )

    assert calls == [
        {
            "args": ("test-model",),
            "kwargs": {
                "output_type": CompanyEnrichment,
                "instructions": COMPANY_ENRICHMENT_PROMPT,
                "capabilities": [{"native_tool": {"tool": "web_search"}}],
            },
        }
    ]
    call_result = extractor({"company": "Acme AI"})
    assert call_result.output.company_type is CompanyType.PRODUCT_COMPANY


def test_pydantic_ai_company_adapter_builds_azure_responses_model() -> None:
    calls: dict[str, Any] = {}

    class FakeProvider:
        def __init__(self, **kwargs: Any) -> None:
            calls["provider_kwargs"] = kwargs

    class FakeResponsesModel:
        def __init__(self, model: str, **kwargs: Any) -> None:
            calls["responses_model_instance"] = self
            calls["responses_model"] = {"model": model, "kwargs": kwargs}

    class FakeAgent:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            calls["agent_args"] = args
            calls["agent_kwargs"] = kwargs

    PydanticAICompanyEnrichmentExtractor(
        model="gpt-5-mini",
        azure_endpoint=(
            "https://dev-aibooking-openai.openai.azure.com/openai/responses?"
            "api-version=2025-04-01-preview"
        ),
        azure_api_key="azure-key",
        agent_factory=FakeAgent,
        azure_provider_factory=FakeProvider,
        openai_responses_model_factory=FakeResponsesModel,
        native_tool_factory=lambda tool: {"native_tool": tool},
        web_search_tool_factory=lambda: {"tool": "web_search"},
    )

    assert calls["provider_kwargs"] == {
        "azure_endpoint": "https://dev-aibooking-openai.openai.azure.com/",
        "api_key": "azure-key",
        "api_version": "2025-04-01-preview",
    }
    assert calls["responses_model"]["model"] == "gpt-5-mini"
    assert calls["agent_args"] == (calls["responses_model_instance"],)
    assert calls["agent_kwargs"]["output_type"] == CompanyEnrichment
    assert calls["agent_kwargs"]["capabilities"] == [
        {"native_tool": {"tool": "web_search"}}
    ]
