"""
CareerPathPredictorAgent: single Moonshot call to generate a 5-year career trajectory.
Runs in parallel with MatchScorerAgent (both depend only on Phase 1 outputs).
CareerPathPredictorAgent：只需一次 Moonshot 调用即可生成 5 年职业发展轨迹。
与 MatchScorerAgent 并行运行（两者均仅依赖于第一阶段的输出）。
"""

import json
import logging

from openai import AsyncOpenAI

from src.agents.base import AgentBase, AgentContext
from src.models.agent_schemas import CareerPrediction, Milestone
from src.core.config import get_moonshot_api_key, get_moonshot_model

logger = logging.getLogger(__name__)

_client = AsyncOpenAI(
    api_key=get_moonshot_api_key(),
    base_url="https://api.moonshot.ai/v1",
)
MOONSHOT_MODEL = get_moonshot_model()


class CareerPathPredictorAgent(AgentBase):
    """
    Predicts the candidate's 5-year career trajectory based on their profile.
    Output feeds into InsightGeneratorAgent for career-fit commentary.
    根据候选人的个人资料预测其未来五年的职业发展轨迹。
    预测结果将输入到 InsightGeneratorAgent，用于生成职业匹配度分析报告。
    """
    name = "career_predictor"
    timeout = 60.0

    async def run(self, ctx: AgentContext) -> AgentContext:
        if ctx.candidate_profile is None:
            raise ValueError("candidate_profile not available — ResumeParserAgent must run first")

        cp = ctx.candidate_profile
        logger.info(f"[{ctx.request_id}] CareerPathPredictorAgent: predicting trajectory for {cp.name!r}...")

        prompt = f"""You are a senior career development advisor. Based on the candidate's profile below,
            predict their realistic 5-year career trajectory with concrete milestones.

            Candidate Profile:
            - Name: {cp.name}
            - Current Title: {cp.current_title}
            - Years of Experience: {cp.years_of_experience}
            - Seniority Level: {cp.seniority_self_reported}
            - Technical Skills: {cp.skills}
            - Soft Skills: {cp.soft_skills}
            - Career Objective: {cp.career_objective}

            Respond ONLY with valid JSON. The milestones array must have 3 entries (year 1, year 3, year 5):
            {{
            "current_level": "mid",
            "target_role_in_5yr": "Staff Engineer",
            "milestones": [
                {{"year": 1, "title": "Senior Engineer", "skills_needed": ["system design", "mentoring"]}},
                {{"year": 3, "title": "Tech Lead", "skills_needed": ["project ownership", "cross-team coordination"]}},
                {{"year": 5, "title": "Staff Engineer", "skills_needed": ["org-wide impact", "technical strategy"]}}
            ],
            "skill_gaps_to_bridge": ["Kubernetes", "distributed systems design"],
            "confidence_note": "High confidence — strong technical foundation with clear progression indicators."
            }}
        """

        response = await _client.chat.completions.create(
            model=MOONSHOT_MODEL,
            messages=[
                {"role": "system", "content": "You are a career development advisor. Output only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        data = json.loads(content)

        milestones = [
            Milestone(
                year=m.get("year", 0),
                title=m.get("title", ""),
                skills_needed=m.get("skills_needed", []),
            )
            for m in data.get("milestones", [])
        ]

        ctx.career_prediction = CareerPrediction(
            current_level=data.get("current_level", cp.seniority_self_reported or "mid"),
            target_role_in_5yr=data.get("target_role_in_5yr", ""),
            milestones=milestones,
            skill_gaps_to_bridge=data.get("skill_gaps_to_bridge", []),
            confidence_note=data.get("confidence_note", ""),
        )

        logger.info(
            f"[{ctx.request_id}] CareerPathPredictorAgent done — "
            f"target={ctx.career_prediction.target_role_in_5yr!r} "
            f"gaps={ctx.career_prediction.skill_gaps_to_bridge}"
        )
        return ctx
