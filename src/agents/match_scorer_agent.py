"""
MatchScorerAgent: runs FiveDimScorer.score_batch in a ThreadPoolExecutor.
Reuses the process-level FiveDimScorer singleton from routes.py.
MatchScorerAgent：在线程池执行器中运行 FiveDimScorer.score_batch。
重用 routes.py 中的进程级 FiveDimScorer 单例。
"""

import asyncio
import logging
from functools import partial

from src.agents.base import AgentBase, AgentContext
from src.api.routes import get_five_dim_scorer

logger = logging.getLogger(__name__)


class MatchScorerAgent(AgentBase):
    """
    Extracts JobPosting objects from ctx.analyzed_jobs and runs 5-dimension
    batch scoring. PyTorch encode() runs in executor to avoid event-loop blocking.
    从 ctx.analyzed_jobs 中提取 JobPosting 对象并运行 5 维批量评分。
    PyTorch encode() 在执行器中运行，以避免事件循环阻塞。
    """
    name = "match_scorer"
    timeout = 180.0

    async def run(self, ctx: AgentContext) -> AgentContext:
        # 前置条件检查：确保 resume_parser 和 job_analyzer 已成功运行
        if ctx.candidate_profile is None:
            raise ValueError("candidate_profile not available — ResumeParserAgent must run first")
        if not ctx.analyzed_jobs:
            raise ValueError("analyzed_jobs is empty — JobAnalyzerAgent must run first")

        scorer = get_five_dim_scorer() # 从 routes.py 获取 FiveDimScorer 单例
        candidate = ctx.candidate_profile.to_candidate_profile() # 转换为 MatchScorer 输入格式
        postings = [aj.posting for aj in ctx.analyzed_jobs] # 从 AnalyzedJob 中提取原始 JobPosting 列表

        logger.info(f"[{ctx.request_id}] MatchScorerAgent: scoring {len(postings)} jobs (5-dim)...")
        # 批量评分（顺序执行）。当多个线程并发调用 `SentenceTransformer.encode()` 时，`ThreadPoolExecutor` 会导致 PyTorch 死锁。请改为顺序执行。
        # Returns: list sorted by final_score descending top_k. 
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None, partial(scorer.score_batch, candidate, postings, ctx.top_k)
        )
        ctx.scored_results = results

        # 前 3 个推荐的维度拆解
        for i, r in enumerate(results[:3], 1):
            logger.info(
                f"[{ctx.request_id}]   #{i} {r.job_id} | final={r.final_score:.3f} | "
                f"sem={r.semantic.score:.2f} skill={r.skill_graph.score:.2f} "
                f"sen={r.seniority.score:.2f} cul={r.culture.score:.2f} sal={r.salary.score:.2f}"
            )
        return ctx
