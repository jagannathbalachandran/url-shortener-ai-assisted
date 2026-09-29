"""Unit tests for the in-memory RateLimiter."""

from __future__ import annotations

import threading

from shortener.rate_limit import RateLimiter


class FakeClock:
    """A manually-advanced clock for deterministic window tests."""

    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


def test_requests_within_limit_are_allowed() -> None:
    limiter = RateLimiter(max_requests=3, window_seconds=60.0, clock=FakeClock())

    results = [limiter.allow("1.2.3.4") for _ in range(3)]

    assert all(result.allowed for result in results)


def test_request_over_limit_is_rejected_with_retry_after() -> None:
    clock = FakeClock()
    limiter = RateLimiter(max_requests=2, window_seconds=60.0, clock=clock)
    limiter.allow("1.2.3.4")
    limiter.allow("1.2.3.4")

    result = limiter.allow("1.2.3.4")

    assert result.allowed is False
    assert result.retry_after_seconds == 60.0


def test_requests_succeed_again_after_the_window_passes() -> None:
    clock = FakeClock()
    limiter = RateLimiter(max_requests=1, window_seconds=60.0, clock=clock)
    limiter.allow("1.2.3.4")
    assert limiter.allow("1.2.3.4").allowed is False

    clock.advance(60.0)

    assert limiter.allow("1.2.3.4").allowed is True


def test_different_keys_have_independent_limits() -> None:
    limiter = RateLimiter(max_requests=1, window_seconds=60.0, clock=FakeClock())
    limiter.allow("1.2.3.4")

    result = limiter.allow("5.6.7.8")

    assert result.allowed is True


def test_expired_key_resets_even_when_no_sweep_has_run_yet() -> None:
    clock = FakeClock()
    limiter = RateLimiter(max_requests=1, window_seconds=60.0, clock=clock)
    limiter.allow("A")  # t=0: first-ever call, always sweeps (empty dict).
    clock.advance(30.0)
    limiter.allow("B")  # t=30: 30s since last sweep, no sweep due.

    clock.advance(35.0)  # t=65: pushes the global sweep timer past due.
    limiter.allow("A")  # A is stale (65-0=65>=60): sweep runs, evicts A.
    sweeps_before = limiter.sweep_count()

    clock.advance(30.0)  # t=95: only 30s since the sweep at t=65 -- not due.
    result = limiter.allow("B")  # B's own bucket (ws=30) is stale: 95-30=65>=60.

    # No new sweep ran, yet B's own expired bucket still reset and was
    # allowed again (max_requests=1 would reject it if the stale count of
    # 1 had carried over instead of being reset on this call).
    assert limiter.sweep_count() == sweeps_before
    assert result.allowed is True


def test_sweep_runs_at_most_once_per_window() -> None:
    clock = FakeClock()
    limiter = RateLimiter(max_requests=100, window_seconds=60.0, clock=clock)
    limiter.allow("A")  # First-ever call always sweeps (empty dict).
    assert limiter.sweep_count() == 1

    clock.advance(10.0)
    limiter.allow("B")
    clock.advance(10.0)
    limiter.allow("C")
    clock.advance(10.0)
    limiter.allow("D")

    # 30s have passed since the first sweep, well under the 60s window:
    # none of these calls were due for another sweep.
    assert limiter.sweep_count() == 1


def test_idle_entries_are_evicted_after_the_window_passes() -> None:
    clock = FakeClock()
    limiter = RateLimiter(max_requests=5, window_seconds=60.0, clock=clock)
    limiter.allow("1.2.3.4")
    limiter.allow("5.6.7.8")
    assert limiter.bucket_count() == 2

    clock.advance(60.0)
    limiter.allow("9.9.9.9")

    # The two idle buckets were evicted; only the fresh key remains.
    assert limiter.bucket_count() == 1


def test_allow_is_thread_safe_under_concurrent_calls() -> None:
    call_count = 200
    limiter = RateLimiter(
        max_requests=call_count, window_seconds=60.0, clock=FakeClock()
    )

    def _call() -> None:
        limiter.allow("1.2.3.4")

    threads = [threading.Thread(target=_call) for _ in range(call_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    # If a concurrent update were lost, the bucket's count would be under
    # call_count and this next call would incorrectly still be allowed.
    assert limiter.allow("1.2.3.4").allowed is False
