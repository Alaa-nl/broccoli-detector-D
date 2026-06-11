"""In-memory per-key rate limiter for the /api/detect endpoint.

Process-local; a multi-instance deploy would need a shared store like Redis.
"""

import random
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict


# Fraction of allow() calls that trigger an opportunistic prune of stale keys.
# Kept small so the O(keys) scan stays rare; pruning is best-effort, so the
# exact rate doesn't matter and skipping it is always safe.
_PRUNE_PROBABILITY = 0.01


class RateLimiter:
    """Sliding-window request limiter keyed by an arbitrary string.

    Each key (typically a client IP) gets a deque of recent hit
    timestamps. On each check we drop timestamps older than the window,
    then allow the request only if the remaining count is below the cap.
    """

    def __init__(self, max_requests: int, window_seconds: float):
        """
        Args:
            max_requests: Maximum number of allowed requests per window.
            window_seconds: Length of the sliding window, in seconds.
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds

        # The model runs inference on a worker thread (run_in_threadpool),
        # so requests can touch this from multiple threads. Guard the
        # shared state with a lock.
        self._lock = threading.Lock()
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        """Record a hit for `key` and report whether it is allowed.

        Returns:
            True if the request is within the limit (and is now counted),
            False if the limit is already reached for this window.
        """
        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            hits = self._hits[key]

            while hits and hits[0] <= cutoff:
                hits.popleft()

            allowed = len(hits) < self.max_requests
            if allowed:
                hits.append(now)

        # Best-effort prune to bound memory. Must run AFTER the lock block above:
        # _prune acquires the lock itself, and re-entering would deadlock.
        if random.random() < _PRUNE_PROBABILITY:
            self._prune()

        return allowed

    def retry_after(self, key: str) -> int:
        """Seconds until the oldest in-window hit for `key` expires.

        Used to populate the Retry-After header on a 429. Returns at
        least 1 so clients always back off for a moment.
        """
        now = time.monotonic()
        with self._lock:
            # .get, not [key]: this is a pure query, and the defaultdict
            # would otherwise grow an empty deque for every key probed.
            hits = self._hits.get(key)
            if not hits:
                return 1
            seconds = self.window_seconds - (now - hits[0])
        return max(1, int(seconds) + 1)

    def _prune(self) -> None:
        """Drop keys whose windows are fully expired, to bound memory.

        Internal: called opportunistically from allow(); safe to skip.
        Without this, the dict would keep one (empty) deque per IP ever seen.
        """
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            stale = [
                key
                for key, hits in self._hits.items()
                if not hits or hits[-1] <= cutoff
            ]
            for key in stale:
                del self._hits[key]
