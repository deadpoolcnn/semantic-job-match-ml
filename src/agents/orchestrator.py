"""
OrchestratorAgent: 3-phase DAG execution.

Phase 1 (parallel): ResumeParserAgent  ||  JobAnalyzerAgent
Phase 2 (parallel): MatchScorerAgent   ||  CareerPathPredictorAgent
Phase 3 (serial):   InsightGeneratorAgent

Error handling:
  - Each agent captures its own exceptions into ctx.errors (non-fatal)
  - ResumeParserAgent failure aborts Phase 2+3 (nothing to score)
  - MatchScorerAgent failure aborts Phase 3 (nothing to explain)
  - JobAnalyzerAgent failure: fallback to unenriched JobPostings
  - CareerPathPredictorAgent failure: insight proceeds without career context

OrchestratorAgent：三阶段 DAG 执行。

阶段 1（并行）：ResumeParserAgent || JobAnalyzerAgent
阶段 2（并行）：MatchScorerAgent || CareerPathPredictorAgent
阶段 3（串行）：InsightGeneratorAgent

错误处理：
- 每个代理将自身的异常捕获到 ctx.errors 中（非致命异常）
- ResumeParserAgent 失败：中止阶段 2 和阶段 3（因为没有需要评分的内容）
- MatchScorerAgent 失败：中止阶段 3（因为没有需要解释的内容）
- JobAnalyzerAgent 失败：回退到未增强的 JobPostings
- CareerPathPredictorAgent 失败：在没有职业背景信息的情况下继续进行洞察分析
"""

import asyncio
import logging

from src.agents.base import AgentContext
from src.agents.resume_parser_agent import ResumeParserAgent
from src.agents.job_analyzer_agent import JobAnalyzerAgent
from src.agents.match_scorer_agent import MatchScorerAgent
from src.agents.career_path_predictor_agent import CareerPathPredictorAgent
from src.agents.insight_generator_agent import InsightGeneratorAgent
from src.models.agent_schemas import AnalyzedJob
from src.services.job_loader import load_jobs
from src.services.job_adapter import jobs_to_postings

logger = logging.getLogger(__name__)


class OrchestratorAgent:
    """Coordinates all specialist agents in a 3-phase DAG."""

    def __init__(self) -> None:
        self.parser    = ResumeParserAgent() # 解析简历
        self.analyzer  = JobAnalyzerAgent() # 分析JD
        self.scorer    = MatchScorerAgent() # 对JD进行五维评分
        self.predictor = CareerPathPredictorAgent() # 预测职业发展路径
        self.insight   = InsightGeneratorAgent() # 生成 per-job insight + overall summary

    async def run(self, ctx: AgentContext) -> AgentContext:
        # ── Phase 1: Resume parse + JD analysis (parallel) ───────────────────
        logger.info(f"[{ctx.request_id}] Orchestrator Phase 1 — parse + analyze (parallel)")
        await asyncio.gather(
            self.parser(ctx),
            self.analyzer(ctx),
        )

        # Resume parsing is a hard dependency — abort if it failed
        # 简历是硬依赖，解析失败整个 pipeline 直接中止。
        if "resume_parser" in ctx.errors:
            logger.error(
                f"[{ctx.request_id}] ResumeParserAgent failed ({ctx.errors['resume_parser']}), aborting pipeline"
            )
            return ctx

        # JD analysis failure: fall back to unenriched postings so scoring can continue
        if "job_analyzer" in ctx.errors:
            logger.warning(
                f"[{ctx.request_id}] JobAnalyzerAgent failed ({ctx.errors['job_analyzer']}), "
                "falling back to unenriched job postings"
            )
            # 用原始 job_mock.json 加载职位，转成 JobPosting。
            raw_jobs = load_jobs()
            postings = jobs_to_postings(raw_jobs)
            # 构造“空壳” AnalyzedJob（没有隐含要求和文化信号），让后面的打分仍然能跑。
            ctx.analyzed_jobs = [
                AnalyzedJob(posting=p, company=raw_jobs[i].get("company", ""))
                for i, p in enumerate(postings)
            ]

        # ── Phase 2: Scoring + Career prediction (parallel) ──────────────────
        logger.info(f"[{ctx.request_id}] Orchestrator Phase 2 — score + predict (parallel)")
        await asyncio.gather(
            self.scorer(ctx),
            self.predictor(ctx),
        )

        # Scoring is a hard dependency for Phase 3
        # Scoring 是 Phase 3 的硬依赖（没有评分就没办法生成 job-level insights），直接中止。
        if "match_scorer" in ctx.errors:
            logger.error(
                f"[{ctx.request_id}] MatchScorerAgent failed ({ctx.errors['match_scorer']}), aborting pipeline"
            )
            return ctx

        # Insight 还能继续，只是 prompt 里少了 career context。
        if "career_predictor" in ctx.errors:
            logger.warning(
                f"[{ctx.request_id}] CareerPathPredictorAgent failed ({ctx.errors['career_predictor']}), "
                "insight will proceed without career context"
            )

        # ── Phase 3: Insight synthesis (serial) ──────────────────────────────
        logger.info(f"[{ctx.request_id}] Orchestrator Phase 3 — generate insights")
        await self.insight(ctx)

        error_summary = ctx.errors or "none"
        logger.info(f"[{ctx.request_id}] Orchestrator complete. Errors: {error_summary}")
        return ctx
