from __future__ import annotations

import pytest

from ai_hiring_radar.llm_usage import (
    LLMUsage,
    estimate_llm_cost,
    normalize_model_name,
    pricing_for_model,
)


def test_normalize_model_name_removes_provider_prefix() -> None:
    assert normalize_model_name("openai:gpt-5-mini") == "gpt-5-mini"


def test_pricing_for_model_handles_snapshots() -> None:
    pricing = pricing_for_model("gpt-5.4-mini-2026-03-17")

    assert pricing is not None
    assert pricing.model == "gpt-5.4-mini"


def test_estimate_llm_cost_uses_openai_pricing_and_web_search_calls() -> None:
    cost = estimate_llm_cost(
        model="openai:gpt-5.4-mini",
        usage=LLMUsage(
            input_tokens=1_000,
            cache_read_tokens=100,
            output_tokens=2_000,
            requests=1,
            tool_calls=2,
        ),
        web_search_tool_calls=2,
    )

    assert cost is not None
    assert cost.pricing_model == "gpt-5.4-mini"
    assert cost.input_cost_usd == pytest.approx(0.000675)
    assert cost.cached_input_cost_usd == pytest.approx(0.0000075)
    assert cost.output_cost_usd == pytest.approx(0.009)
    assert cost.web_search_cost_usd == pytest.approx(0.02)
    assert cost.total_cost_usd == pytest.approx(0.0296825)


def test_estimate_llm_cost_marks_unknown_model_as_unpriced() -> None:
    cost = estimate_llm_cost(
        model="custom-azure-deployment",
        usage=LLMUsage(input_tokens=100, output_tokens=100, requests=1),
    )

    assert cost is not None
    assert cost.pricing_model is None
    assert cost.total_cost_usd is None
