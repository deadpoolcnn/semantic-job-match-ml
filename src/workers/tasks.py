"""
Celery tasks for async resume matching pipeline.

The worker process runs the full agent DAG and stores the result in Redis.
The API then polls /api/v2/result/{task_id} until the task completes.
"""
from __future__ import annotations

import asyncio
import logging
import traceback
from typing import Any

from celery import Task
from celery.exceptions import SoftTimeLimitExceeded

from src.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


# ── Task base class with per-worker singleton orchestrator ────────────────────

class OrchestratorTask(Task):
    """
    Celery Task subclass that holds a process-level OrchestratorAgent singleton.
    The singleton is created once per worker process (lazy, on first task run),
    so model weights and FAISS index are loaded only once regardless of how many
    tasks that worker processes.
    """
    abstract = True
    _orchestrator = None

    @property
    def orchestrator(self):
        if self._orchestrator is None:
            # Ensure NLTK data is available in the worker process
            import src.core.nltk_init  # noqa: F401
            import torch
            torch.set_num_threads(1)

            from src.agents.orchestrator import OrchestratorAgent
            self._orchestrator = OrchestratorAgent()
            logger.info("[CeleryWorker] OrchestratorAgent initialised")
        return self._orchestrator


# ── Main matching task ────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    base=OrchestratorTask,
    name="src.workers.tasks.run_match_pipeline",
    max_retries=0,           # retries handled inside agents via tenacity
    track_started=True,
)
def run_match_pipeline(
    self: OrchestratorTask,
    file_bytes: list[int],   # bytes serialised as list[int] for JSON transport
    filename: str,
    top_k: int,
    request_id: str,
) -> dict[str, Any]:
    """
    Run the full multi-agent resume matching pipeline.

    Returns a JSON-serialisable dict identical in shape to MatchV2Response
    so the polling endpoint can deserialise it directly.
    """
    logger.info(f"[{request_id}] Worker picked up task {self.request.id}")

    raw_bytes = bytes(file_bytes)

    try:
        result = asyncio.run(_run_async(self.orchestrator, raw_bytes, filename, top_k, request_id))
        logger.info(f"[{request_id}] Task {self.request.id} complete")
        return result

    except SoftTimeLimitExceeded:
        logger.error(f"[{request_id}] Task exceeded soft time limit")
        return _error_result(request_id, "Task timed out — please try again")

    except Exception as exc:
        logger.error(f"[{request_id}] Task failed: {exc}\n{traceback.format_exc()}")
        return _error_result(request_id, str(exc))


async def _run_async(
    orchestrator,
    file_bytes: bytes,
    filename: str,
    top_k: int,
    request_id: str,
) -> dict[str, Any]:
    """Execute the orchestrator DAG and serialize the result to a plain dict."""
    from src.agents.base import AgentContext

    ctx = AgentContext(
        request_id=request_id,
        file_bytes=file_bytes,
        filename=filename,
        top_k=top_k,
    )
    ctx = await orchestrator.run(ctx)
    return _serialize_ctx(ctx, request_id)


def _serialize_ctx(ctx, request_id: str) -> dict[str, Any]:
    """Convert AgentContext into a JSON-serialisable dict (mirrors MatchV2Response)."""
    from src.agents.base import AgentContext  # type: ignore

    cp = ctx.candidate_profile
    if cp is None:
        return _error_result(
            request_id,
            ctx.errors.get("resume_parser", "Resume parsing failed"),
        )

    def _milestone(m) -> dict:
        gate = None
        if m.decision_gate:
            g = m.decision_gate
            gate = {
                "year": g.year,
                "question": g.question,
                "option_A": g.option_A,
                "option_B": g.option_B,
                "impact": g.impact,
            }
        return {"year": m.year, "title": m.title, "skills_needed": m.skills_needed, "decision_gate": gate}

    def _career_path(path) -> dict | None:
        if path is None:
            return None
        return {
            "job_id": path.job_id,
            "job_title": path.job_title,
            "company": path.company,
            "trajectory_summary": path.trajectory_summary,
            "milestones": [_milestone(m) for m in path.milestones],
            "key_risks": path.key_risks,
        }

    career_prediction = None
    if ctx.career_prediction:
        pred = ctx.career_prediction
        career_prediction = {
            "current_level": pred.current_level,
            "target_role_in_5yr": pred.target_role_in_5yr,
            "milestones": [_milestone(m) for m in pred.milestones],
            "skill_gaps_to_bridge": pred.skill_gaps_to_bridge,
            "confidence_note": pred.confidence_note,
        }

    top_matches = []
    if ctx.insight_report:
        for ji in ctx.insight_report.top_jobs:
            top_matches.append({
                "job_id": ji.job_id,
                "job_title": ji.job_title,
                "company": ji.company,
                "score": ji.score,
                "five_dim_score": ji.five_dim_score,
                "why_match": ji.why_match,
                "skill_gaps": ji.skill_gaps,
                "career_fit_commentary": ji.career_fit_commentary,
                "implicit_requirements": ji.implicit_requirements,
                "counterfactual_path": _career_path(ji.counterfactual_path),
            })

    comparison_matrix = None
    if ctx.insight_report and ctx.insight_report.job_comparison_matrix:
        mx = ctx.insight_report.job_comparison_matrix
        comparison_matrix = {
            "rows": [{"dimension": r.dimension, "values": r.values} for r in mx.rows],
            "recommendation": mx.recommendation,
        }

    return {
        "status": "completed",
        "request_id": request_id,
        "candidate_summary": {
            "name": cp.name,
            "current_title": cp.current_title,
            "seniority": cp.seniority_self_reported,
            "years_of_experience": cp.years_of_experience,
            "skills": cp.skills,
            "career_objective": cp.career_objective,
        },
        "career_prediction": career_prediction,
        "top_matches": top_matches,
        "overall_summary": ctx.insight_report.overall_summary if ctx.insight_report else "",
        "development_plan": ctx.insight_report.development_plan if ctx.insight_report else "",
        "job_comparison_matrix": comparison_matrix,
        "errors": ctx.errors,
        "timings": ctx.timings,
    }


def _error_result(request_id: str, detail: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "request_id": request_id,
        "error": detail,
        "candidate_summary": None,
        "career_prediction": None,
        "top_matches": [],
        "overall_summary": "",
        "development_plan": "",
        "job_comparison_matrix": None,
        "errors": {"pipeline": detail},
        "timings": {},
    }
