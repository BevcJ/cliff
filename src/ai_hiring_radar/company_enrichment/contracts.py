from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator

from ai_hiring_radar.llm_usage import LLMCallResult, LLMUsage

from ai_hiring_radar.company_enrichment.text import normalize_source_urls


EMAIL_PATTERN = re.compile(r"^[^@\s:/]+@[^@\s:/]+\.[^@\s:/]+$")
SIZE_NUMBER_PATTERN = re.compile(r"\d+")
SOURCE_FIELD_ALIASES = {
    "company_description_sources": "company_description_source_urls",
    "company_description_sourceurls": "company_description_source_urls",
    "company_description_urls": "company_description_source_urls",
    "industry_sourceurls": "industry_source_urls",
    "industry_sources": "industry_source_urls",
    "industry_urls": "industry_source_urls",
    "company_size_sourceurls": "company_size_source_urls",
    "company_size_sources": "company_size_source_urls",
    "company_size_urls": "company_size_source_urls",
    "founded_year_sourceurls": "founded_year_source_urls",
    "founded_year_sources": "founded_year_source_urls",
    "founded_year_urls": "founded_year_source_urls",
    "company_type_sourceurls": "company_type_source_urls",
    "company_type_sources": "company_type_source_urls",
    "company_type_urls": "company_type_source_urls",
    "funding_source_urls": "funding_summary_source_urls",
    "funding_sourceurls": "funding_summary_source_urls",
    "funding_sources": "funding_summary_source_urls",
    "funding_urls": "funding_summary_source_urls",
    "funding_summary_sourceurls": "funding_summary_source_urls",
    "ai_tech_forward_sourceurls": "ai_tech_forward_source_urls",
    "ai_tech_forward_sources": "ai_tech_forward_source_urls",
    "ai_tech_forward_urls": "ai_tech_forward_source_urls",
}


class CompanyType(StrEnum):
    PRODUCT_COMPANY = "product_company"
    AGENCY_CONSULTING = "agency_consulting"
    TRADITIONAL_COMPANY = "traditional_company"
    AI_NATIVE = "ai_native"
    OTHER = "other"


class AiTechForwardSignal(StrEnum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    NONE = "none"


class CompanySizeRange(StrEnum):
    UP_TO_50 = "0-50"
    FROM_51_TO_100 = "51-100"
    FROM_101_TO_500 = "101-500"
    FROM_501_UP = "501+"


def normalize_company_size_range(value: object | None) -> CompanySizeRange | None:
    if value is None:
        return None
    if isinstance(value, CompanySizeRange):
        return value

    cleaned = " ".join(str(value).split()).strip()
    if not cleaned:
        return None

    lowered = (
        cleaned.casefold()
        .replace(",", "")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
    )
    for size_range in CompanySizeRange:
        if lowered == size_range.value:
            return size_range

    numbers = [int(match.group()) for match in SIZE_NUMBER_PATTERN.finditer(lowered)]
    if not numbers:
        return None

    if "+" in lowered or "more than" in lowered or "over" in lowered:
        return _company_size_bucket_for_count(numbers[0] + 1)
    if len(numbers) >= 2:
        return _company_size_bucket_for_count(numbers[1])
    return _company_size_bucket_for_count(numbers[0])


def _company_size_bucket_for_count(count: int) -> CompanySizeRange:
    if count <= 50:
        return CompanySizeRange.UP_TO_50
    if count <= 100:
        return CompanySizeRange.FROM_51_TO_100
    if count <= 500:
        return CompanySizeRange.FROM_101_TO_500
    return CompanySizeRange.FROM_501_UP


class CompanyContactRole(StrEnum):
    HIRING_MANAGER = "hiring_manager"
    CTO = "cto"
    CEO_FOUNDER = "ceo_founder"
    HEAD_OF_AI_DATA_ENGINEERING = "head_of_ai_data_engineering"
    RECRUITER = "recruiter"
    GENERIC_COMPANY_EMAIL = "generic_company_email"
    OTHER = "other"


class CompanyContact(BaseModel):
    name: str | None = Field(
        default=None,
        description=(
            "Full name for a public named company contact. Prefer multiple relevant "
            "technology, AI, data, ML, engineering, or technical hiring contacts. "
            "Leave null for generic company inboxes and do not infer names from emails."
        ),
    )
    role: CompanyContactRole | None = Field(
        default=None,
        description=(
            "Best matching public contact role. Generic public inboxes must use "
            "generic_company_email. Use other for named contacts with no match."
        ),
    )
    title: str | None = Field(
        default=None,
        description="Explicit public title for the contact, if available.",
    )
    email: str | None = Field(
        default=None,
        description=(
            "Public email address only. Named non-generic public work emails are "
            "first-class contacts when explicitly found. Do not infer emails from "
            "names or domain patterns. Generic public inboxes are allowed as fallback."
        ),
    )
    linkedin_url: str | None = Field(
        default=None,
        description=(
            "Public LinkedIn person profile URL when surfaced by search or a public "
            "page. LinkedIn-only named contacts are first-class contact results."
        ),
    )
    source_urls: list[str] = Field(
        default_factory=list,
        description="Public source URL(s) supporting this contact.",
    )

    @field_validator("name", "title", mode="before")
    @classmethod
    def _blank_to_none(cls, value: object | None) -> object | None:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, value: object | None) -> str | None:
        if not isinstance(value, str):
            return None
        cleaned = " ".join(value.split()).strip()
        if not cleaned or not EMAIL_PATTERN.match(cleaned):
            return None
        return cleaned

    @field_validator("linkedin_url", mode="before")
    @classmethod
    def _normalize_linkedin_url(cls, value: object | None) -> str | None:
        if not isinstance(value, str):
            return None
        cleaned = " ".join(value.split()).strip()
        if not cleaned:
            return None
        parsed = urlparse(cleaned)
        host = parsed.netloc.casefold()
        if parsed.scheme not in {"http", "https"}:
            return None
        if host != "linkedin.com" and not host.endswith(".linkedin.com"):
            return None
        path = parsed.path.strip("/").casefold()
        if not path.startswith("in/") or path == "in":
            return None
        return cleaned

    @field_validator("role", mode="before")
    @classmethod
    def _blank_role_to_none(cls, value: object | None) -> object | None:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("source_urls", mode="before")
    @classmethod
    def _normalize_source_urls(cls, value: object | None) -> list[str]:
        return normalize_source_urls(value)

    @model_validator(mode="after")
    def _normalize_contact_after_validation(self) -> CompanyContact:
        title = (self.title or "").casefold()
        if self.role is CompanyContactRole.CTO and any(
            term in title
            for term in (
                "chief financial officer",
                "cfo",
                "finance",
                "financial officer",
            )
        ):
            self.role = CompanyContactRole.OTHER
        if self.linkedin_url and not self.source_urls:
            self.source_urls = [self.linkedin_url]
        return self


class CompanyEnrichment(BaseModel):
    company_description: str | None = Field(
        default=None,
        description="Short sourced factual company description, not generated marketing copy.",
    )
    company_description_source_urls: list[str] = Field(default_factory=list)
    industry: str | None = Field(
        default=None,
        description="Sourced industry or category only when a public source supports it.",
    )
    industry_source_urls: list[str] = Field(default_factory=list)
    company_size: CompanySizeRange | None = Field(
        default=None,
        description=(
            "Sourced company employee-size bucket. Use only one of 0-50, 51-100, "
            "101-500, or 501+. Leave null when size cannot be confidently mapped."
        ),
    )
    company_size_source_urls: list[str] = Field(default_factory=list)
    founded_year: int | None = Field(
        default=None,
        description="Explicit sourced founding year only. Do not estimate.",
    )
    founded_year_source_urls: list[str] = Field(default_factory=list)
    company_type: CompanyType | None = Field(
        default=None,
        description="Classification based on sourced company facts, not a recommendation.",
    )
    company_type_source_urls: list[str] = Field(default_factory=list)
    funding_summary: str | None = Field(
        default=None,
        description="Compact sourced funding or investment summary when available.",
    )
    funding_summary_source_urls: list[str] = Field(default_factory=list)
    ai_tech_forward_signal: AiTechForwardSignal | None = Field(
        default=None,
        description="Public-evidence signal for whether the company is AI/tech-forward.",
    )
    ai_tech_forward_reason: str | None = Field(
        default=None,
        description="Brief sourced reason for the AI/tech-forward signal.",
    )
    ai_tech_forward_source_urls: list[str] = Field(default_factory=list)
    contacts: list[CompanyContact] = Field(
        default_factory=list,
        description=(
            "Public contacts. Prefer multiple relevant named LinkedIn person profiles "
            "and named non-generic public work emails; keep generic public company "
            "inboxes only as fallback contacts."
        ),
    )
    source_urls: list[str] = Field(
        default_factory=list,
        description="Deduplicated public source URL union used for the enrichment.",
    )

    @model_validator(mode="before")
    @classmethod
    def _repair_source_field_aliases(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data

        repaired = dict(data)
        for alias, target in SOURCE_FIELD_ALIASES.items():
            if alias not in repaired:
                continue
            if repaired.get(target):
                continue
            repaired[target] = repaired[alias]
        return repaired

    @field_validator(
        "company_description",
        "industry",
        "funding_summary",
        "ai_tech_forward_reason",
        mode="before",
    )
    @classmethod
    def _blank_text_to_none(cls, value: object | None) -> object | None:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("company_size", mode="before")
    @classmethod
    def _normalize_company_size(cls, value: object | None) -> CompanySizeRange | None:
        return normalize_company_size_range(value)

    @field_validator("founded_year", mode="before")
    @classmethod
    def _blank_year_to_none(cls, value: object | None) -> object | None:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("company_type", "ai_tech_forward_signal", mode="before")
    @classmethod
    def _blank_enum_to_none(cls, value: object | None) -> object | None:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator(
        "company_description_source_urls",
        "industry_source_urls",
        "company_size_source_urls",
        "founded_year_source_urls",
        "company_type_source_urls",
        "funding_summary_source_urls",
        "ai_tech_forward_source_urls",
        "source_urls",
        mode="before",
    )
    @classmethod
    def _normalize_source_url_list(cls, value: object | None) -> list[str]:
        return normalize_source_urls(value)


class CompanyEnrichmentExtractor(Protocol):
    def __call__(
        self,
        enrichment_input: dict[str, Any],
    ) -> CompanyEnrichment | dict[str, Any] | LLMCallResult[Any]: ...


@dataclass(frozen=True)
class PreparedCompanyEnrichment:
    enrichment: CompanyEnrichment | None
    quality_warnings: tuple[str, ...] = ()
    failed: bool = False


@dataclass(frozen=True)
class CompanyEnrichmentRunIssue:
    company: str | None
    error_type: str
    message: str


@dataclass(frozen=True)
class CompanyEnrichmentRunResult:
    collection_date: str
    model: str
    company_input_path: Path
    candidate_input_path: Path
    output_path: Path
    companies_read: int
    processable_count: int
    enriched_count: int
    skipped_count: int
    validation_error_count: int
    llm_error_count: int
    already_processed_count: int = 0
    llm_usage: LLMUsage = field(default_factory=LLMUsage)
    llm_estimated_cost_usd: float | None = 0.0
    llm_pricing_missing_models: tuple[str, ...] = ()
    quality_error_count: int = 0
    dry_run: bool = False
    validation_error_samples: tuple[CompanyEnrichmentRunIssue, ...] = ()
    llm_error_samples: tuple[CompanyEnrichmentRunIssue, ...] = ()
    quality_error_samples: tuple[CompanyEnrichmentRunIssue, ...] = ()
