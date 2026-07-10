from __future__ import annotations

import json
from datetime import date, datetime, timezone
from email.utils import format_datetime

import httpx
import pytest

from ai_hiring_radar.sources import collection_resilience
from ai_hiring_radar.sources.collection_resilience import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_REQUEST_DELAY_SECONDS,
    ResilientHttpRequester,
    is_valid_raw_ats_resume_file,
    raw_ats_response_path,
    read_ats_board_file,
)
from ai_hiring_radar.storage_json import write_raw_ats_response


def test_default_request_configuration() -> None:
    assert DEFAULT_REQUEST_DELAY_SECONDS == 0.5
    assert DEFAULT_MAX_RETRIES == 3


@pytest.mark.parametrize(
    ("request_delay_seconds", "max_retries"),
    [(-0.1, 0), (0, -1)],
)
def test_requester_rejects_negative_configuration(
    request_delay_seconds: float,
    max_retries: int,
) -> None:
    with httpx.Client() as http_client:
        with pytest.raises(ValueError):
            ResilientHttpRequester(
                http_client,
                request_delay_seconds=request_delay_seconds,
                max_retries=max_retries,
            )


def test_get_and_post_forward_requests_and_return_successful_responses() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"method": request.method})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        requester = ResilientHttpRequester(http_client, request_delay_seconds=0)

        get_response = requester.get(
            "https://example.test/boards",
            params={"page": 2},
        )
        post_response = requester.post(
            "https://example.test/graphql",
            json={"query": "jobs"},
        )

        assert not http_client.is_closed
        assert get_response.json() == {"method": "GET"}
        assert post_response.json() == {"method": "POST"}

    assert [request.method for request in requests] == ["GET", "POST"]
    assert requests[0].url.params["page"] == "2"
    assert json.loads(requests[1].content) == {"query": "jobs"}


@pytest.mark.parametrize("status_code", [429, 500, 502, 503, 504])
def test_requester_retries_only_retryable_statuses(status_code: int) -> None:
    attempts = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(status_code if attempts == 1 else 200)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        response = ResilientHttpRequester(
            http_client,
            request_delay_seconds=0.5,
            max_retries=1,
            sleeper=sleeps.append,
        ).get("https://example.test/jobs")

    assert response.status_code == 200
    assert attempts == 2
    assert sleeps == [1.0]


@pytest.mark.parametrize("status_code", [400, 401, 403, 404])
def test_requester_does_not_retry_terminal_client_statuses(status_code: int) -> None:
    attempts = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(status_code)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        requester = ResilientHttpRequester(
            http_client,
            sleeper=sleeps.append,
        )
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            requester.get("https://example.test/jobs")

    assert exc_info.value.response.status_code == status_code
    assert attempts == 1
    assert sleeps == []


def test_requester_does_not_retry_transport_exceptions() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("connection failed", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        requester = ResilientHttpRequester(http_client, max_retries=3)
        with pytest.raises(httpx.ConnectError):
            requester.get("https://example.test/jobs")

    assert attempts == 1


def test_max_retries_are_additional_and_backoff_is_exponential() -> None:
    attempts = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(500)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        requester = ResilientHttpRequester(
            http_client,
            request_delay_seconds=0.5,
            max_retries=3,
            sleeper=sleeps.append,
        )
        with pytest.raises(httpx.HTTPStatusError):
            requester.get("https://example.test/jobs")

    assert attempts == 4
    assert sleeps == [1.0, 2.0, 4.0]


def test_backoff_is_capped_at_thirty_seconds() -> None:
    attempts = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(502)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        requester = ResilientHttpRequester(
            http_client,
            request_delay_seconds=0,
            max_retries=7,
            sleeper=sleeps.append,
        )
        with pytest.raises(httpx.HTTPStatusError):
            requester.get("https://example.test/jobs")

    assert attempts == 8
    assert sleeps == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0]


def test_requester_paces_physical_requests_across_its_lifetime() -> None:
    statuses = iter([200, 500, 200, 200])
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(next(statuses))

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        requester = ResilientHttpRequester(
            http_client,
            request_delay_seconds=0.5,
            max_retries=1,
            sleeper=sleeps.append,
        )
        requester.get("https://example.test/first")
        requester.get("https://example.test/second")
        requester.get("https://example.test/third")

    assert sleeps == [0.5, 1.0, 0.5]


@pytest.mark.parametrize("status_code", [429, 503])
def test_retry_after_delta_seconds_honors_minimum_pacing(status_code: int) -> None:
    attempts = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(status_code, headers={"Retry-After": "7"})
        return httpx.Response(200)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        ResilientHttpRequester(
            http_client,
            request_delay_seconds=12,
            max_retries=1,
            sleeper=sleeps.append,
        ).get("https://example.test/jobs")

    assert sleeps == [12.0]


def test_retry_after_http_date_is_honored(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    retry_at = datetime(2026, 7, 10, 12, 0, 11, tzinfo=timezone.utc)
    attempts = 0
    sleeps: list[float] = []
    monkeypatch.setattr(collection_resilience, "_utc_now", lambda: now)

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(
                503,
                headers={"Retry-After": format_datetime(retry_at, usegmt=True)},
            )
        return httpx.Response(200)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        ResilientHttpRequester(
            http_client,
            request_delay_seconds=0.5,
            max_retries=1,
            sleeper=sleeps.append,
        ).get("https://example.test/jobs")

    assert sleeps == [11.0]


def test_zero_retry_after_does_not_bypass_request_pacing() -> None:
    attempts = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        ResilientHttpRequester(
            http_client,
            request_delay_seconds=0.5,
            max_retries=1,
            sleeper=sleeps.append,
        ).get("https://example.test/jobs")

    assert sleeps == [0.5]


@pytest.mark.parametrize("status_code", [500, 502, 504])
def test_retry_after_is_ignored_for_statuses_that_do_not_define_it(
    status_code: int,
) -> None:
    attempts = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(status_code, headers={"Retry-After": "20"})
        return httpx.Response(200)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        ResilientHttpRequester(
            http_client,
            request_delay_seconds=0.5,
            max_retries=1,
            sleeper=sleeps.append,
        ).get("https://example.test/jobs")

    assert sleeps == [1.0]


def test_invalid_retry_after_uses_exponential_backoff() -> None:
    attempts = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"Retry-After": "soon"})
        return httpx.Response(200)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        ResilientHttpRequester(
            http_client,
            max_retries=1,
            sleeper=sleeps.append,
        ).get("https://example.test/jobs")

    assert sleeps == [1.0]


def test_raw_ats_response_path_matches_storage_writer(tmp_path) -> None:
    expected = (
        tmp_path
        / "raw"
        / "ats"
        / "2026-07-10"
        / "greenhouse"
        / "acme-ai.json"
    )
    path = raw_ats_response_path(
        platform_company_slug="Acme AI",
        collection_date=date(2026, 7, 10),
        data_dir=tmp_path,
        platform="greenhouse",
    )
    written_path = write_raw_ats_response(
        {},
        platform_company_slug="Acme AI",
        collection_date="2026-07-10",
        data_dir=tmp_path,
        platform="greenhouse",
    )

    assert path == expected
    assert written_path == path


def test_valid_raw_ats_resume_file_requires_exact_metadata(tmp_path) -> None:
    path = tmp_path / "raw.json"
    path.write_text(
        json.dumps(
            {
                "record_type": "raw_ats_response",
                "platform": "ashby",
                "platform_company_slug": "acme-ai",
                "response": {},
            }
        ),
        encoding="utf-8",
    )

    assert is_valid_raw_ats_resume_file(
        path,
        platform="ashby",
        platform_company_slug="acme-ai",
    )
    assert not is_valid_raw_ats_resume_file(
        path,
        platform="greenhouse",
        platform_company_slug="acme-ai",
    )
    assert not is_valid_raw_ats_resume_file(
        path,
        platform="ashby",
        platform_company_slug="ACME-AI",
    )


@pytest.mark.parametrize(
    "content",
    [
        "not JSON",
        "[]",
        '{"record_type": "other", "platform": "ashby", '
        '"platform_company_slug": "acme-ai"}',
    ],
)
def test_invalid_raw_ats_resume_file_returns_false(tmp_path, content: str) -> None:
    path = tmp_path / "raw.json"
    path.write_text(content, encoding="utf-8")

    assert not is_valid_raw_ats_resume_file(
        path,
        platform="ashby",
        platform_company_slug="acme-ai",
    )


def test_missing_raw_ats_resume_file_returns_false(tmp_path) -> None:
    assert not is_valid_raw_ats_resume_file(
        tmp_path / "missing.json",
        platform="ashby",
        platform_company_slug="acme-ai",
    )


def test_read_ats_board_file_supports_jsonl_json_strings_and_plain_text(
    tmp_path,
) -> None:
    path = tmp_path / "boards.txt"
    path.write_text(
        "\n".join(
            [
                "",
                '{"board_url": "https://jobs.example/acme", '
                '"platform_company_slug": "ignored"}',
                '{"board_url": "  ", "platform_company_slug": "fallback"}',
                '{"board_url": 42, "platform_company_slug": "typed-fallback"}',
                "https://jobs.example/plain",
                "plain-slug",
                '"json-string-slug"',
                "plain-slug",
                "",
            ]
        ),
        encoding="utf-8",
    )

    assert read_ats_board_file(path) == [
        "https://jobs.example/acme",
        "fallback",
        "typed-fallback",
        "https://jobs.example/plain",
        "plain-slug",
        "json-string-slug",
        "plain-slug",
    ]


def test_read_ats_board_file_rejects_malformed_json_with_line_context(
    tmp_path,
) -> None:
    path = tmp_path / "boards.jsonl"
    path.write_text("plain-slug\n{broken JSON\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"boards\.jsonl: line 2: malformed JSON"):
        read_ats_board_file(path)


@pytest.mark.parametrize(
    "line",
    [
        "{}",
        '{"board_url": "", "platform_company_slug": null}',
        '"   "',
        "[]",
    ],
)
def test_read_ats_board_file_rejects_json_without_usable_board(
    tmp_path,
    line: str,
) -> None:
    path = tmp_path / "boards.jsonl"
    path.write_text(f"{line}\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"line 1: .*board|line 1: JSON value"):
        read_ats_board_file(path)
