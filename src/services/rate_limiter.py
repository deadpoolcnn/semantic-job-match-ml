"""
Moonshot API rate limiter and retry/circuit-breaker wrapper.

Rate limiter:  async token-bucket, MOONSHOT_RPM_LIMIT tokens per 60 s.
Retry policy:  exponential back-off via tenacity, up to MOONSHOT_MAX_RETRIES.
Circuit breaker: after MOONSHOT_MAX_RETRIES consecutive failures on a single
                 call, tenacity raises RetryError which callers should catch.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Coroutine, TypeVar

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
    RetryError,
)

from src.core.app_config import get_app_config

logger = logging.getLogger(__name__)
_cfg = get_app_config()

T = TypeVar("T")

# ── Async token-bucket rate limiter ─────────────────────────────────────────

class AsyncTokenBucket:
    """
    Token-bucket rate limiter for use in async code.

    Allows up to `rate` requests per `period` seconds.
    Callers await `acquire()` before each LLM call; if the bucket is empty
    they block until a token is available (max wait = period).
    """

    def __init__(self, rate: int, period: float = 60.0) -> None:
        self._rate = rate          # tokens added per period
        self._period = period      # seconds
        self._tokens: float = rate
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            # Refill tokens proportional to elapsed time
            self._tokens = min(
                self._rate,
                self._tokens + elapsed * (self._rate / self._period),
            )
            self._last_refill = now

            if self._tokens >= 1:
                self._tokens -= 1
                return

            # Not enough tokens — wait until one becomes available
            wait_time = (1 - self._tokens) * (self._period / self._rate)
            logger.debug(f"[RateLimiter] Bucket empty, waiting {wait_time:.2f}s")

        await asyncio.sleep(wait_time)
        await self.acquire()  # re-acquire after sleep


# Singleton bucket — shared across all agents in the same process
_moonshot_bucket = AsyncTokenBucket(
    rate=_cfg.MOONSHOT_RPM_LIMIT,
    period=60.0,
)


async def moonshot_acquire() -> None:
    """Acquire a rate-limit token before calling the Moonshot API."""
    await _moonshot_bucket.acquire()


# ── Retry / circuit-breaker decorator factory ────────────────────────────────

def moonshot_retry(func: Callable[..., Coroutine[Any, Any, T]]) -> Callable[..., Coroutine[Any, Any, T]]:
    """
    Decorator that wraps an async Moonshot API call with:
      - Exponential back-off retry (tenacity)
      - Retries on openai.APIError, openai.RateLimitError, Exception
      - Logs before each retry sleep

    Usage:
        @moonshot_retry
        async def call_llm(...):
            await moonshot_acquire()
            return await client.chat.completions.create(...)
    """
    import openai  # imported lazily so the module works without openai installed

    decorated = retry(
        retry=retry_if_exception_type((
            openai.APIError,
            openai.RateLimitError,
            openai.APIConnectionError,
            asyncio.TimeoutError,
        )),
        stop=stop_after_attempt(_cfg.MOONSHOT_MAX_RETRIES),
        wait=wait_exponential(
            multiplier=_cfg.MOONSHOT_RETRY_WAIT_BASE,
            max=_cfg.MOONSHOT_RETRY_WAIT_MAX,
        ),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=False,   # raises RetryError after exhausting attempts
    )(func)
    return decorated


# Re-export RetryError so callers can catch it without importing tenacity
__all__ = [
    "moonshot_acquire",
    "moonshot_retry",
    "RetryError",
    "AsyncTokenBucket",
]
