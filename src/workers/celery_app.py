"""
Celery application instance.

Import this module to get the configured Celery app:

    from src.workers.celery_app import celery_app
"""
import logging
import os
from pathlib import Path
from celery import Celery
from src.core.app_config import get_app_config

# Configure logging for Celery workers
# Use /var/log in Docker, fallback to ./logs locally
if os.access("/var/log", os.W_OK):
    LOG_FILE = Path("/var/log/semantic-job-match/app.log")
else:
    LOG_FILE = Path("./logs/app.log")

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

_cfg = get_app_config()

celery_app = Celery(
    "semantic_job_match",
    broker=_cfg.REDIS_URL,
    backend=_cfg.REDIS_URL,
    include=["src.workers.tasks"],
)

celery_app.conf.update(
    # Serialisation
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Result TTL
    result_expires=_cfg.TASK_RESULT_TTL,
    # Routing — all tasks go to the default queue
    task_default_queue="match_queue",
    # Worker behaviour
    worker_prefetch_multiplier=1,        # fair dispatch: one task at a time per worker slot
    task_acks_late=True,                 # ack only after task completes (safe restart)
    task_reject_on_worker_lost=True,     # re-queue if worker dies mid-task
    # Hard time limit (seconds); task is SIGKILL'd if exceeded
    task_time_limit=_cfg.REQUEST_TIMEOUT_SECONDS + 30,
    # Soft time limit: raises SoftTimeLimitExceeded so task can clean up
    task_soft_time_limit=_cfg.REQUEST_TIMEOUT_SECONDS,
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Broker — fail fast when Redis is unreachable
    broker_connection_timeout=4.0,
    broker_connection_retry=False,
    broker_connection_max_retries=0,
    # Redis-specific socket timeouts (Celery-level settings for redis-py)
    redis_socket_connect_timeout=4,
    redis_socket_timeout=4,
    redis_retry_on_timeout=False,
    # Result backend — also fail fast; disable the 20-retry loop
    result_backend_transport_options={
        "max_connections": 10,
    },
    result_backend_connection_retry_on_startup=False,
)

