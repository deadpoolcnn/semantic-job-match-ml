"""
V2 API routes — multi-agent pipeline.

POST /api/v2/match_resume_file        Sync endpoint (blocks until done, ~15-25s)
POST /api/v2/match_resume_async       Async endpoint — returns task_id immediately (<100ms)
GET  /api/v2/result/{task_id}         Poll for async task result
GET  /api/v2/jd_cache/status          Inspect JD cache state
DELETE /api/v2/jd_cache               Manually invalidate JD cache
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from src.agents.base import AgentContext
from src.agents.orchestrator import OrchestratorAgent
from src.agents.job_analyzer_agent import _cache as _jd_cache
from src.core.app_config import get_app_config

logger = logging.getLogger(__name__)

_cfg = get_app_config()

router_v2 = APIRouter(prefix="/api/v2", tags=["match-v2"])

# Semaphore limits concurrent requests on the sync endpoint
_sync_semaphore = asyncio.Semaphore(_cfg.MAX_CONCURRENT_REQUESTS)

# Process-level orchestrator singleton (agents hold no mutable state between requests)
_orchestrator = OrchestratorAgent()

ALLOWED_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


# ── Response models ───────────────────────────────────────────────────────────

class DecisionGateOut(BaseModel):
    year: int
    question: str
    option_A: str
    option_B: str
    impact: str

class MilestoneOut(BaseModel):
    year: int
    title: str
    skills_needed: list[str]
    decision_gate: Optional[DecisionGateOut] = None

class JobCareerPathOut(BaseModel):
    job_id: str
    job_title: str
    company: str
    trajectory_summary: str
    milestones: list[MilestoneOut]
    key_risks: list[str]

class CareerPredictionOut(BaseModel):
    current_level: str
    target_role_in_5yr: str
    milestones: list[MilestoneOut]
    skill_gaps_to_bridge: list[str]
    confidence_note: str

class JobInsightOut(BaseModel):
    job_id: str
    job_title: str
    company: str
    score: float
    five_dim_score: dict
    why_match: list[str]
    skill_gaps: list[str]
    career_fit_commentary: str
    implicit_requirements: list[str]
    counterfactual_path: Optional[JobCareerPathOut] = None

class ComparisonRowOut(BaseModel):
    dimension: str
    values: dict[str, str]

class JobComparisonMatrixOut(BaseModel):
    rows: list[ComparisonRowOut]
    recommendation: str

class CandidateSummaryOut(BaseModel):
    name: str
    current_title: str
    seniority: Optional[str]
    years_of_experience: Optional[float]
    skills: list[str]
    career_objective: str

class MatchV2Response(BaseModel):
    request_id: str
    candidate_summary: CandidateSummaryOut
    career_prediction: Optional[CareerPredictionOut]
    top_matches: list[JobInsightOut]
    overall_summary: str
    development_plan: str
    job_comparison_matrix: Optional[JobComparisonMatrixOut] = None
    errors: dict
    timings: dict          # agent_name → elapsed seconds


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router_v2.post("/match_resume_file", response_model=MatchV2Response)
async def match_resume_file_v2(
    file: UploadFile = File(..., description="PDF or DOCX resume"),
    top_k: int = 3,
):
    """
    Synchronous multi-agent pipeline (blocks until done, ~15-25s).
    Limited to MAX_CONCURRENT_REQUESTS simultaneous calls; excess requests queue on
    the semaphore. For high-concurrency use POST /match_resume_async instead.

    Phase 1 (parallel): ResumeParserAgent + JobAnalyzerAgent
    Phase 2 (parallel): MatchScorerAgent + CareerPathPredictorAgent
    Phase 3 (serial):   InsightGeneratorAgent
    """
    request_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    logger.info(f"[{request_id}] V2 upload | {file.filename} | top_k={top_k}")

    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Only PDF/DOCX supported.")

    file_bytes = await file.read()
    logger.info(f"[{request_id}] File size: {len(file_bytes)/1024:.1f} KB")

    ctx = AgentContext(
        request_id=request_id,
        file_bytes=file_bytes,
        filename=file.filename or "",
        top_k=top_k,
    )

    async with _sync_semaphore:
        ctx = await _orchestrator.run(ctx)

    # Hard abort: resume parsing must succeed
    if ctx.candidate_profile is None:
        error_detail = ctx.errors.get("resume_parser", "Unknown parse error")
        raise HTTPException(status_code=500, detail=f"Resume parsing failed: {error_detail}")

    cp = ctx.candidate_profile

    candidate_summary = CandidateSummaryOut(
        name=cp.name,
        current_title=cp.current_title,
        seniority=cp.seniority_self_reported,
        years_of_experience=cp.years_of_experience,
        skills=cp.skills,
        career_objective=cp.career_objective,
    )

    career_out: Optional[CareerPredictionOut] = None
    if ctx.career_prediction:
        pred = ctx.career_prediction
        career_out = CareerPredictionOut(
            current_level=pred.current_level,
            target_role_in_5yr=pred.target_role_in_5yr,
            milestones=[
                MilestoneOut(
                    year=m.year,
                    title=m.title,
                    skills_needed=m.skills_needed,
                    decision_gate=DecisionGateOut(
                        year=m.decision_gate.year,
                        question=m.decision_gate.question,
                        option_A=m.decision_gate.option_A,
                        option_B=m.decision_gate.option_B,
                        impact=m.decision_gate.impact,
                    ) if m.decision_gate else None,
                )
                for m in pred.milestones
            ],
            skill_gaps_to_bridge=pred.skill_gaps_to_bridge,
            confidence_note=pred.confidence_note,
        )

    def _milestone_out(m) -> MilestoneOut:
        """Convert a Milestone dataclass (possibly with DecisionGate) to MilestoneOut."""
        gate = None
        if m.decision_gate:
            gate = DecisionGateOut(
                year=m.decision_gate.year,
                question=m.decision_gate.question,
                option_A=m.decision_gate.option_A,
                option_B=m.decision_gate.option_B,
                impact=m.decision_gate.impact,
            )
        return MilestoneOut(year=m.year, title=m.title, skills_needed=m.skills_needed, decision_gate=gate)

    def _career_path_out(path) -> Optional[JobCareerPathOut]:
        if path is None:
            return None
        return JobCareerPathOut(
            job_id=path.job_id,
            job_title=path.job_title,
            company=path.company,
            trajectory_summary=path.trajectory_summary,
            milestones=[_milestone_out(m) for m in path.milestones],
            key_risks=path.key_risks,
        )

    top_matches: list[JobInsightOut] = []
    if ctx.insight_report:
        for ji in ctx.insight_report.top_jobs:
            top_matches.append(JobInsightOut(
                job_id=ji.job_id,
                job_title=ji.job_title,
                company=ji.company,
                score=ji.score,
                five_dim_score=ji.five_dim_score,
                why_match=ji.why_match,
                skill_gaps=ji.skill_gaps,
                career_fit_commentary=ji.career_fit_commentary,
                implicit_requirements=ji.implicit_requirements,
                counterfactual_path=_career_path_out(ji.counterfactual_path),
            ))

    overall_summary = ctx.insight_report.overall_summary if ctx.insight_report else ""
    development_plan = ctx.insight_report.development_plan if ctx.insight_report else ""

    comparison_matrix_out: Optional[JobComparisonMatrixOut] = None
    if ctx.insight_report and ctx.insight_report.job_comparison_matrix:
        mx = ctx.insight_report.job_comparison_matrix
        comparison_matrix_out = JobComparisonMatrixOut(
            rows=[ComparisonRowOut(dimension=r.dimension, values=r.values) for r in mx.rows],
            recommendation=mx.recommendation,
        )

    logger.info(f"[{request_id}] V2 done | matches={len(top_matches)} | errors={ctx.errors or 'none'} | timings={ctx.timings}")
    return MatchV2Response(
        request_id=request_id,
        candidate_summary=candidate_summary,
        career_prediction=career_out,
        top_matches=top_matches,
        overall_summary=overall_summary,
        development_plan=development_plan,
        job_comparison_matrix=comparison_matrix_out,
        errors=ctx.errors,
        timings=ctx.timings,
    )


@router_v2.get("/jd_cache/status")
def jd_cache_status():
    """Inspect current JD cache state."""
    return {
        "cached_mtime": _jd_cache.get("mtime"),
        "cached_jobs": len(_jd_cache.get("results", {})),
        "job_ids": list(_jd_cache.get("results", {}).keys()),
    }


@router_v2.delete("/jd_cache")
def jd_cache_clear():
    """Force-invalidate the JD cache. Next request will re-analyze all JDs."""
    _jd_cache["mtime"] = None
    _jd_cache["results"] = {}
    logger.info("JD cache manually cleared")
    return {"status": "cleared"}


# ── Async task endpoints ───────────────────────────────────────────────────────

class TaskEnqueuedResponse(BaseModel):
    task_id: str
    status: str   # "queued"
    poll_url: str


class TaskResultResponse(BaseModel):
    task_id: str
    status: str   # "queued" | "started" | "completed" | "failed"
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None


@router_v2.post(
    "/match_resume_async",
    response_model=TaskEnqueuedResponse,
    status_code=202,
    summary="Enqueue resume matching (async)",
)
async def match_resume_async(
    file: UploadFile = File(..., description="PDF or DOCX resume"),
    top_k: int = 3,
):
    """
    Enqueue a resume matching job and return immediately (<100ms).

    The client should poll **GET /api/v2/result/{task_id}** until
    `status` is `"completed"` or `"failed"`.
    """
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Only PDF/DOCX supported.")

    file_bytes = await file.read()
    request_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    # Celery requires JSON-serialisable args — send bytes as list[int]
    _bytes_list = list(file_bytes)
    _filename = file.filename or ""

    def _enqueue():
        from src.workers.tasks import run_match_pipeline
        return run_match_pipeline.delay(
            file_bytes=_bytes_list,
            filename=_filename,
            top_k=top_k,
            request_id=request_id,
        )

    try:
        loop = asyncio.get_event_loop()
        task = await asyncio.wait_for(
            loop.run_in_executor(None, _enqueue),
            timeout=6.0,  # Fail fast if Redis is unreachable
        )
    except (asyncio.TimeoutError, Exception) as exc:
        logger.error(f"[{request_id}] Broker unavailable: {exc}")
        raise HTTPException(
            status_code=503,
            detail="Task queue unavailable — Redis broker is not reachable.",
        ) from exc

    logger.info(f"[{request_id}] Task enqueued | task_id={task.id} | {file.filename} | top_k={top_k}")
    return TaskEnqueuedResponse(
        task_id=task.id,
        status="queued",
        poll_url=f"/api/v2/result/{task.id}",
    )


@router_v2.get(
    "/result/{task_id}",
    response_model=TaskResultResponse,
    summary="Poll async task result",
)
def get_task_result(task_id: str):
    """
    Poll the status and result of an async matching task.

    | `status`    | Meaning                                  |
    |-------------|------------------------------------------|
    | `queued`    | Waiting in Redis queue                   |
    | `started`   | Worker has picked it up                  |
    | `completed` | Done — `result` field contains the data  |
    | `failed`    | Pipeline error — check `error` field     |
    """
    from celery.result import AsyncResult
    from src.workers.celery_app import celery_app

    try:
        res = AsyncResult(task_id, app=celery_app)
        # Force a backend connection to detect broker unavailability early
        state = res.state
    except Exception as exc:
        logger.error(f"Broker unavailable when polling {task_id}: {exc}")
        raise HTTPException(
            status_code=503,
            detail="Task queue unavailable — Redis broker is not reachable.",
        ) from exc

    if state in ("PENDING", "RECEIVED"):
        return TaskResultResponse(task_id=task_id, status="queued")

    if state == "STARTED":
        return TaskResultResponse(task_id=task_id, status="started")

    if state == "SUCCESS":
        payload: dict = res.result or {}
        # Worker may have returned a failed-pipeline result (not a Celery failure)
        if payload.get("status") == "failed":
            return TaskResultResponse(
                task_id=task_id,
                status="failed",
                error=payload.get("error", "Unknown error"),
            )
        return TaskResultResponse(task_id=task_id, status="completed", result=payload)

    if state == "FAILURE":
        return TaskResultResponse(
            task_id=task_id,
            status="failed",
            error=str(res.result),
        )

    # REVOKED / other
    return TaskResultResponse(task_id=task_id, status=state.lower())
