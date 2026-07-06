from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field, field_validator

from ai_hiring_radar.llm_usage import LLMCallResult, LLMUsage


class WorkplaceMode(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"


class AiTeamContext(StrEnum):
    FIRST_AI_PERSON = "first_ai_person"
    EXISTING_AI_TEAM = "existing_ai_team"


class DeliveryContext(StrEnum):
    INTERNAL = "internal"
    EXTERNAL_CLIENTS = "external_clients"
    MIXED = "mixed"


class JDContactRole(StrEnum):
    HIRING_MANAGER = "hiring_manager"
    CTO = "cto"
    CEO_FOUNDER = "ceo_founder"
    HEAD_OF_AI_DATA_ENGINEERING = "head_of_ai_data_engineering"
    RECRUITER = "recruiter"
    OTHER = "other"


class JDContact(BaseModel):
    name: str | None = Field(
        default=None,
        description=(
            "Full name of an explicitly listed job contact. Do not infer a name "
            "from an email address or company name."
        ),
    )
    role: JDContactRole | None = Field(
        default=None,
        description=(
            "Best matching contact role, only when the contact block or title makes "
            "it explicit. Use other for named contacts with no matching role."
        ),
    )
    title: str | None = Field(
        default=None,
        description=(
            "Explicit professional title for the contact, such as Talent Partner or "
            "VP Engineering. Leave null when not present."
        ),
    )
    email: str | None = Field(
        default=None,
        description=(
            "Explicit contact email address from the job data. Generic recruiting "
            "emails are allowed only when they are shown in the provided data."
        ),
    )
    linkedin_url: str | None = Field(
        default=None,
        description="Explicit LinkedIn URL for the contact, if present.",
    )

    @field_validator("name", "title", "email", "linkedin_url", mode="before")
    @classmethod
    def _blank_to_none(cls, value: object | None) -> object | None:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class JobDescriptionExtraction(BaseModel):
    workplace_mode: WorkplaceMode | None = Field(
        default=None,
        description=(
            "Work arrangement explicitly stated in the job data. remote requires "
            "explicit remote/work from anywhere/remote-first language. hybrid "
            "requires explicit hybrid or office-frequency language. onsite requires "
            "explicit onsite/in-office language. City, country, or office location "
            "alone is not enough; return null when ambiguous."
        ),
    )
    ai_team_context: AiTeamContext | None = Field(
        default=None,
        description=(
            "Whether the role joins an existing AI/data/ML/product platform context "
            "or appears to be the first dedicated AI person. existing_ai_team "
            "requires explicit evidence of an existing AI team, platform, product, "
            "AI operations, or collaboration with AI specialists. first_ai_person "
            "requires explicit first-hire or first-dedicated-AI-person language. "
            "Return null when only the title, department, or company context hints "
            "at AI."
        ),
    )
    delivery_context: DeliveryContext | None = Field(
        default=None,
        description=(
            "Who the AI work is delivered for. internal means the role builds, "
            "operates, or enables AI for the employer's own teams, product, or "
            "business operations. external_clients means implementation, advisory, "
            "support, or solution delivery for external customers/client accounts. "
            "mixed requires clear evidence of both. Return null if unclear."
        ),
    )
    contacts: list[JDContact] = Field(
        default_factory=list,
        description=(
            "People or contact details explicitly present in the job data. Do not "
            "invent contacts. Prefer one contact object per contact block."
        ),
    )
    posted_at: str | None = Field(
        default=None,
        description=(
            "Explicit posting date/time. Use normalized_source_dates.posted_at or "
            "source_created_at when provided, or an explicit posted date in the job "
            "description. Never use collected_at and never estimate job age."
        ),
    )
    updated_at: str | None = Field(
        default=None,
        description=(
            "Explicit update date/time. Use normalized_source_dates.updated_at or "
            "source_updated_at when provided, or an explicit updated date in the job "
            "description. Never use collected_at and never estimate job age."
        ),
    )

    @field_validator("posted_at", "updated_at", mode="before")
    @classmethod
    def _blank_date_to_none(cls, value: object | None) -> object | None:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class JobDescriptionExtractor(Protocol):
    def __call__(
        self,
        extraction_input: dict[str, Any],
    ) -> JobDescriptionExtraction | dict[str, Any] | LLMCallResult[Any]: ...


@dataclass(frozen=True)
class JobDescriptionExtractionRunResult:
    collection_date: str
    model: str
    input_path: Path
    output_path: Path
    candidates_read: int
    processable_count: int
    extracted_count: int
    skipped_count: int
    validation_error_count: int
    llm_error_count: int
    already_processed_count: int = 0
    llm_usage: LLMUsage = field(default_factory=LLMUsage)
    llm_estimated_cost_usd: float | None = 0.0
    llm_pricing_missing_models: tuple[str, ...] = ()
    dry_run: bool = False
