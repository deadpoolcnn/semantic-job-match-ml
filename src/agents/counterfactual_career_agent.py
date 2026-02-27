"""
CounterfactualCareerAgent: per-job "what if you take this role" trajectory.

Runs in Phase 2 (parallel with MatchScorerAgent + CareerPathPredictorAgent).
One Moonshot call per AnalyzedJob → all concurrent via asyncio.gather.

For each job it generates:
- 3 milestones (Y1 / Y3 / Y5) with optional DecisionGate forks
- key_risks list
- trajectory_summary label (e.g. "Y1: Tech Lead → Y3: EM → Y5: VP Eng")

CounterfactualCareerAgent：针对每个岗位生成"如果你接受这个 offer"的专属职业轨迹。
在第二阶段与 MatchScorerAgent 和 CareerPathPredictorAgent 并行运行。
每个 AnalyzedJob 发起一次 Moonshot 调用，所有调用通过 asyncio.gather 并发执行。
"""

import asyncio
import json
import logging

from openai import AsyncOpenAI

from src.agents.base import AgentBase, AgentContext
from src.models.agent_schemas import DecisionGate, JobCareerPath, Milestone
from src.core.config import get_moonshot_api_key, get_moonshot_model

logger = logging.getLogger(__name__)

_client = AsyncOpenAI(
    api_key=get_moonshot_api_key(),
    base_url="https://api.moonshot.ai/v1",
)
MOONSHOT_MODEL = get_moonshot_model()


async def _predict_for_job(
    candidate_name: str,
    current_title: str,
    seniority: str,
    skills: list[str],
    years_exp: float,
    job_id: str,
    job_title: str,
    company: str,
    description: str,
    requirements: list[str],
    implicit_requirements: list[str],
) -> JobCareerPath:
    """
    Single Moonshot call: generate a job-specific counterfactual career path.
    单次 Moonshot 调用：生成针对特定岗位的反事实职业路径。
    """
    prompt = f"""You are a senior career advisor specializing in tech industry career planning.

        A candidate is considering the following job offer. Generate a REALISTIC, JOB-SPECIFIC 5-year career
        trajectory showing what would happen if they accepted this role.

        Candidate Profile:
        - Name: {candidate_name}
        - Current Title: {current_title}
        - Seniority: {seniority}
        - Years of Experience: {years_exp}
        - Skills: {skills}

        Job Offer:
        - Title: {job_title}
        - Company: {company}
        - Description: {description[:1500]}
        - Requirements: {requirements}
        - Implicit Requirements: {implicit_requirements}

        Rules:
        1. Milestones must be specific to THIS company/role type (startup vs big tech vs agency matters).
        2. Include a decision_gate at the milestone where there is a real career fork (typically year 2-3).
        If no meaningful fork exists, set decision_gate to null.
        3. key_risks must be specific (e.g. "startup runway risk", "promotion timeline 3-4 yrs at big tech").
        4. trajectory_summary is a short label like "Y1: Tech Lead → Y3: EM → Y5: VP Eng".

        Respond ONLY with valid JSON matching this exact schema:
        {{
        "trajectory_summary": "Y1: Senior SWE → Y3: Tech Lead → Y5: Staff Engineer",
        "milestones": [
            {{
            "year": 1,
            "title": "Senior Software Engineer",
            "skills_needed": ["codebase onboarding", "team collaboration"],
            "decision_gate": null
            }},
            {{
            "year": 3,
            "title": "Tech Lead",
            "skills_needed": ["system design", "mentoring"],
            "decision_gate": {{
                "year": 3,
                "question": "Stay IC or move to Engineering Manager?",
                "option_A": "IC track → Staff Engineer in 2 more years, deep technical ownership",
                "option_B": "Management track → Engineering Manager, team of 6–8, people ops focus",
                "impact": "5-year salary gap ~20-30%; IC gains technical depth, EM gains organizational influence"
            }}
            }},
            {{
            "year": 5,
            "title": "Staff Engineer",
            "skills_needed": ["org-wide technical strategy", "cross-team influence"],
            "decision_gate": null
            }}
        ],
        "key_risks": [
            "Technical stack may limit transferability to other domains",
            "Promotion pace depends on headcount growth"
        ]
        }}
    """

    try:
        response = await _client.chat.completions.create(
            model=MOONSHOT_MODEL,
            messages=[
                {"role": "system", "content": "You are a career advisor. Output only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        data = json.loads(content)

        milestones: list[Milestone] = []
        for m in data.get("milestones", []):
            gate_data = m.get("decision_gate")
            gate = (
                DecisionGate(
                    year=gate_data.get("year", m.get("year", 0)),
                    question=gate_data.get("question", ""),
                    option_A=gate_data.get("option_A", ""),
                    option_B=gate_data.get("option_B", ""),
                    impact=gate_data.get("impact", ""),
                )
                if gate_data
                else None
            )
            milestones.append(Milestone(
                year=m.get("year", 0),
                title=m.get("title", ""),
                skills_needed=m.get("skills_needed", []),
                decision_gate=gate,
            ))

        return JobCareerPath(
            job_id=job_id,
            job_title=job_title,
            company=company,
            trajectory_summary=data.get("trajectory_summary", ""),
            milestones=milestones,
            key_risks=data.get("key_risks", []),
        )

    except Exception as e:
        logger.warning(f"CounterfactualCareerAgent failed for job_id={job_id}: {e}")
        return JobCareerPath(
            job_id=job_id,
            job_title=job_title,
            company=company,
            trajectory_summary="Trajectory unavailable.",
            milestones=[],
            key_risks=[],
        )


class CounterfactualCareerAgent(AgentBase):
    """
    Generates a job-specific counterfactual career path for every AnalyzedJob.
    All Moonshot calls run concurrently via asyncio.gather.

    Input:  ctx.candidate_profile, ctx.analyzed_jobs
    Output: ctx.job_career_paths (list[JobCareerPath], one per job)

    Phase 2 agent — runs in parallel with MatchScorerAgent + CareerPathPredictorAgent.
    Failure is non-fatal; the pipeline continues without per-job paths.

    为每个 AnalyzedJob 生成岗位专属的反事实职业路径。
    所有 Moonshot 调用通过 asyncio.gather 并发执行。
    """
    name = "counterfactual_career"
    timeout = 180.0

    async def run(self, ctx: AgentContext) -> AgentContext:
        if ctx.candidate_profile is None:
            raise ValueError("candidate_profile not available — ResumeParserAgent must run first")
        if not ctx.analyzed_jobs:
            raise ValueError("analyzed_jobs is empty — JobAnalyzerAgent must run first")

        cp = ctx.candidate_profile
        logger.info(
            f"[{ctx.request_id}] CounterfactualCareerAgent: predicting paths for "
            f"{len(ctx.analyzed_jobs)} jobs concurrently..."
        )

        tasks = [
            _predict_for_job(
                candidate_name=cp.name,
                current_title=cp.current_title,
                seniority=cp.seniority_self_reported or "mid",
                skills=cp.skills,
                years_exp=cp.years_of_experience or 0.0,
                job_id=aj.posting.job_id,
                job_title=aj.posting.title,
                company=aj.company,
                description=aj.posting.description or "",
                requirements=aj.posting.required_skills or [],
                implicit_requirements=aj.implicit_requirements,
            )
            for aj in ctx.analyzed_jobs
        ]

        results: list[JobCareerPath] = list(await asyncio.gather(*tasks))
        ctx.job_career_paths = results

        logger.info(
            f"[{ctx.request_id}] CounterfactualCareerAgent done — "
            f"{len(results)} paths generated"
        )
        return ctx
