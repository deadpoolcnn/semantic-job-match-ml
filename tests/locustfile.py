"""
Locust stress test for the async resume matching API.

Usage:
    # Headless mode (CI / terminal)
    locust -f tests/locustfile.py \
        --headless \
        --users 10 \
        --spawn-rate 2 \
        --run-time 60s \
        --host http://localhost:8000

    # Web UI mode (open http://localhost:8089 in browser)
    locust -f tests/locustfile.py --host http://localhost:8000

Scenarios:
  - AsyncMatchUser   : POST /match_resume_async → poll /result/{id}
  - HealthCheckUser  : lightweight GET /health (background probe)
"""

import io
import time

from locust import HttpUser, TaskSet, between, task, events


# ── Minimal fake PDF ──────────────────────────────────────────────────────────

_FAKE_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog >>\nendobj\n"
    b"%%EOF"
)


# ── Task sets ─────────────────────────────────────────────────────────────────

class AsyncMatchTasks(TaskSet):
    """
    Primary scenario: enqueue a resume, then poll until done.
    Simulates a realistic user session.
    """

    @task(8)             # weight 8 — most traffic
    def enqueue_and_poll(self):
        # 1. Enqueue
        with self.client.post(
            "/api/v2/match_resume_async",
            files={"file": ("resume.pdf", io.BytesIO(_FAKE_PDF), "application/pdf")},
            data={"top_k": "2"},
            name="POST /api/v2/match_resume_async",
            catch_response=True,
        ) as enqueue_resp:
            if enqueue_resp.status_code != 202:
                enqueue_resp.failure(f"Expected 202, got {enqueue_resp.status_code}")
                return
            task_id = enqueue_resp.json().get("task_id")
            if not task_id:
                enqueue_resp.failure("No task_id in response")
                return
            enqueue_resp.success()

        # 2. Poll up to 30s
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            time.sleep(2)
            with self.client.get(
                f"/api/v2/result/{task_id}",
                name="GET /api/v2/result/{task_id}",
                catch_response=True,
            ) as poll_resp:
                if poll_resp.status_code != 200:
                    poll_resp.failure(f"Poll returned {poll_resp.status_code}")
                    return
                status = poll_resp.json().get("status", "")
                if status in ("completed", "failed"):
                    poll_resp.success()
                    return
                poll_resp.success()  # still pending, keep looping

    @task(2)             # weight 2 — some users check cache status
    def check_jd_cache(self):
        self.client.get(
            "/api/v2/jd_cache/status",
            name="GET /api/v2/jd_cache/status",
        )

    @task(1)
    def health_check(self):
        self.client.get("/health", name="GET /health")


class HealthOnlyTasks(TaskSet):
    """Lightweight background traffic — simulates monitoring probes."""

    @task
    def health(self):
        self.client.get("/health", name="GET /health [probe]")


# ── User classes ──────────────────────────────────────────────────────────────

class AsyncMatchUser(HttpUser):
    """
    Primary load user.
    Wait 1–5s between tasks to simulate real-world think time.
    """
    tasks = [AsyncMatchTasks]
    wait_time = between(1, 5)
    weight = 9


class ProbeUser(HttpUser):
    """
    Lightweight health-check user running in parallel.
    """
    tasks = [HealthOnlyTasks]
    wait_time = between(5, 10)
    weight = 1


# ── Custom event hooks ────────────────────────────────────────────────────────

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    print("\n🚀 Stress test starting...")
    print(f"  Target: {environment.host}")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    stats = environment.stats.total
    print("\n📊 Stress test complete")
    print(f"  Total requests : {stats.num_requests}")
    print(f"  Failures       : {stats.num_failures}")
    print(f"  Failure rate   : {stats.fail_ratio * 100:.1f}%")
    print(f"  Avg response   : {stats.avg_response_time:.0f}ms")
    print(f"  P95 response   : {stats.get_response_time_percentile(0.95):.0f}ms")
    print(f"  RPS            : {stats.current_rps:.1f}")
