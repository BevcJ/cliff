from __future__ import annotations

from typing import Any

from ai_hiring_radar.company_enrichment.contracts import (
    CompanyEnrichment,
    PreparedCompanyEnrichment,
)
from ai_hiring_radar.company_enrichment.text import (
    clean_scalar,
    has_non_ats_source_url,
    is_low_trust_contact_source_url,
    normalize_source_urls,
)


CORE_FACT_FIELDS = (
    ("company_description", "company_description_source_urls"),
    ("industry", "industry_source_urls"),
    ("company_size", "company_size_source_urls"),
    ("founded_year", "founded_year_source_urls"),
    ("company_type", "company_type_source_urls"),
    ("funding_summary", "funding_summary_source_urls"),
)


def prepare_enrichment_for_record(
    *,
    company_record: dict[str, Any],
    enrichment: CompanyEnrichment,
) -> PreparedCompanyEnrichment:
    enrichment_dump = enrichment.model_dump(mode="json")
    warnings: list[str] = []

    _remove_ats_only_core_fields(enrichment_dump, warnings)
    _add_low_trust_field_warnings(enrichment_dump, warnings)
    _sanitize_contacts(enrichment_dump, warnings)

    prepared_enrichment = CompanyEnrichment.model_validate(enrichment_dump)
    if _has_useful_data(prepared_enrichment):
        return PreparedCompanyEnrichment(
            enrichment=prepared_enrichment,
            quality_warnings=tuple(warnings),
        )

    company = clean_scalar(company_record.get("company")) or "company"
    warnings.append(f"No usable enrichment data remained for {company}.")
    return PreparedCompanyEnrichment(
        enrichment=None,
        quality_warnings=tuple(warnings),
        failed=True,
    )


def needs_quality_retry(enrichment: CompanyEnrichment) -> str | None:
    for field, source_field in CORE_FACT_FIELDS:
        if getattr(enrichment, field) is not None and not has_non_ats_source_url(
            getattr(enrichment, source_field)
        ):
            return (
                f"{field} was supported only by ATS/job-board sources. "
                "Retry with broader web research."
            )

    if not has_non_ats_source_url(enrichment.source_urls):
        return "No non-ATS source URL returned. Retry with broader web research."

    return None


def sanitize_low_trust_named_contact_emails(
    enrichment: CompanyEnrichment,
) -> CompanyEnrichment:
    enrichment_dump = enrichment.model_dump(mode="json")
    _sanitize_contacts(enrichment_dump, [])
    return CompanyEnrichment.model_validate(enrichment_dump)


def enrichment_quality_error(
    *,
    company_record: dict[str, Any],
    enrichment: CompanyEnrichment,
) -> str | None:
    for field, source_field in CORE_FACT_FIELDS:
        if getattr(enrichment, field) is not None and not has_non_ats_source_url(
            getattr(enrichment, source_field)
        ):
            return (
                f"{field} is populated but has no non-ATS source URL; "
                "company facts require web sources beyond job boards."
            )

    if not has_non_ats_source_url(enrichment.source_urls):
        return (
            "No non-ATS source URL returned; web search likely did not verify "
            "company-level facts."
        )

    if not _has_core_fact(enrichment) and not enrichment.contacts:
        company = clean_scalar(company_record.get("company")) or "company"
        return f"No company facts or contacts returned for {company}."

    return None


def _has_core_fact(enrichment: CompanyEnrichment) -> bool:
    return any(getattr(enrichment, field) is not None for field, _ in CORE_FACT_FIELDS)


def _remove_ats_only_core_fields(
    enrichment_dump: dict[str, Any],
    warnings: list[str],
) -> None:
    for field, source_field in CORE_FACT_FIELDS:
        if enrichment_dump.get(field) is None:
            continue
        source_urls = normalize_source_urls(enrichment_dump.get(source_field))
        if has_non_ats_source_url(source_urls):
            continue
        enrichment_dump[field] = None
        enrichment_dump[source_field] = []
        warnings.append(
            f"Removed {field} because it was supported only by ATS/job-board sources."
        )


def _sanitize_contacts(
    enrichment_dump: dict[str, Any],
    warnings: list[str],
) -> None:
    contacts: list[dict[str, Any]] = []
    for contact in enrichment_dump.get("contacts", []):
        if not isinstance(contact, dict):
            continue
        if contact.get("name") and contact.get("email") and any(
            is_low_trust_contact_source_url(url)
            for url in contact.get("source_urls", [])
        ):
            contact["email"] = None
            warnings.append(
                "Removed named-person email sourced only from a low-trust contact aggregator."
            )
        if _is_named_contact_supported_only_by_low_trust_sources(contact):
            warnings.append(
                "Kept named contact supported only by low-trust directory sources."
            )
        if _has_contact_value(contact):
            contacts.append(contact)
        else:
            if _is_generic_email_contact(contact):
                warnings.append("Removed generic company email contact without a valid email.")
            else:
                warnings.append("Removed empty contact with no usable public contact data.")
    enrichment_dump["contacts"] = contacts


def _has_contact_value(contact: dict[str, Any]) -> bool:
    if _is_generic_email_contact(contact):
        return clean_scalar(contact.get("email")) is not None
    return any(
        clean_scalar(contact.get(field)) is not None
        for field in ("name", "title", "email", "linkedin_url")
    )


def _is_generic_email_contact(contact: dict[str, Any]) -> bool:
    return clean_scalar(contact.get("role")) == "generic_company_email"


def _add_low_trust_field_warnings(
    enrichment_dump: dict[str, Any],
    warnings: list[str],
) -> None:
    for field, source_field in CORE_FACT_FIELDS:
        if enrichment_dump.get(field) is None:
            continue
        source_urls = normalize_source_urls(enrichment_dump.get(source_field))
        if not source_urls:
            continue
        if all(is_low_trust_contact_source_url(url) for url in source_urls):
            warnings.append(
                f"Kept {field} although it is supported only by low-trust directory sources."
            )


def _is_named_contact_supported_only_by_low_trust_sources(
    contact: dict[str, Any],
) -> bool:
    if clean_scalar(contact.get("name")) is None:
        return False
    source_urls = normalize_source_urls(contact.get("source_urls"))
    return bool(source_urls) and all(
        is_low_trust_contact_source_url(url) for url in source_urls
    )


def _has_useful_data(enrichment: CompanyEnrichment) -> bool:
    if _has_core_fact(enrichment) or enrichment.contacts:
        return True
    if enrichment.ai_tech_forward_signal is not None:
        return True
    if clean_scalar(enrichment.ai_tech_forward_reason) is not None:
        return True
    return False
