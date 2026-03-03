"""
Unit tests for:
  - AppConfig values and env override
  - AsyncTokenBucket rate limiting behaviour
  - JD cache concurrent-safe rebuild (asyncio.Lock double-check)
"""

import asyncio
import os
import time

import pytest
import pytest_asyncio


# ── AppConfig ─────────────────────────────────────────────────────────────────

class TestAppConfig:
    def test_defaults(self):
        # Import fresh (lru_cache already called, check defaults match)
        from src.core.app_config import get_app_config
        cfg = get_app_config()
        assert cfg.MAX_CONCURRENT_REQUESTS == 2
        assert cfg.MOONSHOT_RPM_LIMIT == 30
        assert cfg.CELERY_WORKER_CONCURRENCY == 1
        assert cfg.REQUEST_TIMEOUT_SECONDS == 120
        assert cfg.MOONSHOT_MAX_RETRIES == 3

    def test_env_override(self, monkeypatch):
        """Env vars should override defaults when config is reloaded."""
        from src.core import app_config
        monkeypatch.setenv("MAX_CONCURRENT_REQUESTS", "10")
        monkeypatch.setenv("MOONSHOT_RPM_LIMIT", "60")

        # Clear lru_cache so env vars are re-read
        app_config.get_app_config.cache_clear()
        cfg = app_config.get_app_config()
        assert cfg.MAX_CONCURRENT_REQUESTS == 10
        assert cfg.MOONSHOT_RPM_LIMIT == 60

        # Restore
        app_config.get_app_config.cache_clear()


# ── AsyncTokenBucket ──────────────────────────────────────────────────────────

class TestAsyncTokenBucket:
    @pytest.mark.asyncio
    async def test_first_requests_are_instant(self):
        """The first N requests within the rate should not wait."""
        from src.services.rate_limiter import AsyncTokenBucket
        bucket = AsyncTokenBucket(rate=5, period=60.0)
        start = time.monotonic()
        for _ in range(5):
            await bucket.acquire()
        elapsed = time.monotonic() - start
        assert elapsed < 0.2, f"First 5 requests should be instant, took {elapsed:.2f}s"

    @pytest.mark.asyncio
    async def test_excess_requests_are_throttled(self):
        """Requests beyond the rate should be delayed."""
        from src.services.rate_limiter import AsyncTokenBucket
        # 2 tokens per second; 3rd request must wait ~0.5s
        bucket = AsyncTokenBucket(rate=2, period=1.0)
        start = time.monotonic()
        await bucket.acquire()
        await bucket.acquire()
        await bucket.acquire()   # should wait
        elapsed = time.monotonic() - start
        assert elapsed >= 0.4, f"3rd request should have waited, elapsed={elapsed:.2f}s"

    @pytest.mark.asyncio
    async def test_concurrent_acquires_respect_rate(self):
        """Concurrent callers should all get tokens, just some wait."""
        from src.services.rate_limiter import AsyncTokenBucket
        bucket = AsyncTokenBucket(rate=3, period=1.0)
        start = time.monotonic()
        await asyncio.gather(*[bucket.acquire() for _ in range(6)])
        elapsed = time.monotonic() - start
        # 6 requests at 3/s takes ~1s
        assert elapsed >= 0.9, f"Should have throttled, elapsed={elapsed:.2f}s"


# ── JD Cache concurrency ──────────────────────────────────────────────────────

class TestJDCacheConcurrency:
    @pytest.mark.asyncio
    async def test_lock_prevents_double_rebuild(self, monkeypatch):
        """
        Simulate 5 concurrent cache-miss triggers.
        The rebuild function should be called exactly ONCE.
        """
        import src.agents.job_analyzer_agent as jaa

        rebuild_count = 0
        original_rebuild = jaa._rebuild_cache

        async def counting_rebuild(mtime):
            nonlocal rebuild_count
            rebuild_count += 1
            await asyncio.sleep(0.05)   # simulate network latency
            # Fake cache result so the double-check passes
            jaa._cache["mtime"] = mtime
            jaa._cache["results"] = {"fake_job": object()}

        monkeypatch.setattr(jaa, "_rebuild_cache", counting_rebuild)
        monkeypatch.setattr(jaa, "_get_mtime", lambda: 12345.0)

        # Reset cache to cold state
        jaa._cache["mtime"] = None
        jaa._cache["results"] = {}

        # 5 concurrent cold-start hits
        from src.agents.base import AgentContext
        agents = [jaa.JobAnalyzerAgent() for _ in range(5)]
        ctxs = [AgentContext(request_id=f"test_{i}", file_bytes=b"", filename="", top_k=3)
                for i in range(5)]

        await asyncio.gather(*[a.run(c) for a, c in zip(agents, ctxs)])

        assert rebuild_count == 1, (
            f"Cache should be rebuilt exactly once, but was rebuilt {rebuild_count} times"
        )

    @pytest.mark.asyncio
    async def test_cache_hit_skips_rebuild(self, monkeypatch):
        """A warm cache should return immediately without rebuilding."""
        import src.agents.job_analyzer_agent as jaa

        class FakeAnalyzed:
            class posting:
                job_id = "j1"

        jaa._cache["mtime"] = 99999.0
        jaa._cache["results"] = {"j1": FakeAnalyzed()}
        monkeypatch.setattr(jaa, "_get_mtime", lambda: 99999.0)

        from src.agents.base import AgentContext
        ctx = AgentContext(request_id="hit_test", file_bytes=b"", filename="", top_k=3)
        agent = jaa.JobAnalyzerAgent()
        await agent.run(ctx)

        assert len(ctx.analyzed_jobs) == 1
