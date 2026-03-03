"""
Centralized application configuration.

All tunable operational knobs live here so they can be overridden
via environment variables without touching any other file.
"""
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
import os

_root = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=_root / ".env")


@lru_cache(maxsize=1)
def get_app_config() -> "AppConfig":
    return AppConfig()


class AppConfig:
    """
    All values are read from env vars at *instance creation* time so that
    monkeypatching env vars in tests (and cache_clear + re-calling
    get_app_config()) correctly picks up the new values.
    """

    def __init__(self) -> None:
        # ── Concurrency ──────────────────────────────────────────────────────
        self.MAX_CONCURRENT_REQUESTS: int = int(os.getenv("MAX_CONCURRENT_REQUESTS", "2"))

        # ── Request timeout ──────────────────────────────────────────────────
        self.REQUEST_TIMEOUT_SECONDS: int = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "120"))

        # ── Moonshot API rate limiting ────────────────────────────────────────
        self.MOONSHOT_RPM_LIMIT: int = int(os.getenv("MOONSHOT_RPM_LIMIT", "30"))

        # ── Moonshot retry / circuit breaker ─────────────────────────────────
        self.MOONSHOT_MAX_RETRIES: int = int(os.getenv("MOONSHOT_MAX_RETRIES", "3"))
        self.MOONSHOT_RETRY_WAIT_BASE: float = float(os.getenv("MOONSHOT_RETRY_WAIT_BASE", "2.0"))
        self.MOONSHOT_RETRY_WAIT_MAX: float = float(os.getenv("MOONSHOT_RETRY_WAIT_MAX", "30.0"))

        # ── JD cache ─────────────────────────────────────────────────────────
        self.JD_CACHE_REFRESH_INTERVAL: int = int(os.getenv("JD_CACHE_REFRESH_INTERVAL", "0"))

        # ── Redis / Celery ───────────────────────────────────────────────────
        self.REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.TASK_RESULT_TTL: int = int(os.getenv("TASK_RESULT_TTL", "3600"))

        # ── Celery worker ─────────────────────────────────────────────────────
        self.CELERY_WORKER_CONCURRENCY: int = int(os.getenv("CELERY_WORKER_CONCURRENCY", "1"))
