"""
五维度评分协调器
统一入口：输入候选人 + 职位列表 → 输出排序评分结果
"""

import logging
from typing import Optional

from src.models.schemas import CandidateProfile, JobPosting, FiveDimScore
from src.dimensions.semantic_matcher import SemanticMatcher
from src.dimensions.skill_graph_matcher import SkillGraphMatcher
from src.dimensions.seniority_matcher import SeniorityMatcher
from src.dimensions.culture_matcher import CultureMatcher
from src.dimensions.salary_matcher import SalaryMatcher

logger = logging.getLogger(__name__)

class FiveDimScorer:
    """
    五维度评分系统主入口

    评分维度与权重:
    ┌─────────────────┬────────┬─────────────────────────────┐
    │ 维度             │ 权重   │ 方法                         │
    ├─────────────────┼────────┼─────────────────────────────┤
    │ 语义匹配         │ 30%    │ MPNet + cosine similarity   │
    │ 技能图谱匹配     │ 25%    │ NetworkX Graph + hop search │
    │ 职级匹配         │ 20%    │ 规则引擎 + 可选 LLM          │
    │ 文化/价值观匹配  │ 15%    │ MiniLM + 文化维度向量        │
    │ 薪资匹配         │ 10%    │ 区间重叠规则引擎             │
    └─────────────────┴────────┴─────────────────────────────┘
    """

    def __init__(self, llm_client=None):
        logger.info("Initializing FiveDimScorer...")
        self.semantic  = SemanticMatcher()
        self.skill     = SkillGraphMatcher()
        self.seniority = SeniorityMatcher(llm_client=llm_client)
        self.culture   = CultureMatcher()
        self.salary    = SalaryMatcher()
        logger.info("FiveDimScorer ready.")
    
    def score_one(self, candidate: CandidateProfile, job: JobPosting) -> FiveDimScore:
        """对单个职位评分"""
        result = FiveDimScore(
            job_id      = job.job_id,
            semantic    = self.semantic.score(candidate, job),
            skill_graph = self.skill.score(candidate, job),
            seniority   = self.seniority.score(candidate, job),
            culture     = self.culture.score(candidate, job),
            salary      = self.salary.score(candidate, job),
        )
        result.compute_final()
        return result

    def score_batch(
        self,
        candidate: CandidateProfile,
        jobs: list[JobPosting],
        top_k: Optional[int] = None,
    ) -> list[FiveDimScore]:
        """
        Batch scoring (sequential).
        ThreadPoolExecutor causes PyTorch deadlocks when multiple threads
        call SentenceTransformer.encode() concurrently — run sequentially instead.
        Returns: list sorted by final_score descending.
        批量评分（顺序执行）。
        当多个线程并发调用 `SentenceTransformer.encode()` 时，`ThreadPoolExecutor` 会导致 PyTorch 死锁。
        请改为顺序执行。
        返回值：按 `final_score` 降序排列的列表。
        """
        results: list[FiveDimScore] = []
        for job in jobs:
            try:
                results.append(self.score_one(candidate, job))
            except Exception as e:
                logger.error(f"Scoring failed for job {job.job_id}: {e}")

        results.sort(key=lambda r: r.final_score, reverse=True)
        return results[:top_k] if top_k else results
    
    def explain(self, score: FiveDimScore) -> str:
        """生成人类可读的评分解释"""
        lines = [
            f"╔══ Job: {score.job_id} ══ Final Score: {score.final_score:.1%} ══",
            f"║  语义匹配    [{score.semantic.weight:.0%}]: {score.semantic.score:.1%}",
            f"║  技能图谱    [{score.skill_graph.weight:.0%}]: {score.skill_graph.score:.1%}",
            f"║  职级匹配    [{score.seniority.weight:.0%}]: {score.seniority.score:.1%}  "
            f"(candidate L{score.seniority.details.get('candidate_level','?')} "
            f"vs job L{score.seniority.details.get('job_level','?')})",
            f"║  文化匹配    [{score.culture.weight:.0%}]: {score.culture.score:.1%}",
            f"║  薪资匹配    [{score.salary.weight:.0%}]: {score.salary.score:.1%}",
            f"╚{'═' * 45}",
        ]
        return "\n".join(lines)
