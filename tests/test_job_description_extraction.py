from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from ai_hiring_radar.job_description_extraction import (
    DEFAULT_JOB_DESCRIPTION_EXTRACTION_MODEL,
    JOB_DESCRIPTION_EXTRACTION_PROMPT,
    AiTeamContext,
    DeliveryContext,
    JDContact,
    JDContactRole,
    JobDescriptionExtraction,
    PROMPT_VERSION,
    PydanticAIJobDescriptionExtractor,
    WorkplaceMode,
    build_extraction_input,
    build_extraction_record,
    normalize_azure_openai_endpoint,
    normalize_explicit_date,
    run_job_description_extraction,
)
from ai_hiring_radar.llm_usage import LLMCallResult, LLMUsage
from ai_hiring_radar.storage_json import read_jsonl, write_processed_jsonl


def _candidate(**overrides: Any) -> dict[str, Any]:
    candidate = {
        "record_type": "job_candidate",
        "job_id": "job-123",
        "source": "lever",
        "source_mode": "public_job_board_endpoint",
        "platform": "lever",
        "platform_company_slug": "acme-ai",
        "platform_job_id": "job-ai-engineer",
        "company_normalized": "Acme Ai",
        "job_title_raw": "Senior AI Engineer",
        "job_title_normalized": "AI Engineer",
        "role_search_term": "AI Engineer",
        "role_group": "AI Execution Role",
        "source_url": "https://jobs.lever.co/acme-ai/job-ai-engineer",
        "job_url": "https://jobs.lever.co/acme-ai/job-ai-engineer",
        "team": "Engineering",
        "department": "AI",
        "location": "Amsterdam, Netherlands",
        "job_locations_raw": ["Amsterdam, Netherlands"],
        "workplace_type": "Hybrid",
        "employment_type": "Full-time",
        "description": "<p>Build internal AI products.</p>",
        "description_plain": "Build internal AI products.",
        "job_description_sections": [
            {"name": "About", "value": "Build internal AI products."}
        ],
        "lists": [{"text": "Responsibilities", "content": "Build AI systems."}],
        "source_created_at": "1780000000000",
        "source_updated_at": "2026-06-16T00:00:00Z",
    }
    candidate.update(overrides)
    return candidate


def test_job_description_extraction_accepts_enum_values() -> None:
    extraction = JobDescriptionExtraction.model_validate(
        {
            "workplace_mode": "hybrid",
            "ai_team_context": "existing_ai_team",
            "delivery_context": "internal",
            "contacts": [
                {
                    "name": "Ada Lovelace",
                    "role": "hiring_manager",
                    "title": "VP Engineering",
                }
            ],
        }
    )

    assert extraction.workplace_mode is WorkplaceMode.HYBRID
    assert extraction.ai_team_context is AiTeamContext.EXISTING_AI_TEAM
    assert extraction.delivery_context is DeliveryContext.INTERNAL
    assert extraction.contacts == [
        JDContact(
            name="Ada Lovelace",
            role=JDContactRole.HIRING_MANAGER,
            title="VP Engineering",
        )
    ]


def test_job_description_extraction_rejects_invalid_enum_values() -> None:
    try:
        JobDescriptionExtraction.model_validate({"workplace_mode": "spaceship"})
    except ValidationError:
        return

    raise AssertionError("Invalid enum value should fail validation.")


def test_job_description_extraction_defaults_missing_values() -> None:
    extraction = JobDescriptionExtraction.model_validate(
        {"posted_at": "", "updated_at": " "}
    )

    assert extraction.workplace_mode is None
    assert extraction.ai_team_context is None
    assert extraction.delivery_context is None
    assert extraction.contacts == []
    assert extraction.posted_at is None
    assert extraction.updated_at is None


def test_extraction_prompt_contains_conservative_quality_rules() -> None:
    assert PROMPT_VERSION == "v2"
    assert "null is better than a guessed value" in JOB_DESCRIPTION_EXTRACTION_PROMPT
    assert "Do not classify from the job title alone" in JOB_DESCRIPTION_EXTRACTION_PROMPT
    assert "city, country, office name" in JOB_DESCRIPTION_EXTRACTION_PROMPT
    assert "remote-first culture" in JOB_DESCRIPTION_EXTRACTION_PROMPT
    assert "first AI hire" in JOB_DESCRIPTION_EXTRACTION_PROMPT
    assert "external customers, clients, or client accounts" in (
        JOB_DESCRIPTION_EXTRACTION_PROMPT
    )
    assert "Never use collected_at as posted_at or updated_at" in (
        JOB_DESCRIPTION_EXTRACTION_PROMPT
    )


def test_extraction_schema_describes_ambiguous_fields() -> None:
    schema = JobDescriptionExtraction.model_json_schema()
    properties = schema["properties"]

    assert "City, country, or office location alone is not enough" in properties[
        "workplace_mode"
    ]["description"]
    assert "first-hire or first-dedicated-AI-person" in properties[
        "ai_team_context"
    ]["description"]
    assert "external customers/client accounts" in properties["delivery_context"][
        "description"
    ]
    assert "Never use collected_at" in properties["posted_at"]["description"]
    assert "Never use collected_at" in properties["updated_at"]["description"]


def test_build_extraction_input_includes_relevant_candidate_fields() -> None:
    extraction_input = build_extraction_input(_candidate())

    assert extraction_input is not None
    assert extraction_input["job_title_raw"] == "Senior AI Engineer"
    assert extraction_input["location"] == "Amsterdam, Netherlands"
    assert extraction_input["team"] == "Engineering"
    assert extraction_input["department"] == "AI"
    assert extraction_input["source_created_at"] == "1780000000000"
    assert extraction_input["normalized_source_dates"]["posted_at"].endswith("Z")
    assert extraction_input["job_url"] == "https://jobs.lever.co/acme-ai/job-ai-engineer"
    assert extraction_input["platform_company_slug"] == "acme-ai"
    assert extraction_input["description"] == "<p>Build internal AI products.</p>"
    assert extraction_input["job_description_sections"] == [
        {"name": "About", "value": "Build internal AI products."}
    ]


def test_build_extraction_input_skips_title_only_records() -> None:
    assert (
        build_extraction_input(
            {
                "record_type": "job_candidate",
                "job_id": "title-only",
                "source": "serper_google",
                "source_url": "https://www.linkedin.com/jobs/view/123",
                "company_normalized": "Acme",
                "job_title_raw": "AI Product Manager",
            }
        )
        is None
    )


def test_build_extraction_record_excludes_full_description_fields() -> None:
    record = build_extraction_record(
        candidate=_candidate(),
        extraction=JobDescriptionExtraction(
            workplace_mode=WorkplaceMode.HYBRID,
            delivery_context=DeliveryContext.INTERNAL,
        ),
        model="test-model",
        extracted_at="2026-07-02T10:00:00Z",
    )

    assert record["record_type"] == "job_description_extract"
    assert record["model"] == "test-model"
    assert record["job_id"] == "job-123"
    assert record["workplace_mode"] == "hybrid"
    assert record["delivery_context"] == "internal"
    assert record["posted_at"].endswith("Z")
    assert record["updated_at"] == "2026-06-16T00:00:00Z"
    assert "description" not in record
    assert "description_plain" not in record
    assert "job_description_sections" not in record
    assert "lists" not in record


def test_normalize_explicit_date_handles_lever_millisecond_timestamp() -> None:
    assert normalize_explicit_date("1780000000000") == "2026-05-28T20:26:40Z"


def test_run_job_description_extraction_writes_jsonl_with_fake_extractor(tmp_path) -> None:
    write_processed_jsonl(
        "job_candidates_2026-07-02.jsonl",
        [_candidate()],
        data_dir=tmp_path,
    )

    def fake_extractor(
        extraction_input: dict[str, Any],
    ) -> LLMCallResult[JobDescriptionExtraction]:
        assert extraction_input["job_id"] == "job-123"
        return LLMCallResult(
            output=JobDescriptionExtraction(
                workplace_mode=WorkplaceMode.HYBRID,
                delivery_context=DeliveryContext.INTERNAL,
            ),
            usage=LLMUsage(input_tokens=1_000, output_tokens=500, requests=1),
        )

    result = run_job_description_extraction(
        "2026-07-02",
        extractor=fake_extractor,
        model="gpt-5-mini",
        data_dir=tmp_path,
        clock=lambda: "2026-07-02T10:00:00Z",
        show_progress=False,
    )

    assert result.candidates_read == 1
    assert result.processable_count == 1
    assert result.extracted_count == 1
    assert result.skipped_count == 0
    assert result.validation_error_count == 0
    assert result.llm_error_count == 0
    assert result.llm_usage.input_tokens == 1_000
    assert result.llm_usage.output_tokens == 500
    assert result.llm_estimated_cost_usd == 0.00125
    records = read_jsonl(result.output_path)
    assert records[0]["workplace_mode"] == "hybrid"
    assert records[0]["extracted_at"] == "2026-07-02T10:00:00Z"
    assert records[0]["llm_usage"]["requests"] == 1
    assert records[0]["llm_pricing_model"] == "gpt-5-mini"
    assert records[0]["llm_estimated_cost_usd"] == 0.00125


def test_run_job_description_extraction_counts_skips_and_errors(tmp_path) -> None:
    write_processed_jsonl(
        "job_candidates_2026-07-02.jsonl",
        [
            _candidate(job_id="valid"),
            _candidate(job_id="invalid-output"),
            _candidate(job_id="llm-error"),
            {"record_type": "job_candidate", "source": "lever"},
            "not-a-dict",  # type: ignore[list-item]
        ],
        data_dir=tmp_path,
    )

    def fake_extractor(extraction_input: dict[str, Any]) -> dict[str, Any]:
        if extraction_input["job_id"] == "invalid-output":
            return {"workplace_mode": "spaceship"}
        if extraction_input["job_id"] == "llm-error":
            raise RuntimeError("model unavailable")
        return {"workplace_mode": "remote"}

    result = run_job_description_extraction(
        "2026-07-02",
        extractor=fake_extractor,
        model="test-model",
        data_dir=tmp_path,
        clock=lambda: "2026-07-02T10:00:00Z",
        show_progress=False,
    )

    assert result.candidates_read == 5
    assert result.processable_count == 3
    assert result.extracted_count == 1
    assert result.skipped_count == 2
    assert result.validation_error_count == 1
    assert result.llm_error_count == 1
    assert len(read_jsonl(result.output_path)) == 1


def test_run_job_description_extraction_resumes_existing_output(tmp_path) -> None:
    done_candidate = _candidate(job_id="done")
    new_candidate = _candidate(job_id="new")
    write_processed_jsonl(
        "job_candidates_2026-07-02.jsonl",
        [done_candidate, new_candidate],
        data_dir=tmp_path,
    )
    write_processed_jsonl(
        "job_description_extracts_2026-07-02.jsonl",
        [
            build_extraction_record(
                candidate=done_candidate,
                extraction=JobDescriptionExtraction(workplace_mode=WorkplaceMode.REMOTE),
                model="old-model",
                extracted_at="2026-07-01T10:00:00Z",
            )
        ],
        data_dir=tmp_path,
    )
    calls: list[str] = []

    def fake_extractor(extraction_input: dict[str, Any]) -> dict[str, Any]:
        calls.append(extraction_input["job_id"])
        return {"workplace_mode": "hybrid"}

    result = run_job_description_extraction(
        "2026-07-02",
        extractor=fake_extractor,
        model="test-model",
        data_dir=tmp_path,
        clock=lambda: "2026-07-02T10:00:00Z",
        show_progress=False,
    )

    assert calls == ["new"]
    assert result.candidates_read == 2
    assert result.already_processed_count == 1
    assert result.extracted_count == 1
    records = read_jsonl(result.output_path)
    assert [record["job_id"] for record in records] == ["done", "new"]
    assert records[1]["workplace_mode"] == "hybrid"


def test_run_job_description_extraction_restart_replaces_existing_output(
    tmp_path,
) -> None:
    candidate = _candidate(job_id="done")
    write_processed_jsonl(
        "job_candidates_2026-07-02.jsonl",
        [candidate],
        data_dir=tmp_path,
    )
    write_processed_jsonl(
        "job_description_extracts_2026-07-02.jsonl",
        [
            build_extraction_record(
                candidate=candidate,
                extraction=JobDescriptionExtraction(workplace_mode=WorkplaceMode.REMOTE),
                model="old-model",
                extracted_at="2026-07-01T10:00:00Z",
            )
        ],
        data_dir=tmp_path,
    )

    def fake_extractor(extraction_input: dict[str, Any]) -> dict[str, Any]:
        assert extraction_input["job_id"] == "done"
        return {"workplace_mode": "hybrid"}

    result = run_job_description_extraction(
        "2026-07-02",
        extractor=fake_extractor,
        model="test-model",
        data_dir=tmp_path,
        clock=lambda: "2026-07-02T10:00:00Z",
        show_progress=False,
        restart=True,
    )

    assert result.already_processed_count == 0
    assert result.extracted_count == 1
    records = read_jsonl(result.output_path)
    assert len(records) == 1
    assert records[0]["job_id"] == "done"
    assert records[0]["workplace_mode"] == "hybrid"


def test_run_job_description_extraction_dry_run_does_not_write_or_call_model(
    tmp_path,
) -> None:
    write_processed_jsonl(
        "job_candidates_2026-07-02.jsonl",
        [_candidate()],
        data_dir=tmp_path,
    )

    result = run_job_description_extraction(
        "2026-07-02",
        extractor=None,
        model="test-model",
        data_dir=tmp_path,
        dry_run=True,
        show_progress=False,
    )

    assert result.dry_run is True
    assert result.processable_count == 1
    assert result.extracted_count == 0
    assert not result.output_path.exists()


def test_pydantic_ai_adapter_constructs_agent_with_model_and_output_type() -> None:
    calls: list[dict[str, Any]] = []

    class FakeAgent:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            calls.append({"args": args, "kwargs": kwargs})

        def run_sync(self, prompt: str) -> Any:
            assert "Job data:" in prompt

            class Result:
                output = JobDescriptionExtraction(workplace_mode=WorkplaceMode.REMOTE)

            return Result()

    extractor = PydanticAIJobDescriptionExtractor(
        model="test-model",
        agent_factory=FakeAgent,
    )

    assert calls == [
        {
            "args": ("test-model",),
            "kwargs": {
                "output_type": JobDescriptionExtraction,
                "instructions": JOB_DESCRIPTION_EXTRACTION_PROMPT,
            },
        }
    ]
    call_result = extractor({"job_id": "123"})
    assert call_result.output.workplace_mode is WorkplaceMode.REMOTE
    assert DEFAULT_JOB_DESCRIPTION_EXTRACTION_MODEL == "openai:gpt-5-mini"


def test_normalize_azure_openai_responses_endpoint() -> None:
    endpoint = normalize_azure_openai_endpoint(
        "https://dev-aibooking-openai.openai.azure.com/openai/responses?"
        "api-version=2025-04-01-preview"
    )

    assert endpoint.azure_endpoint == "https://dev-aibooking-openai.openai.azure.com/"
    assert endpoint.api_version == "2025-04-01-preview"
    assert endpoint.use_responses_model is True


def test_pydantic_ai_adapter_builds_azure_responses_model() -> None:
    calls: dict[str, Any] = {}

    class FakeProvider:
        def __init__(self, **kwargs: Any) -> None:
            calls["provider_kwargs"] = kwargs

    class FakeResponsesModel:
        def __init__(self, model: str, **kwargs: Any) -> None:
            calls["responses_model_instance"] = self
            calls["responses_model"] = {"model": model, "kwargs": kwargs}

    class FakeChatModel:
        def __init__(self, model: str, **kwargs: Any) -> None:
            calls["chat_model"] = {"model": model, "kwargs": kwargs}

    class FakeAgent:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            calls["agent_args"] = args
            calls["agent_kwargs"] = kwargs

        def run_sync(self, prompt: str) -> Any:
            class Result:
                output = JobDescriptionExtraction(workplace_mode=WorkplaceMode.REMOTE)

            return Result()

    PydanticAIJobDescriptionExtractor(
        model="gpt-5.4-mini",
        provider="azure",
        azure_endpoint=(
            "https://dev-aibooking-openai.openai.azure.com/openai/responses?"
            "api-version=2025-04-01-preview"
        ),
        azure_api_key="test-key",
        agent_factory=FakeAgent,
        azure_provider_factory=FakeProvider,
        openai_chat_model_factory=FakeChatModel,
        openai_responses_model_factory=FakeResponsesModel,
    )

    assert calls["provider_kwargs"] == {
        "azure_endpoint": "https://dev-aibooking-openai.openai.azure.com/",
        "api_key": "test-key",
        "api_version": "2025-04-01-preview",
    }
    assert calls["responses_model"]["model"] == "gpt-5.4-mini"
    assert "chat_model" not in calls
    assert calls["agent_args"] == (calls["responses_model_instance"],)
    assert calls["agent_kwargs"]["output_type"] == JobDescriptionExtraction
