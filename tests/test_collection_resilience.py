import pytest


@pytest.mark.skip(reason="TDD stub - not yet implemented")
def test_resilient_http_retries_transient_status() -> None:
    """(07-ats-collection-resilience, US-4)

    The shared ATS HTTP helper should retry transient HTTP responses such as
    429 and 5xx using Retry-After or capped exponential backoff before surfacing
    the final failure.
    """
    raise NotImplementedError("TDD stub - transient ATS HTTP retry")
