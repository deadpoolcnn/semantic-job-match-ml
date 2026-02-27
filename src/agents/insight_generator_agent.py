"""
InsightGeneratorAgent: final synthesis stage.

For each matched job: async Moonshot call → why_match, skill_gaps, career_fit_commentary.
After per-job insights: one more Moonshot call → overall_summary + development_plan.
All per-job calls run concurrently via asyncio.gather.
InsightGeneratorAgent：最终综合阶段。
对于每个匹配的职位：异步调用 Moonshot → why_match、skill_gaps 和 career_fit_commentary。
在获取每个职位的洞察之后：再次调用 Moonshot → overall_summary + development_plan。
所有针对每个职位的调用均通过 asyncio.gather 并发运行。
"""

import asyncio
import json
import logging
from typing import Optional

from openai import AsyncOpenAI

from src.agents.base import AgentBase, AgentContext
from src.models.agent_schemas import (
    AnalyzedJob,
    CareerPrediction,
    ComparisonRow,
    InsightReport,
    JobCareerPath,
    JobComparisonMatrix,
    JobInsight,
)
from src.models.schemas import FiveDimScore
from src.core.config import get_moonshot_api_key, get_moonshot_model

logger = logging.getLogger(__name__)

_client = AsyncOpenAI(
    api_key=get_moonshot_api_key(),
    base_url="https://api.moonshot.ai/v1",
)
MOONSHOT_MODEL = get_moonshot_model()

_DIMS = ["semantic", "skill_graph", "seniority", "culture", "salary"]

# 辅助函数：将 FiveDimScore + AnalyzedJob 合并成一个扁平化的 dict，供 LLM 使用
# 把打分结果和职位信息合成一份字典
# mathc_score_agent + job_analyzer_agent 的输出合成一份字典，供 insight_generator_agent 使用
def _build_job_dict(score: FiveDimScore, aj: Optional[AnalyzedJob]) -> dict:
    """Merge FiveDimScore + AnalyzedJob into a flat dict for LLM prompts."""
    posting = aj.posting if aj else None
    return {
        "job_id": score.job_id,
        "title": posting.title if posting else "",
        "company": aj.company if aj else "",
        "description": posting.description if posting else "",
        "required_skills": posting.required_skills if posting else [],
        "implicit_requirements": aj.implicit_requirements if aj else [],
        "score": score.final_score,
        "five_dim_score": {
            dim: {
                "score": getattr(score, dim).score,
                "weight": getattr(score, dim).weight,
                "weighted_score": getattr(score, dim).weighted_score,
            }
            for dim in _DIMS
        },
    }

# 为单个职位生成“为什么匹配 / 差在哪 / 职业契合度一句话
async def _generate_job_insight(
    resume_text: str,
    job: dict,
    career_summary: str,
    path_map: dict[str, "JobCareerPath"],
) -> JobInsight:
    """Generate a single job's insight: why_match, skill_gaps, career_fit_commentary."""
    prompt = f"""You are a technical recruitment advisor. Analyze the match between this candidate and job.

        Candidate Resume:
        {resume_text[:3000]}

        Job:
        Title: {job['title']}
        Company: {job['company']}
        Required Skills: {job['required_skills']}
        Implicit Requirements: {job['implicit_requirements']}
        Description: {job['description'][:1500]}

        Match Score: {job['score']:.2f} / 1.0
        Candidate Career Context: {career_summary}

        Respond ONLY with valid JSON:
        {{
        "why_match": ["specific reason 1", "specific reason 2", "specific reason 3"],
        "skill_gaps": ["concrete gap 1", "concrete gap 2"],
        "career_fit_commentary": "One sentence on how this role fits their career trajectory."
        }}
    """

    try:
        response = await _client.chat.completions.create(
            model=MOONSHOT_MODEL,
            messages=[
                {"role": "system", "content": "You are a recruitment advisor. Output only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        data = json.loads(content)

        return JobInsight(
            job_id=job["job_id"],
            job_title=job["title"],
            company=job["company"],
            score=job["score"],
            five_dim_score=job["five_dim_score"],
            why_match=data.get("why_match", []),     # 具体到点的"你为什么适合这个岗位"
            skill_gaps=data.get("skill_gaps", []),     # 明确写出差在哪、缺哪些技能
            career_fit_commentary=data.get("career_fit_commentary", ""),  # 与 5 年职业目标的关系
            implicit_requirements=job["implicit_requirements"],
            counterfactual_path=path_map.get(job["job_id"]),
        )
    except Exception as e:
        logger.warning(f"Insight generation failed for job_id={job['job_id']}: {e}")
        return JobInsight(
            job_id=job["job_id"],
            job_title=job["title"],
            company=job["company"],
            score=job["score"],
            five_dim_score=job["five_dim_score"],
            why_match=[],
            skill_gaps=[],
            counterfactual_path=path_map.get(job["job_id"]),
        )

# ── Comparison Matrix ─────────────────────────────────────────────────────────

async def _generate_comparison_matrix(
    top_jobs: list[JobInsight],
    job_career_paths: list[JobCareerPath],
) -> Optional[JobComparisonMatrix]:
    """
    Single Moonshot call: produce a cross-job comparison matrix across 6 career dimensions.
    单次 Moonshot 调用：跨 6 个职业维度生成岗位对比矩阵。
    """
    if len(top_jobs) < 2:
        return None

    path_map = {p.job_id: p for p in job_career_paths}

    job_summaries = []
    for ji in top_jobs:
        path = path_map.get(ji.job_id)
        trajectory = path.trajectory_summary if path else "N/A"
        risks = ", ".join(path.key_risks[:2]) if path else "N/A"
        job_summaries.append(
            f"Job ID {ji.job_id} | {ji.job_title} @ {ji.company} | "
            f"score={ji.score:.2f} | trajectory={trajectory} | risks={risks}"
        )

    jobs_block = "\n".join(f"  - {s}" for s in job_summaries)
    job_ids = [ji.job_id for ji in top_jobs]

    prompt = (
        "You are a career strategist. Compare the following job options for a single candidate\n"
        "and fill in a comparison matrix across exactly these 6 dimensions:\n"
        "1. Career Ceiling (5-yr highest title achievable)\n"
        "2. Management vs IC Track (which path is more natural)\n"
        "3. Technical Depth (how deep they can go technically)\n"
        "4. Risk Level (job stability, startup risk, big-tech bureaucracy etc.)\n"
        "5. Salary Trajectory (estimated 5-yr earning potential)\n"
        "6. Culture & Pace (work culture, speed of iteration)\n\n"
        f"Jobs:\n{jobs_block}\n\n"
        f"Job IDs: {job_ids}\n\n"
        "Respond ONLY with valid JSON:\n"
        '{"rows": [{"dimension": "Career Ceiling", "values": {"<job_id_1>": "VP Eng", "<job_id_2>": "Principal Engineer"}}, ...],'
        ' "recommendation": "One sentence: which job to choose and why, with a trade-off callout."}'
    )

    try:
        response = await _client.chat.completions.create(
            model=MOONSHOT_MODEL,
            messages=[
                {"role": "system", "content": "You are a career strategist. Output only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        data = json.loads(content)

        rows = [
            ComparisonRow(dimension=r.get("dimension", ""), values=r.get("values", {}))
            for r in data.get("rows", [])
        ]
        return JobComparisonMatrix(
            rows=rows,
            recommendation=data.get("recommendation", ""),
        )
    except Exception as e:
        logger.warning(f"Comparison matrix generation failed: {e}")
        return None
async def _generate_overall_summary(
    candidate_name: str,
    top_jobs: list[JobInsight],
    career: Optional[CareerPrediction],
) -> tuple[str, str]:
    """Generate overall candidacy summary and development plan."""
    job_lines = "\n".join(
        f"  - {j.job_title} @ {j.company} (score: {j.score:.2f}): {j.career_fit_commentary}"
        for j in top_jobs[:3]
    )
    target = career.target_role_in_5yr if career else "N/A"
    gaps = career.skill_gaps_to_bridge if career else []
    milestones = (
        " → ".join(f"Year {m.year}: {m.title}" for m in career.milestones)
        if career else "N/A"
    )

    prompt = f"""Based on the candidate's job match results and career trajectory, write:
        1. A one-sentence overall summary of their candidacy strength
        2. A concise development plan (2–3 sentences) tailored to their 5-year goal

        Candidate: {candidate_name}
        Top Job Matches:
        {job_lines}

        5-Year Target: {target}
        Career Milestones: {milestones}
        Key Skill Gaps: {gaps}

        Respond ONLY with valid JSON:
        {{
        "overall_summary": "...",
        "development_plan": "..."
        }}
    """

    try:
        response = await _client.chat.completions.create(
            model=MOONSHOT_MODEL,
            messages=[
                {"role": "system", "content": "You are a career coach. Output only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        data = json.loads(content)
        return data.get("overall_summary", ""), data.get("development_plan", "")
    except Exception as e:
        logger.warning(f"Overall summary generation failed: {e}")
        return "Overall summary unavailable.", ""


class InsightGeneratorAgent(AgentBase):
    """
    Final synthesis agent. Runs after MatchScorerAgent and CareerPathPredictorAgent.

    Execution order:
      1. Build job dicts from scored_results + analyzed_jobs
      2. All per-job LLM calls concurrently (asyncio.gather)
      3. One final LLM call for overall_summary + development_plan
      最终综合代理。在 MatchScorerAgent 和 CareerPathPredictorAgent 之后运行。

    执行顺序：
    1. 根据 scores_results 和 analysed_jobs 构建作业字典
    2. 并发执行所有针对每个作业的 LLM 调用（asyncio.gather）
    3. 执行一次最终的 LLM 调用，用于生成 overall_summary 和 development_plan
    """
    name = "insight_generator"
    timeout = 180.0

    async def run(self, ctx: AgentContext) -> AgentContext:
        if not ctx.scored_results:
            raise ValueError("scored_results is empty — MatchScorerAgent must run first")

        # 候选人信息
        cp = ctx.candidate_profile
        # 职业预测信息
        career = ctx.career_prediction

        # Build lookup map from job_id → AnalyzedJob
        # 从 job_id 构建到 AnalyzedJob 的查找映射
        analyzed_map = {aj.posting.job_id: aj for aj in ctx.analyzed_jobs}

        # Merge score + analyzed metadata into flat dicts
        # 将分数和分析的元数据合并成扁平化的字典，对所有job信息进行操作
        job_dicts = [
            _build_job_dict(score, analyzed_map.get(score.job_id))
            for score in ctx.scored_results
        ]

        # 准备 career_summary / 简历文本 / 姓名
        career_summary = ""
        if career:
            career_summary = (
                f"Targeting {career.target_role_in_5yr!r} in 5 years. "
                f"Key skill gaps: {career.skill_gaps_to_bridge}."
            )

        resume_text = cp.resume_text if cp else ""
        candidate_name = cp.name if cp else ""

        logger.info(
            f"[{ctx.request_id}] InsightGeneratorAgent: "
            f"generating insights for {len(job_dicts)} jobs concurrently..."
        )

        # Phase A: per-job insights in parallel
        # 阶段 A：并行生成每个职位的洞察
        path_map: dict[str, JobCareerPath] = {
            p.job_id: p for p in ctx.job_career_paths
        }

        job_insights: list[JobInsight] = list(
            await asyncio.gather(
                *[_generate_job_insight(resume_text, jd, career_summary, path_map) for jd in job_dicts]
            )
        )

        # Phase B: overall summary + development plan (after insights are ready)
        # 第二阶段：总体总结 + 发展计划（在洞察分析完成后）
        overall_summary, dev_plan = await _generate_overall_summary(
            candidate_name, job_insights, career
        )

        # Phase C: job comparison matrix — single LLM call comparing all top-k jobs
        # 第三阶段：岗位对比矩阵（对 top-k 结果跨岗位对比，单次 LLM 调用）
        comparison_matrix = await _generate_comparison_matrix(job_insights, ctx.job_career_paths)

        ctx.insight_report = InsightReport(
            overall_summary=overall_summary,
            top_jobs=job_insights,
            development_plan=dev_plan,
            job_comparison_matrix=comparison_matrix,
        )

        logger.info(f"[{ctx.request_id}] InsightGeneratorAgent done")
        return ctx
