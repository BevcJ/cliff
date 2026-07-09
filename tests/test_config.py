from ai_hiring_radar.config import (
    Settings,
    load_countries_config,
    load_taxonomy_config,
    require_inspection_database_url,
)


def test_country_config_loads_initial_countries() -> None:
    config = load_countries_config()

    assert set(config.countries) == {"nl", "uk", "dk"}
    assert config.countries["nl"].name == "Netherlands"
    assert len(config.countries["nl"].search_locations) == 11
    assert config.countries["nl"].search_locations[1].label == "Amsterdam"
    assert config.countries["uk"].search_location == "United Kingdom"
    assert config.countries["dk"].gl == "dk"


def test_taxonomy_config_loads_role_groups() -> None:
    config = load_taxonomy_config()

    assert "LLM Engineer" in config.execution_roles
    assert "AI Product Manager" in config.product_roles
    assert len(config.all_roles) == len(config.execution_roles) + len(config.product_roles)


def test_settings_loads_serper_api_key_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("SERPER_API_KEY", "test-key")

    settings = Settings()

    assert settings.serper_api_key == "test-key"


def test_settings_loads_job_description_extraction_model_from_environment(
    monkeypatch,
) -> None:
    monkeypatch.setenv("JOB_DESCRIPTION_EXTRACTION_MODEL", "openai:gpt-5-mini")
    monkeypatch.setenv("JOB_DESCRIPTION_EXTRACTION_PROVIDER", "azure")
    monkeypatch.setenv("COMPANY_ENRICHMENT_MODEL", "gpt-5-mini")
    monkeypatch.setenv(
        "AZURE_OPENAI_ENDPOINT",
        "https://dev-aibooking-openai.openai.azure.com/openai/responses?api-version=2025-04-01-preview",
    )
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "azure-key")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5.4-mini")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
    monkeypatch.setenv("AI_HIRING_RADAR_DATABASE_URL", "postgresql://inspection-db")

    settings = Settings()

    assert settings.job_description_extraction_model == "openai:gpt-5-mini"
    assert settings.job_description_extraction_provider == "azure"
    assert settings.company_enrichment_model == "gpt-5-mini"
    assert settings.azure_openai_endpoint == (
        "https://dev-aibooking-openai.openai.azure.com/openai/responses?api-version=2025-04-01-preview"
    )
    assert settings.azure_openai_api_key == "azure-key"
    assert settings.azure_openai_deployment_name == "gpt-5.4-mini"
    assert settings.azure_openai_api_version == "2025-04-01-preview"
    assert settings.inspection_database_url == "postgresql://inspection-db"


def test_settings_can_be_created_with_field_name() -> None:
    settings = Settings(
        serper_api_key="test-key",
        job_description_extraction_model="test-model",
        job_description_extraction_provider="azure",
        company_enrichment_model="gpt-5-mini",
        inspection_database_url="postgresql://inspection-db",
        azure_openai_endpoint="https://example.openai.azure.com/",
        azure_openai_api_key="azure-key",
        azure_openai_deployment_name="deployment",
        azure_openai_api_version="2025-04-01-preview",
    )

    assert settings.serper_api_key == "test-key"
    assert settings.job_description_extraction_model == "test-model"
    assert settings.job_description_extraction_provider == "azure"
    assert settings.company_enrichment_model == "gpt-5-mini"
    assert settings.inspection_database_url == "postgresql://inspection-db"
    assert settings.azure_openai_endpoint == "https://example.openai.azure.com/"
    assert settings.azure_openai_api_key == "azure-key"
    assert settings.azure_openai_deployment_name == "deployment"
    assert settings.azure_openai_api_version == "2025-04-01-preview"


def test_require_inspection_database_url_returns_configured_url() -> None:
    settings = Settings(inspection_database_url="postgresql://inspection-db")

    assert require_inspection_database_url(settings) == "postgresql://inspection-db"
