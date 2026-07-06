from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
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

    @property
    def all_roles(self) -> list[str]:
        return [*self.execution_roles, *self.product_roles]


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


def load_countries_config(path: Path | None = None) -> CountriesConfig:
    config_path = path or CONFIG_DIR / "countries.yaml"
    return CountriesConfig.model_validate(load_yaml_file(config_path))


def load_taxonomy_config(path: Path | None = None) -> TaxonomyConfig:
    config_path = path or CONFIG_DIR / "taxonomy.yaml"
    return TaxonomyConfig.model_validate(load_yaml_file(config_path))
