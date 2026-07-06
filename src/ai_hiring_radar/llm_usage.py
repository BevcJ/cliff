from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Generic, TypeVar


OutputT = TypeVar("OutputT")

OPENAI_PRICING_SOURCE = "OpenAI API pricing docs, fetched 2026-07-03"
TOKENS_PER_MILLION = 1_000_000
WEB_SEARCH_CALLS_PER_UNIT = 1_000


@dataclass(frozen=True)
class LLMUsage:
    input_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0
    input_audio_tokens: int = 0
    cache_audio_read_tokens: int = 0
    output_audio_tokens: int = 0
    details: dict[str, int] = field(default_factory=dict)
    requests: int = 0
    tool_calls: int = 0


@dataclass(frozen=True)
class LLMCallResult(Generic[OutputT]):
    output: OutputT
    usage: LLMUsage | None = None


@dataclass(frozen=True)
class ModelTokenPricing:
    model: str
    input_per_million: float
    cached_input_per_million: float | None
    output_per_million: float


@dataclass(frozen=True)
class LLMCostEstimate:
    pricing_model: str | None
    input_cost_usd: float | None
    cached_input_cost_usd: float | None
    output_cost_usd: float | None
    web_search_cost_usd: float
    total_cost_usd: float | None
    pricing_source: str = OPENAI_PRICING_SOURCE

    @property
    def has_complete_pricing(self) -> bool:
        return self.total_cost_usd is not None


OPENAI_TEXT_MODEL_PRICING: dict[str, ModelTokenPricing] = {
    "gpt-5-mini": ModelTokenPricing(
        model="gpt-5-mini",
        input_per_million=0.25,
        cached_input_per_million=0.025,
        output_per_million=2.00,
    ),
    "gpt-5.4-mini": ModelTokenPricing(
        model="gpt-5.4-mini",
        input_per_million=0.75,
        cached_input_per_million=0.075,
        output_per_million=4.50,
    ),
    "gpt-5.4": ModelTokenPricing(
        model="gpt-5.4",
        input_per_million=2.50,
        cached_input_per_million=0.25,
        output_per_million=15.00,
    ),
}

WEB_SEARCH_PRICE_PER_1K_CALLS = 10.00


def usage_from_run_usage(raw_usage: Any) -> LLMUsage | None:
    if raw_usage is None:
        return None
    if isinstance(raw_usage, LLMUsage):
        return raw_usage
    if isinstance(raw_usage, type):
        return None
    if callable(raw_usage):
        try:
            raw_usage = raw_usage()
        except TypeError:
            return None
    raw_usage_data: Any = raw_usage
    if is_dataclass(raw_usage_data) and not isinstance(raw_usage_data, type):
        raw_usage_data = asdict(raw_usage_data)
    else:
        model_dump = getattr(raw_usage_data, "model_dump", None)
        if callable(model_dump):
            raw_usage_data = model_dump(mode="json")

    if not isinstance(raw_usage_data, dict):
        raw_usage_data = {
            field_name: getattr(raw_usage_data, field_name, 0)
            for field_name in _USAGE_NUMERIC_FIELDS
            if hasattr(raw_usage_data, field_name)
        } | {"details": getattr(raw_usage_data, "details", {})}

    return LLMUsage(
        input_tokens=_int_value(raw_usage_data.get("input_tokens")),
        cache_write_tokens=_int_value(raw_usage_data.get("cache_write_tokens")),
        cache_read_tokens=_int_value(raw_usage_data.get("cache_read_tokens")),
        output_tokens=_int_value(raw_usage_data.get("output_tokens")),
        input_audio_tokens=_int_value(raw_usage_data.get("input_audio_tokens")),
        cache_audio_read_tokens=_int_value(raw_usage_data.get("cache_audio_read_tokens")),
        output_audio_tokens=_int_value(raw_usage_data.get("output_audio_tokens")),
        details=_details_value(raw_usage_data.get("details")),
        requests=_int_value(raw_usage_data.get("requests")),
        tool_calls=_int_value(raw_usage_data.get("tool_calls")),
    )


def usage_to_dict(usage: LLMUsage | None) -> dict[str, Any] | None:
    if usage is None:
        return None
    return asdict(usage)


def add_usage(left: LLMUsage | None, right: LLMUsage | None) -> LLMUsage:
    if left is None:
        left = LLMUsage()
    if right is None:
        return left

    details = dict(left.details)
    for key, value in right.details.items():
        details[key] = details.get(key, 0) + value

    return LLMUsage(
        input_tokens=left.input_tokens + right.input_tokens,
        cache_write_tokens=left.cache_write_tokens + right.cache_write_tokens,
        cache_read_tokens=left.cache_read_tokens + right.cache_read_tokens,
        output_tokens=left.output_tokens + right.output_tokens,
        input_audio_tokens=left.input_audio_tokens + right.input_audio_tokens,
        cache_audio_read_tokens=(
            left.cache_audio_read_tokens + right.cache_audio_read_tokens
        ),
        output_audio_tokens=left.output_audio_tokens + right.output_audio_tokens,
        details=details,
        requests=left.requests + right.requests,
        tool_calls=left.tool_calls + right.tool_calls,
    )


def estimate_llm_cost(
    *,
    model: str,
    usage: LLMUsage | None,
    web_search_tool_calls: int = 0,
) -> LLMCostEstimate | None:
    if usage is None:
        return None

    pricing = pricing_for_model(model)
    web_search_cost_usd = _cost_per_unit(
        web_search_tool_calls,
        WEB_SEARCH_PRICE_PER_1K_CALLS,
        WEB_SEARCH_CALLS_PER_UNIT,
    )
    if pricing is None:
        return LLMCostEstimate(
            pricing_model=None,
            input_cost_usd=None,
            cached_input_cost_usd=None,
            output_cost_usd=None,
            web_search_cost_usd=web_search_cost_usd,
            total_cost_usd=None,
        )

    cached_input_tokens = usage.cache_read_tokens
    uncached_input_tokens = max(usage.input_tokens - cached_input_tokens, 0)
    input_cost_usd = _cost_per_unit(
        uncached_input_tokens,
        pricing.input_per_million,
        TOKENS_PER_MILLION,
    )
    cached_input_cost_usd = _cost_per_unit(
        cached_input_tokens,
        pricing.cached_input_per_million or pricing.input_per_million,
        TOKENS_PER_MILLION,
    )
    output_cost_usd = _cost_per_unit(
        usage.output_tokens,
        pricing.output_per_million,
        TOKENS_PER_MILLION,
    )
    total_cost_usd = (
        input_cost_usd
        + cached_input_cost_usd
        + output_cost_usd
        + web_search_cost_usd
    )

    return LLMCostEstimate(
        pricing_model=pricing.model,
        input_cost_usd=input_cost_usd,
        cached_input_cost_usd=cached_input_cost_usd,
        output_cost_usd=output_cost_usd,
        web_search_cost_usd=web_search_cost_usd,
        total_cost_usd=total_cost_usd,
    )


def pricing_for_model(model: str) -> ModelTokenPricing | None:
    normalized = normalize_model_name(model)
    for known_model in sorted(OPENAI_TEXT_MODEL_PRICING, key=len, reverse=True):
        if normalized == known_model or normalized.startswith(f"{known_model}-"):
            return OPENAI_TEXT_MODEL_PRICING[known_model]
    return None


def normalize_model_name(model: str) -> str:
    normalized = model.strip().lower()
    if ":" in normalized:
        normalized = normalized.rsplit(":", 1)[1]
    return normalized


def cost_to_dict(cost: LLMCostEstimate | None) -> dict[str, Any] | None:
    if cost is None:
        return None
    return {
        "pricing_model": cost.pricing_model,
        "input_cost_usd": cost.input_cost_usd,
        "cached_input_cost_usd": cost.cached_input_cost_usd,
        "output_cost_usd": cost.output_cost_usd,
        "web_search_cost_usd": cost.web_search_cost_usd,
        "total_cost_usd": cost.total_cost_usd,
        "pricing_source": cost.pricing_source,
    }


def llm_record_metadata(
    *,
    usage: LLMUsage | None,
    cost: LLMCostEstimate | None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    usage_dump = usage_to_dict(usage)
    cost_dump = cost_to_dict(cost)
    if usage_dump is not None:
        metadata["llm_usage"] = usage_dump
    if cost_dump is not None:
        metadata["llm_estimated_cost_usd"] = cost.total_cost_usd if cost else None
        metadata["llm_pricing_model"] = cost.pricing_model if cost else None
        metadata["llm_cost_breakdown_usd"] = cost_dump
    return metadata


def format_usage_summary(usage: LLMUsage) -> str:
    return (
        f"{usage.requests:,} request(s), {usage.tool_calls:,} tool call(s), "
        f"{usage.input_tokens:,} input token(s), "
        f"{usage.cache_read_tokens:,} cached input token(s), "
        f"{usage.output_tokens:,} output token(s)"
    )


def format_usd(value: float) -> str:
    if value < 0.01:
        return f"${value:.6f}"
    return f"${value:.4f}"


_USAGE_NUMERIC_FIELDS = (
    "input_tokens",
    "cache_write_tokens",
    "cache_read_tokens",
    "output_tokens",
    "input_audio_tokens",
    "cache_audio_read_tokens",
    "output_audio_tokens",
    "requests",
    "tool_calls",
)


def _int_value(value: object | None) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return 0


def _details_value(value: object | None) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): int_value
        for key, item in value.items()
        if (int_value := _int_value(item)) > 0
    }


def _cost_per_unit(count: int, price: float, unit_size: int) -> float:
    if count <= 0 or price <= 0:
        return 0.0
    return (count / unit_size) * price
