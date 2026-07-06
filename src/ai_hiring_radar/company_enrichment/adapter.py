from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from pydantic_ai import Agent

from ai_hiring_radar.company_enrichment.constants import COMPANY_ENRICHMENT_PROMPT
from ai_hiring_radar.company_enrichment.contracts import CompanyEnrichment
from ai_hiring_radar.job_description_extraction.adapter import (
    normalize_azure_openai_endpoint,
)
from ai_hiring_radar.llm_usage import LLMCallResult, usage_from_run_usage


class PydanticAICompanyEnrichmentExtractor:
    def __init__(
        self,
        *,
        model: str,
        azure_endpoint: str | None = None,
        azure_api_key: str | None = None,
        azure_api_version: str | None = None,
        agent_factory: Callable[..., Any] = Agent,
        azure_provider_factory: Callable[..., Any] | None = None,
        openai_responses_model_factory: Callable[..., Any] | None = None,
        native_tool_factory: Callable[..., Any] | None = None,
        web_search_tool_factory: Callable[..., Any] | None = None,
    ) -> None:
        model_or_name = _build_model_or_name(
            model=model,
            azure_endpoint=azure_endpoint,
            azure_api_key=azure_api_key,
            azure_api_version=azure_api_version,
            azure_provider_factory=azure_provider_factory,
            openai_responses_model_factory=openai_responses_model_factory,
        )
        self.agent = agent_factory(
            model_or_name,
            output_type=CompanyEnrichment,
            instructions=COMPANY_ENRICHMENT_PROMPT,
            capabilities=[
                _build_web_search_capability(
                    native_tool_factory=native_tool_factory,
                    web_search_tool_factory=web_search_tool_factory,
                )
            ],
        )

    def __call__(
        self,
        enrichment_input: dict[str, Any],
    ) -> LLMCallResult[CompanyEnrichment]:
        result = self.agent.run_sync(_build_prompt(enrichment_input))
        # print(result.output)
        # print("--------------------------------")
        return LLMCallResult(
            output=CompanyEnrichment.model_validate(result.output),
            usage=usage_from_run_usage(getattr(result, "usage", None)),
        )


def _build_prompt(enrichment_input: dict[str, Any]) -> str:
    return "Company data:\n" + json.dumps(
        enrichment_input,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def _build_model_or_name(
    *,
    model: str,
    azure_endpoint: str | None,
    azure_api_key: str | None,
    azure_api_version: str | None,
    azure_provider_factory: Callable[..., Any] | None,
    openai_responses_model_factory: Callable[..., Any] | None,
) -> Any:
    if not azure_endpoint:
        return model

    return _build_azure_responses_model(
        model=model,
        azure_endpoint=azure_endpoint,
        azure_api_key=azure_api_key,
        azure_api_version=azure_api_version,
        azure_provider_factory=azure_provider_factory,
        openai_responses_model_factory=openai_responses_model_factory,
    )


def _build_azure_responses_model(
    *,
    model: str,
    azure_endpoint: str,
    azure_api_key: str | None,
    azure_api_version: str | None,
    azure_provider_factory: Callable[..., Any] | None,
    openai_responses_model_factory: Callable[..., Any] | None,
) -> Any:
    normalized_endpoint = normalize_azure_openai_endpoint(azure_endpoint)
    effective_api_version = azure_api_version or normalized_endpoint.api_version

    if azure_provider_factory is None:
        from pydantic_ai.providers.azure import AzureProvider

        azure_provider_factory = AzureProvider
    if openai_responses_model_factory is None:
        from pydantic_ai.models.openai import OpenAIResponsesModel

        openai_responses_model_factory = OpenAIResponsesModel

    provider_kwargs = {"azure_endpoint": normalized_endpoint.azure_endpoint}
    if azure_api_key:
        provider_kwargs["api_key"] = azure_api_key
    if effective_api_version:
        provider_kwargs["api_version"] = effective_api_version

    assert azure_provider_factory is not None
    assert openai_responses_model_factory is not None
    azure_provider = azure_provider_factory(**provider_kwargs)
    return openai_responses_model_factory(model, provider=azure_provider)


def _build_web_search_capability(
    *,
    native_tool_factory: Callable[..., Any] | None,
    web_search_tool_factory: Callable[..., Any] | None,
) -> Any:
    if native_tool_factory is None:
        from pydantic_ai.capabilities import NativeTool

        native_tool_factory = NativeTool
    if web_search_tool_factory is None:
        from pydantic_ai.native_tools import WebSearchTool

        web_search_tool_factory = WebSearchTool

    assert native_tool_factory is not None
    assert web_search_tool_factory is not None
    return native_tool_factory(web_search_tool_factory())
