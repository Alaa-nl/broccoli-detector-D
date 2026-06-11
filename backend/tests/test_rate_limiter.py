"""Unit tests for the sliding-window rate limiter."""

import time

from app.services.rate_limiter import RateLimiter


def test_allows_up_to_max_then_denies():
    limiter = RateLimiter(max_requests=3, window_seconds=60)
    assert [limiter.allow("client") for _ in range(3)] == [True, True, True]
    # The cap is reached; the next hit in the same window is refused.
    assert limiter.allow("client") is False


def test_retry_after_is_at_least_one_second():
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    limiter.allow("client")
    assert limiter.allow("client") is False
    # Retry-After must be >= 1 so clients always back off for a moment;
    # with a 60 s window it should be close to the full window.
    retry = limiter.retry_after("client")
    assert retry >= 1
    assert retry <= 61


def test_retry_after_for_unknown_key_defaults_to_one():
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    assert limiter.retry_after("never-seen") == 1


def test_window_expiry_readmits_the_client():
    # A short real window keeps the test honest (the limiter uses
    # time.monotonic internally, so we wait it out rather than mock it).
    limiter = RateLimiter(max_requests=1, window_seconds=0.2)
    assert limiter.allow("client") is True
    assert limiter.allow("client") is False
    time.sleep(0.3)
    assert limiter.allow("client") is True


def test_keys_are_independent():
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    assert limiter.allow("alice") is True
    assert limiter.allow("alice") is False
    # Another client is unaffected by alice exhausting her budget.
    assert limiter.allow("bob") is True
