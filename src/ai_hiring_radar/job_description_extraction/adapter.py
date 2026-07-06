from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse, urlunparse

from pydantic_ai import Agent

from ai_hiring_radar.job_description_extraction.constants import (
    DEFAULT_JOB_DESCRIPTION_EXTRACTION_PROVIDER,
    JOB_DESCRIPTION_EXTRACTION_PROMPT,
)
from ai_hiring_radar.job_description_extraction.contracts import JobDescriptionExtraction
from ai_hiring_radar.llm_usage import LLMCallResult, usage_from_run_usage


@dataclass(frozen=True)
class NormalizedAzureEndpoint:
    azure_endpoint: str
    api_version: str | None
    use_responses_model: bool


class PydanticAIJobDescriptionExtractor:
    def __init__(
        self,
        *,
        model: str,
        provider: str = DEFAULT_JOB_DESCRIPTION_EXTRACTION_PROVIDER,
        azure_endpoint: str | None = None,
        azure_api_key: str | None = None,
        azure_api_version: str | None = None,
        agent_factory: Callable[..., Any] = Agent,
        azure_provider_factory: Callable[..., Any] | None = None,
        openai_chat_model_factory: Callable[..., Any] | None = None,
        openai_responses_model_factory: Callable[..., Any] | None = None,
    ) -> None:
        model_or_name = _build_model_or_name(
            model=model,
            provider=provider,
            azure_endpoint=azure_endpoint,
            azure_api_key=azure_api_key,
            azure_api_version=azure_api_version,
            azure_provider_factory=azure_provider_factory,
            openai_chat_model_factory=openai_chat_model_factory,
            openai_responses_model_factory=openai_responses_model_factory,
        )
        self.agent = agent_factory(
            model_or_name,
            output_type=JobDescriptionExtraction,
            instructions=JOB_DESCRIPTION_EXTRACTION_PROMPT,
        )

    def __call__(
        self,
        extraction_input: dict[str, Any],
    ) -> LLMCallResult[JobDescriptionExtraction]:
        result = self.agent.run_sync(_build_prompt(extraction_input))
        print("input:")
        print(extraction_input)
        print("output:")
        print(result.output)
        print("--------------------------------")
        return LLMCallResult(
            output=JobDescriptionExtraction.model_validate(result.output),
            usage=usage_from_run_usage(getattr(result, "usage", None)),
        )


def _build_prompt(extraction_input: dict[str, Any]) -> str:
    return "Job data:\n" + json.dumps(
        extraction_input,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def _build_model_or_name(
    *,
    model: str,
    provider: str,
    azure_endpoint: str | None,
    azure_api_key: str | None,
    azure_api_version: str | None,
    azure_provider_factory: Callable[..., Any] | None,
    openai_chat_model_factory: Callable[..., Any] | None,
    openai_responses_model_factory: Callable[..., Any] | None,
) -> Any:
    if provider.strip().lower() != "azure":
        return model

    return _build_azure_model(
        model=model,
        azure_endpoint=azure_endpoint,
        azure_api_key=azure_api_key,
        azure_api_version=azure_api_version,
        azure_provider_factory=azure_provider_factory,
        openai_chat_model_factory=openai_chat_model_factory,
        openai_responses_model_factory=openai_responses_model_factory,
    )


def _build_azure_model(
    *,
    model: str,
    azure_endpoint: str | None,
    azure_api_key: str | None,
    azure_api_version: str | None,
    azure_provider_factory: Callable[..., Any] | None,
    openai_chat_model_factory: Callable[..., Any] | None,
    openai_responses_model_factory: Callable[..., Any] | None,
) -> Any:
    if not azure_endpoint:
        raise ValueError("AZURE_OPENAI_ENDPOINT is required when using Azure extraction.")

    normalized_endpoint = normalize_azure_openai_endpoint(azure_endpoint)
    effective_api_version = azure_api_version or normalized_endpoint.api_version

    if azure_provider_factory is None:
        from pydantic_ai.providers.azure import AzureProvider

        azure_provider_factory = AzureProvider
    if openai_chat_model_factory is None or openai_responses_model_factory is None:
        from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel

        openai_chat_model_factory = openai_chat_model_factory or OpenAIChatModel
        openai_responses_model_factory = (
            openai_responses_model_factory or OpenAIResponsesModel
        )

    provider_kwargs = {"azure_endpoint": normalized_endpoint.azure_endpoint}
    if azure_api_key:
        provider_kwargs["api_key"] = azure_api_key
    if effective_api_version:
        provider_kwargs["api_version"] = effective_api_version

    assert azure_provider_factory is not None
    azure_provider = azure_provider_factory(**provider_kwargs)
    selected_model_factory = (
        openai_responses_model_factory
        if normalized_endpoint.use_responses_model
        else openai_chat_model_factory
    )
    assert selected_model_factory is not None
    return selected_model_factory(model, provider=azure_provider)


def normalize_azure_openai_endpoint(endpoint: str) -> NormalizedAzureEndpoint:
    raw_endpoint = endpoint.strip()
    parsed = urlparse(raw_endpoint)
    if not parsed.scheme or not parsed.netloc:
        return NormalizedAzureEndpoint(
            azure_endpoint=raw_endpoint,
            api_version=None,
            use_responses_model=False,
        )

    api_version = _first_query_value(parsed.query, "api-version")
    path = parsed.path.rstrip("/")
    use_responses_model = path.endswith("/openai/responses") or path.endswith(
        "/responses"
    )

    if path.endswith("/openai/v1"):
        normalized_path = f"{path}/"
    elif "/openai/" in path or path.endswith("/openai"):
        normalized_path = _path_before_openai(path)
    else:
        normalized_path = path or "/"
        if not normalized_path.endswith("/"):
            normalized_path = f"{normalized_path}/"

    return NormalizedAzureEndpoint(
        azure_endpoint=urlunparse(
            (parsed.scheme, parsed.netloc, normalized_path, "", "", "")
        ),
        api_version=api_version,
        use_responses_model=use_responses_model,
    )


def _first_query_value(query: str, key: str) -> str | None:
    values = parse_qs(query).get(key)
    if not values:
        return None
    return values[0]


def _path_before_openai(path: str) -> str:
    prefix = path.split("/openai", 1)[0]
    if not prefix:
        return "/"
    return f"{prefix.rstrip('/')}/"
