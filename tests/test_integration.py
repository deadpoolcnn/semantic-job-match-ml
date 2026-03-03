"""
Integration tests for V2 API endpoints.

Requires the API server to be running at TEST_API_URL (default: http://127.0.0.1:8000).
Run: pytest tests/test_integration.py -v -s
"""

import asyncio
import io
import os
import socket
import time
from pathlib import Path

import httpx
import pytest

BASE_URL = os.getenv("TEST_API_URL", "http://127.0.0.1:8000")
ROOT = Path(__file__).resolve().parents[1]


# ── Redis availability guard ──────────────────────────────────────────────────

def _check_redis(host: str = "127.0.0.1", port: int = 6379) -> bool:
    """Return True if a TCP connection to Redis can be established."""
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


REDIS_AVAILABLE = _check_redis()

requires_redis = pytest.mark.skipif(
    not REDIS_AVAILABLE,
    reason="Redis not reachable at 127.0.0.1:6379 — Celery tests skipped",
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _fake_pdf_bytes() -> bytes:
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog >>\nendobj\n"
        b"%%EOF"
    )


def _resume_pdf_multipart(filename: str = "resume.pdf") -> dict:
    return {"file": (filename, io.BytesIO(_fake_pdf_bytes()), "application/pdf")}


# ── Smoke tests ───────────────────────────────────────────────────────────────

class TestHealthEndpoints:
    def test_root(self):
        r = httpx.get(f"{BASE_URL}/", timeout=5)
        assert r.status_code == 200
        assert "version" in r.json()

    def test_health(self):
        r = httpx.get(f"{BASE_URL}/health", timeout=5)
        assert r.status_code == 200
        assert r.json().get("status") == "healthy"

    def test_docs_available(self):
        r = httpx.get(f"{BASE_URL}/docs", timeout=5)
        assert r.status_code == 200


# ── JD Cache endpoints ────────────────────────────────────────────────────────

class TestJDCache:
    def test_cache_status(self):
        r = httpx.get(f"{BASE_URL}/api/v2/jd_cache/status", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "cached_jobs" in data
        assert "cached_mtime" in data

    def test_cache_clear_and_refill(self):
        r = httpx.delete(f"{BASE_URL}/api/v2/jd_cache", timeout=10)
        assert r.status_code == 200
        assert r.json()["status"] == "cleared"
        status = httpx.get(f"{BASE_URL}/api/v2/jd_cache/status", timeout=10).json()
        assert status["cached_jobs"] == 0


# ── Async task endpoints ──────────────────────────────────────────────────────

class TestAsyncTaskEndpoints:
    @requires_redis
    def test_enqueue_returns_202(self):
        r = httpx.post(
            f"{BASE_URL}/api/v2/match_resume_async",
            files=_resume_pdf_multipart(),
            params={"top_k": 2},
            timeout=10,
        )
        assert r.status_code == 202, r.text
        body = r.json()
        assert "task_id" in body
        assert body["status"] == "queued"
        assert body["poll_url"].startswith("/api/v2/result/")

    @requires_redis
    def test_poll_endpoint_returns_valid_status(self):
        enqueue = httpx.post(
            f"{BASE_URL}/api/v2/match_resume_async",
            files=_resume_pdf_multipart(),
            params={"top_k": 2},
            timeout=10,
        )
        assert enqueue.status_code == 202, enqueue.text
        task_id = enqueue.json()["task_id"]
        r = httpx.get(f"{BASE_URL}/api/v2/result/{task_id}", timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body["task_id"] == task_id
        assert body["status"] in ("queued", "started", "completed", "failed")

    @requires_redis
    def test_invalid_task_id_returns_queued(self):
        """Non-existent task maps to Celery PENDING -> status 'queued'."""
        r = httpx.get(f"{BASE_URL}/api/v2/result/nonexistent-task-id", timeout=10)
        assert r.status_code == 200
        assert r.json()["status"] == "queued"

    def test_wrong_file_type_rejected(self):
        """File type check runs before Celery — always testable."""
        r = httpx.post(
            f"{BASE_URL}/api/v2/match_resume_async",
            files={"file": ("data.txt", io.BytesIO(b"resume text"), "text/plain")},
            params={"top_k": 2},
            timeout=10,
        )
        assert r.status_code == 400

    @requires_redis
    def test_enqueue_response_time_under_500ms(self):
        """Enqueue must complete in <500 ms (fire-and-forget to broker)."""
        start = time.monotonic()
        r = httpx.post(
            f"{BASE_URL}/api/v2/match_resume_async",
            files=_resume_pdf_multipart(),
            params={"top_k": 2},
            timeout=10,
        )
        elapsed = time.monotonic() - start
        assert r.status_code == 202, r.text
        assert elapsed < 0.5, f"Enqueue took {elapsed:.3f}s — should be <500ms"

    def test_no_redis_returns_503(self):
        """When Redis is down the endpoint must return 503, not 500."""
        if REDIS_AVAILABLE:
            pytest.skip("Redis is up — 503 path not triggered")
        r = httpx.post(
            f"{BASE_URL}/api/v2/match_resume_async",
            files=_resume_pdf_multipart(),
            params={"top_k": 2},
            timeout=15,  # Celery broker timeout is ~4s; allow headroom
        )
        assert r.status_code == 503, r.text


# ── Concurrency tests ─────────────────────────────────────────────────────────

class TestConcurrencyLimits:
    @requires_redis
    def test_multiple_async_enqueues_get_unique_task_ids(self):
        """Each enqueue call must return a distinct task_id."""
        ids = []
        for i in range(5):
            r = httpx.post(
                f"{BASE_URL}/api/v2/match_resume_async",
                files=_resume_pdf_multipart(f"r{i}.pdf"),
                params={"top_k": 2},
                timeout=10,
            )
            assert r.status_code == 202, r.text
            ids.append(r.json()["task_id"])
        assert len(set(ids)) == 5, f"Duplicate task IDs: {ids}"

    @requires_redis
    def test_concurrent_enqueues_all_succeed(self):
        """3 simultaneous async enqueues should all get 202."""
        async def _run():
            async with httpx.AsyncClient() as client:
                return await asyncio.gather(*[
                    client.post(
                        f"{BASE_URL}/api/v2/match_resume_async",
                        files=_resume_pdf_multipart(f"resume_{i}.pdf"),
                        params={"top_k": 2},
                        timeout=30,
                    )
                    for i in range(3)
                ])

        responses = asyncio.run(_run())
        assert all(r.status_code == 202 for r in responses)

