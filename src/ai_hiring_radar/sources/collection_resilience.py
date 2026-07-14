from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import httpx

from ai_hiring_radar.storage_json import (
    DEFAULT_ATS_PLATFORM,
    DEFAULT_DATA_DIR,
    raw_ats_dir,
    stable_board_filename,
)


DEFAULT_REQUEST_DELAY_SECONDS = 0.5
DEFAULT_MAX_RETRIES = 3

_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
_RETRY_AFTER_STATUS_CODES = frozenset({429, 503})
_BACKOFF_BASE_SECONDS = 1.0
_BACKOFF_CAP_SECONDS = 30.0


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _retry_after_seconds(value: str | None) -> float | None:
    if value is None:
        return None

    value = value.strip()
    if value and all("0" <= character <= "9" for character in value):
        return float(value)

    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if retry_at is None:
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=timezone.utc)

    return max((retry_at.astimezone(timezone.utc) - _utc_now()).total_seconds(), 0.0)


def _retry_delay_seconds(response: httpx.Response, retry_number: int) -> float:
    if response.status_code in _RETRY_AFTER_STATUS_CODES:
        retry_after = _retry_after_seconds(response.headers.get("Retry-After"))
        if retry_after is not None:
            return retry_after

    exponent = min(retry_number - 1, 5)
    return min(_BACKOFF_BASE_SECONDS * (2**exponent), _BACKOFF_CAP_SECONDS)


class ResilientHttpRequester:
    def __init__(
        self,
        http_client: httpx.Client,
        *,
        request_delay_seconds: float = DEFAULT_REQUEST_DELAY_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if request_delay_seconds < 0:
            raise ValueError("request_delay_seconds must not be negative")
        if max_retries < 0:
            raise ValueError("max_retries must not be negative")

        self._http_client = http_client
        self._request_delay_seconds = request_delay_seconds
        self._max_retries = max_retries
        self._sleeper = sleeper
        self._request_count = 0

    def _wait_before_request(self, retry_delay_seconds: float | None) -> None:
        if self._request_count == 0:
            return

        delay = self._request_delay_seconds
        if retry_delay_seconds is not None:
            delay = max(delay, retry_delay_seconds)
        if delay > 0:
            self._sleeper(delay)

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        retry_delay_seconds: float | None = None

        for retry_count in range(self._max_retries + 1):
            self._wait_before_request(retry_delay_seconds)
            self._request_count += 1

            response = self._http_client.request(method, url, **kwargs)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError:
                if (
                    response.status_code not in _RETRYABLE_STATUS_CODES
                    or retry_count >= self._max_retries
                ):
                    raise
                retry_delay_seconds = _retry_delay_seconds(
                    response,
                    retry_number=retry_count + 1,
                )
                continue

            return response

        raise AssertionError("unreachable")

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)


def raw_ats_response_path(
    *,
    platform_company_slug: str,
    collection_date: date | str | None = None,
    data_dir: Path = DEFAULT_DATA_DIR,
    platform: str = DEFAULT_ATS_PLATFORM,
) -> Path:
    return raw_ats_dir(
        collection_date,
        data_dir=data_dir,
        platform=platform,
    ) / stable_board_filename(platform_company_slug=platform_company_slug)


def is_valid_raw_ats_resume_file(
    path: Path,
    *,
    platform: str,
    platform_company_slug: str,
) -> bool:
    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError):
        return False

    return (
        isinstance(payload, dict)
        and payload.get("record_type") == "raw_ats_response"
        and payload.get("platform") == platform
        and payload.get("platform_company_slug") == platform_company_slug
    )


def _board_line_error(
    path: Path,
    line_number: int,
    line: str,
    message: str,
) -> ValueError:
    return ValueError(f"{path}: line {line_number}: {message}: {line!r}")


def read_ats_board_file(path: Path) -> list[str]:
    boards: list[str] = []

    with path.open("r", encoding="utf-8") as file:
        for line_number, raw_line in enumerate(file, start=1):
            line = raw_line.strip()
            if not line:
                continue

            if line[0] not in '{["}]':
                boards.append(line)
                continue

            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise _board_line_error(
                    path,
                    line_number,
                    line,
                    "malformed JSON",
                ) from exc

            if isinstance(value, str):
                board = value.strip()
                if board:
                    boards.append(board)
                    continue
                raise _board_line_error(
                    path,
                    line_number,
                    line,
                    "JSON string does not contain a usable board value",
                )

            if isinstance(value, dict):
                for key in ("board_url", "platform_company_slug"):
                    board_value = value.get(key)
                    if isinstance(board_value, str) and board_value.strip():
                        boards.append(board_value.strip())
                        break
                else:
                    raise _board_line_error(
                        path,
                        line_number,
                        line,
                        "JSON object does not contain a usable board_url or platform_company_slug",
                    )
                continue

            raise _board_line_error(
                path,
                line_number,
                line,
                "JSON value must be an object or string",
            )

    return boards
