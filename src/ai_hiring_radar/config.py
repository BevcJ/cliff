from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ai_hiring_radar.company_enrichment.constants import DEFAULT_COMPANY_ENRICHMENT_MODEL
from ai_hiring_radar.job_description_extraction.constants import (
    DEFAULT_JOB_DESCRIPTION_EXTRACTION_MODEL,
    DEFAULT_JOB_DESCRIPTION_EXTRACTION_PROVIDER,
)


PACKAGE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = PACKAGE_DIR / "configs"


class Settings(BaseSettings):
    serper_api_key: str | None = Field(default=None, validation_alias="SERPER_API_KEY")
    fullenrich_api_key: str | None = Field(
        default=None,
        validation_alias="FULLENRICH_API_KEY",
    )
    prospeo_api_key: str | None = Field(
        default=None,
        validation_alias="PROSPEO_API_KEY",
    )
    job_description_extraction_model: str = Field(
        default=DEFAULT_JOB_DESCRIPTION_EXTRACTION_MODEL,
        validation_alias="JOB_DESCRIPTION_EXTRACTION_MODEL",
    )
    job_description_extraction_provider: str = Field(
        default=DEFAULT_JOB_DESCRIPTION_EXTRACTION_PROVIDER,
        validation_alias="JOB_DESCRIPTION_EXTRACTION_PROVIDER",
    )
    company_enrichment_model: str = Field(
        default=DEFAULT_COMPANY_ENRICHMENT_MODEL,
        validation_alias="COMPANY_ENRICHMENT_MODEL",
    )
    inspection_database_url: str | None = Field(
        default=None,
        validation_alias="AI_HIRING_RADAR_DATABASE_URL",
    )
    azure_openai_endpoint: str | None = Field(
        default=None,
        validation_alias="AZURE_OPENAI_ENDPOINT",
    )
    azure_openai_api_key: str | None = Field(
        default=None,
        validation_alias="AZURE_OPENAI_API_KEY",
    )
    azure_openai_deployment_name: str | None = Field(
        default=None,
        validation_alias="AZURE_OPENAI_DEPLOYMENT_NAME",
    )
    azure_openai_api_version: str | None = Field(
        default=None,
        validation_alias="AZURE_OPENAI_API_VERSION",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


class SearchLocationConfig(BaseModel):
    label: str
    query_location: str
    serper_location: str


class CountryConfig(BaseModel):
    name: str
    search_location: str
    gl: str
    hl: str
    search_locations: list[SearchLocationConfig] = Field(default_factory=list)


class CountriesConfig(BaseModel):
    countries: dict[str, CountryConfig]


class TaxonomyConfig(BaseModel):
    execution_roles: list[str]
    product_roles: list[str]
    data_science_roles: list[str] = Field(default_factory=list)
    machine_learning_roles: list[str] = Field(default_factory=list)
    role_aliases: dict[str, list[str]] = Field(default_factory=dict)
    discovery_role_aliases: list[str] = Field(default_factory=list)

    @property
    def all_roles(self) -> list[str]:
        return [
            *self.execution_roles,
            *self.product_roles,
            *self.data_science_roles,
            *self.machine_learning_roles,
        ]

    @property
    def discovery_roles(self) -> list[str]:
        return list(dict.fromkeys([*self.all_roles, *self.discovery_role_aliases]))

    @model_validator(mode="after")
    def validate_aliases(self) -> TaxonomyConfig:
        unknown_targets = set(self.role_aliases).difference(self.all_roles)
        if unknown_targets:
            targets = ", ".join(sorted(unknown_targets))
            raise ValueError(f"Role aliases reference unknown canonical roles: {targets}")

        matching_terms = {
            *self.all_roles,
            *(alias for aliases in self.role_aliases.values() for alias in aliases),
        }
        unknown_discovery_aliases = set(self.discovery_role_aliases).difference(
            matching_terms
        )
        if unknown_discovery_aliases:
            aliases = ", ".join(sorted(unknown_discovery_aliases))
            raise ValueError(f"Unknown discovery role aliases: {aliases}")

        return self


def load_yaml_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    if not isinstance(data, dict):
        raise ValueError(f"Expected a YAML mapping in {path}")

    return data


def load_settings() -> Settings:
    return Settings()


def require_serper_api_key(settings: Settings | None = None) -> str:
    loaded_settings = settings or load_settings()
    api_key = loaded_settings.serper_api_key

    if not api_key:
        raise RuntimeError(
            "SERPER_API_KEY is required for collection commands. "
            "Set it in the environment or in a local .env file."
        )

    return api_key


def require_inspection_database_url(settings: Settings | None = None) -> str:
    loaded_settings = settings or load_settings()
    database_url = (loaded_settings.inspection_database_url or "").strip()

    if not database_url:
        raise RuntimeError(
            "AI_HIRING_RADAR_DATABASE_URL is required for inspection database commands. "
            "Set it in the environment or in a local .env file."
        )

    return database_url


def load_countries_config(path: Path | None = None) -> CountriesConfig:
    config_path = path or CONFIG_DIR / "countries.yaml"
    return CountriesConfig.model_validate(load_yaml_file(config_path))


def load_taxonomy_config(path: Path | None = None) -> TaxonomyConfig:
    config_path = path or CONFIG_DIR / "taxonomy.yaml"
    return TaxonomyConfig.model_validate(load_yaml_file(config_path))
