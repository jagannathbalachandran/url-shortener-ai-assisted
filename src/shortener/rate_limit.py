"""In-memory, per-key, fixed-window rate limiter."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import NamedTuple


class RateLimitResult(NamedTuple):
    """Outcome of a single `RateLimiter.allow` call."""

    allowed: bool
    retry_after_seconds: float


@dataclass
class _Bucket:
    """Request count for one key within its current fixed window."""

    window_start: float
    count: int


class RateLimiter:
    """Thread-safe fixed-window rate limiter, keyed by an arbitrary string.

    Each key gets its own window. Two independent mechanisms keep memory
    bounded and requests correct: `allow` always resets the calling key's
    own bucket immediately if its window has expired (never waits on a
    sweep for that), and a full eviction sweep over every tracked key
    additionally runs, but at most once per window, so an idle key that
    never calls `allow` again is still reclaimed.
    """

    def __init__(
        self,
        max_requests: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._buckets: dict[str, _Bucket] = {}
        self._last_sweep: float | None = None
        self._sweep_count = 0

    def allow(self, key: str) -> RateLimitResult:
        """Record one request for `key`; return whether it's within the limit."""
        now = self._clock()
        with self._lock:
            self._maybe_sweep(now)
            bucket = self._buckets.get(key)
            if bucket is None or now - bucket.window_start >= self._window_seconds:
                bucket = _Bucket(window_start=now, count=0)
                self._buckets[key] = bucket
            bucket.count += 1
            if bucket.count > self._max_requests:
                retry_after = self._window_seconds - (now - bucket.window_start)
                return RateLimitResult(False, max(retry_after, 0.0))
            return RateLimitResult(True, 0.0)

    def bucket_count(self) -> int:
        """Return the number of keys currently tracked (for tests)."""
        with self._lock:
            return len(self._buckets)

    def sweep_count(self) -> int:
        """Return how many full eviction sweeps have run (for tests)."""
        with self._lock:
            return self._sweep_count

    def _maybe_sweep(self, now: float) -> None:
        """Run a full eviction sweep over every key, but at most once per window."""
        due = self._last_sweep is None or now - self._last_sweep >= self._window_seconds
        if not due:
            return
        self._evict_stale(now)
        self._last_sweep = now
        self._sweep_count += 1

    def _evict_stale(self, now: float) -> None:
        """Remove buckets whose window has fully elapsed."""
        stale_keys = [
            key
            for key, bucket in self._buckets.items()
            if now - bucket.window_start >= self._window_seconds
        ]
        for key in stale_keys:
            del self._buckets[key]
