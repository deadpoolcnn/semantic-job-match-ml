"""
V2 API routes — multi-agent pipeline.

POST /api/v2/match_resume_file   Upload PDF/DOCX, run full agent DAG
GET  /api/v2/jd_cache/status     Inspect JD cache state
DELETE /api/v2/jd_cache          Manually invalidate JD cache
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from src.agents.base import AgentContext
from src.agents.orchestrator import OrchestratorAgent
from src.agents.job_analyzer_agent import _cache as _jd_cache

logger = logging.getLogger(__name__)

router_v2 = APIRouter(prefix="/api/v2", tags=["match-v2"])

# Process-level orchestrator singleton (agents hold no mutable state between requests)
_orchestrator = OrchestratorAgent()

ALLOWED_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


# ── Response models ───────────────────────────────────────────────────────────

class MilestoneOut(BaseModel):
    year: int
    title: str
    skills_needed: list[str]

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
    errors: dict
    timings: dict          # agent_name → elapsed seconds


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router_v2.post("/match_resume_file", response_model=MatchV2Response)
async def match_resume_file_v2(
    file: UploadFile = File(..., description="PDF or DOCX resume"),
    top_k: int = 3,
):
    """
    Multi-agent resume matching pipeline.

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

    # Run the full agent DAG with the uploaded file and parameters.
    # return andidate_profile, career_prediction, scored_results, analyzed_jobs, insight_report
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
                MilestoneOut(year=m.year, title=m.title, skills_needed=m.skills_needed)
                for m in pred.milestones
            ],
            skill_gaps_to_bridge=pred.skill_gaps_to_bridge,
            confidence_note=pred.confidence_note,
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
            ))

    overall_summary = ctx.insight_report.overall_summary if ctx.insight_report else ""
    development_plan = ctx.insight_report.development_plan if ctx.insight_report else ""

    logger.info(f"[{request_id}] V2 done | matches={len(top_matches)} | errors={ctx.errors or 'none'} | timings={ctx.timings}")
    return MatchV2Response(
        request_id=request_id,
        candidate_summary=candidate_summary,
        career_prediction=career_out,
        top_matches=top_matches,
        overall_summary=overall_summary,
        development_plan=development_plan,
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
