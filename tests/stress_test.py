#!/usr/bin/env python3
"""
Quick async stress test — no Locust required.

Fires N concurrent requests and reports latency + success rate.

Usage:
    # Async endpoint (requires Redis)
    python tests/stress_test.py --users 10 --host http://localhost:8000
    python tests/stress_test.py --users 5  --host http://localhost:8000 --poll

    # Sync endpoint (no Redis needed, suitable for local dev)
    python tests/stress_test.py --users 3 --host http://localhost:8000 --sync
"""

import argparse
import asyncio
import io
import socket
import time
from dataclasses import dataclass
from typing import Optional

import httpx

# ── Fake PDF ──────────────────────────────────────────────────────────────────
_FAKE_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog >>\nendobj\n"
    b"%%EOF"
)


def _redis_available(host: str = "127.0.0.1", port: int = 6379) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


@dataclass
class Result:
    user_id: int
    enqueue_ms: float
    final_status: str           # queued / started / completed / failed / error
    total_ms: float
    error: Optional[str] = None


async def one_user_async(
    client: httpx.AsyncClient,
    host: str,
    user_id: int,
    poll: bool,
) -> Result:
    """Fire one request to the async endpoint (202 fire-and-forget)."""
    start = time.monotonic()
    try:
        r = await client.post(
            f"{host}/api/v2/match_resume_async",
            files={"file": ("resume.pdf", io.BytesIO(_FAKE_PDF), "application/pdf")},
            data={"top_k": "2"},
            timeout=15,
        )
    except Exception as e:
        return Result(user_id, -1, "error", (time.monotonic() - start) * 1000, str(e))

    enqueue_ms = (time.monotonic() - start) * 1000

    if r.status_code != 202:
        return Result(user_id, enqueue_ms, "error", enqueue_ms, f"HTTP {r.status_code}")

    task_id = r.json().get("task_id", "")
    final_status = r.json().get("status", "unknown")

    if poll and task_id:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            await asyncio.sleep(2)
            try:
                pr = await client.get(f"{host}/api/v2/result/{task_id}", timeout=10)
                final_status = pr.json().get("status", "unknown")
                if final_status in ("completed", "failed"):
                    break
            except Exception as e:
                final_status = f"poll_error: {e}"
                break

    return Result(user_id, enqueue_ms, final_status, (time.monotonic() - start) * 1000)


async def one_user_sync(
    client: httpx.AsyncClient,
    host: str,
    user_id: int,
) -> Result:
    """Fire one request to the sync endpoint (blocks until pipeline finishes or semaphore queues it)."""
    start = time.monotonic()
    try:
        r = await client.post(
            f"{host}/api/v2/match_resume_file",
            files={"file": ("resume.pdf", io.BytesIO(_FAKE_PDF), "application/pdf")},
            data={"top_k": "2"},
            timeout=300,  # sync endpoint can take minutes for real PDFs
        )
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        return Result(user_id, elapsed, "error", elapsed, str(e))

    elapsed = (time.monotonic() - start) * 1000
    status_str = "completed" if r.status_code == 200 else "error"
    error = None if r.status_code == 200 else f"HTTP {r.status_code}"
    return Result(user_id, elapsed, status_str, elapsed, error)


async def run(host: str, users: int, poll: bool, sync: bool) -> None:
    mode = "SYNC endpoint" if sync else "ASYNC endpoint"
    print(f"\n{'='*60}")
    print(f"  Stress test: {users} concurrent users → {host}")
    print(f"  Mode: {mode}")
    if not sync:
        print(f"  Polling for results: {'yes' if poll else 'no'}")
    print(f"{'='*60}\n")

    if not sync and not _redis_available():
        print("⚠️  Redis not reachable — the async endpoint will return 503.")
        print("   Run with --sync to use the sync endpoint instead.\n")

    async with httpx.AsyncClient() as client:
        try:
            h = await client.get(f"{host}/health", timeout=5)
            assert h.json().get("status") == "healthy"
            print(f"✅ Server healthy\n")
        except Exception as e:
            print(f"❌ Server not reachable: {e}")
            return

        wall_start = time.monotonic()
        if sync:
            results = await asyncio.gather(
                *[one_user_sync(client, host, i) for i in range(users)]
            )
        else:
            results = await asyncio.gather(
                *[one_user_async(client, host, i, poll) for i in range(users)]
            )
        wall_elapsed = time.monotonic() - wall_start

    # ── Report ────────────────────────────────────────────────────────────────
    success_statuses = {"202", "completed", "queued", "started"}
    ok = [r for r in results if r.final_status not in ("error",)]
    errors = [r for r in results if r.final_status == "error"]

    enqueue_times = [r.enqueue_ms for r in results if r.enqueue_ms > 0]
    enqueue_times.sort()
    p50 = enqueue_times[len(enqueue_times) // 2] if enqueue_times else 0
    p95 = enqueue_times[int(len(enqueue_times) * 0.95)] if enqueue_times else 0
    avg = sum(enqueue_times) / len(enqueue_times) if enqueue_times else 0

    label = "Response latency" if sync else "Enqueue latency"
    print(f"{'─'*50}")
    print(f"  Users fired      : {users}")
    print(f"  Success          : {len(ok)}")
    print(f"  Errors           : {len(errors)}")
    print(f"  Success rate     : {len(ok)/users*100:.1f}%")
    print(f"{'─'*50}")
    print(f"  {label}  :")
    print(f"    avg            : {avg:.0f}ms")
    print(f"    p50            : {p50:.0f}ms")
    print(f"    p95            : {p95:.0f}ms")
    print(f"  Wall time total  : {wall_elapsed:.1f}s")
    print(f"{'─'*50}")

    if not sync and poll:
        status_counts: dict[str, int] = {}
        for r in results:
            status_counts[r.final_status] = status_counts.get(r.final_status, 0) + 1
        print(f"  Final statuses   : {status_counts}")

    if errors:
        print(f"\n  ❌ Errors:")
        for r in errors[:5]:
            print(f"    user {r.user_id}: {r.error}")

    success_rate = len(ok) / users
    threshold_ms = 300000 if sync else 2000   # sync: 5min, async: 2s
    latency_ok = p95 < threshold_ms
    if success_rate >= 0.95 and latency_ok:
        print(f"\n✅ PASSED (success≥95%, p95<{'5min' if sync else '2s'})")
    else:
        print(f"\n❌ FAILED (success={success_rate*100:.0f}%, p95={p95:.0f}ms)")


def main():
    parser = argparse.ArgumentParser(description="Stress test for resume matching API")
    parser.add_argument("--host", default="http://127.0.0.1:8000", help="API base URL")
    parser.add_argument("--users", type=int, default=10, help="Concurrent virtual users")
    parser.add_argument("--poll", action="store_true", help="Poll result until completed (async mode only)")
    parser.add_argument("--sync", action="store_true", help="Use the sync endpoint instead of async")
    args = parser.parse_args()
    asyncio.run(run(args.host, args.users, args.poll, args.sync))


if __name__ == "__main__":
    main()


import argparse
import asyncio
import io
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

# ── Fake PDF ──────────────────────────────────────────────────────────────────
_FAKE_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog >>\nendobj\n"
    b"%%EOF"
)


@dataclass
class Result:
    user_id: int
    enqueue_ms: float
    final_status: str           # queued / started / completed / failed / error
    total_ms: float
    error: Optional[str] = None


async def one_user(
    client: httpx.AsyncClient,
    host: str,
    user_id: int,
    poll: bool,
) -> Result:
    start = time.monotonic()

    # 1. Enqueue
    try:
        r = await client.post(
            f"{host}/api/v2/match_resume_async",
            files={"file": ("resume.pdf", io.BytesIO(_FAKE_PDF), "application/pdf")},
            data={"top_k": "2"},
            timeout=15,
        )
    except Exception as e:
        return Result(user_id, -1, "error", (time.monotonic() - start) * 1000, str(e))

    enqueue_ms = (time.monotonic() - start) * 1000

    if r.status_code != 202:
        return Result(user_id, enqueue_ms, "error", enqueue_ms, f"HTTP {r.status_code}")

    task_id = r.json().get("task_id", "")
    final_status = r.json().get("status", "unknown")

    # 2. Poll until done (optional — for integration smoke-test)
    if poll and task_id:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            await asyncio.sleep(2)
            try:
                pr = await client.get(f"{host}/api/v2/result/{task_id}", timeout=10)
                final_status = pr.json().get("status", "unknown")
                if final_status in ("completed", "failed"):
                    break
            except Exception as e:
                final_status = f"poll_error: {e}"
                break

    return Result(user_id, enqueue_ms, final_status, (time.monotonic() - start) * 1000)


async def run(host: str, users: int, poll: bool) -> None:
    print(f"\n{'='*60}")
    print(f"  Stress test: {users} concurrent users → {host}")
    print(f"  Polling for results: {'yes' if poll else 'no'}")
    print(f"{'='*60}\n")

    async with httpx.AsyncClient() as client:
        # Warm-up: verify server is up
        try:
            h = await client.get(f"{host}/health", timeout=5)
            assert h.json().get("status") == "healthy"
            print(f"✅ Server healthy\n")
        except Exception as e:
            print(f"❌ Server not reachable: {e}")
            return

        wall_start = time.monotonic()
        results = await asyncio.gather(
            *[one_user(client, host, i, poll) for i in range(users)]
        )
        wall_elapsed = time.monotonic() - wall_start

    # ── Report ────────────────────────────────────────────────────────────────
    ok = [r for r in results if r.final_status not in ("error",)]
    errors = [r for r in results if r.final_status == "error"]

    enqueue_times = [r.enqueue_ms for r in results if r.enqueue_ms > 0]
    enqueue_times.sort()
    p50 = enqueue_times[len(enqueue_times) // 2] if enqueue_times else 0
    p95 = enqueue_times[int(len(enqueue_times) * 0.95)] if enqueue_times else 0
    avg = sum(enqueue_times) / len(enqueue_times) if enqueue_times else 0

    print(f"{'─'*50}")
    print(f"  Users fired      : {users}")
    print(f"  Success (202)    : {len(ok)}")
    print(f"  Errors           : {len(errors)}")
    print(f"  Success rate     : {len(ok)/users*100:.1f}%")
    print(f"{'─'*50}")
    print(f"  Enqueue latency  :")
    print(f"    avg            : {avg:.0f}ms")
    print(f"    p50            : {p50:.0f}ms")
    print(f"    p95            : {p95:.0f}ms")
    print(f"  Wall time total  : {wall_elapsed:.1f}s")
    print(f"{'─'*50}")

    if poll:
        status_counts: dict[str, int] = {}
        for r in results:
            status_counts[r.final_status] = status_counts.get(r.final_status, 0) + 1
        print(f"  Final statuses   : {status_counts}")

    if errors:
        print(f"\n  ❌ Errors:")
        for r in errors[:5]:
            print(f"    user {r.user_id}: {r.error}")

    # Pass/fail gate
    success_rate = len(ok) / users
    enqueue_ok = p95 < 2000  # 95th pct enqueue must be <2s
    if success_rate >= 0.95 and enqueue_ok:
        print(f"\n✅ PASSED (success≥95%, p95 enqueue<2s)")
    else:
        print(f"\n❌ FAILED (success={success_rate*100:.0f}%, p95={p95:.0f}ms)")


def main():
    parser = argparse.ArgumentParser(description="Async stress test for resume matching API")
    parser.add_argument("--host", default="http://127.0.0.1:8000", help="API base URL")
    parser.add_argument("--users", type=int, default=10, help="Concurrent virtual users")
    parser.add_argument("--poll", action="store_true", help="Poll result until completed")
    args = parser.parse_args()
    asyncio.run(run(args.host, args.users, args.poll))


if __name__ == "__main__":
    main()
