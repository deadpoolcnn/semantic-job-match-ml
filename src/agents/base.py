"""
Multi-agent base classes and shared context.
多智能体基类与共享上下文。
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from src.models.agent_schemas import (
    ResumeProfile,
    AnalyzedJob,
    CareerPrediction,
    JobCareerPath,
    InsightReport,
)
from src.models.schemas import FiveDimScore

logger = logging.getLogger(__name__)


@dataclass
class AgentContext:
    """
    Shared mutable state passed through the agent pipeline.
    Each agent reads upstream fields and writes its own output field.

    共享的可变状态，在整个 Agent 管道中传递。
    每个 Agent 读取上游字段，并将自己的输出写入对应字段。
    """
    # ── Request params / 请求参数 ─────────────────────────────────────────────
    request_id: str
    file_bytes: bytes = field(default=b"")
    filename: str = ""
    top_k: int = 3

    # ── Agent outputs (written in DAG order) / Agent 输出（按 DAG 顺序写入）──
    candidate_profile: Optional[ResumeProfile] = None               # ResumeParserAgent            → 候选人画像
    analyzed_jobs: list[AnalyzedJob] = field(default_factory=list)       # JobAnalyzerAgent        → JD 深度分析结果
    scored_results: list[FiveDimScore] = field(default_factory=list)     # MatchScorerAgent        → 五维评分结果
    career_prediction: Optional[CareerPrediction] = None               # CareerPathPredictorAgent  → 岂位无关全局轨迹
    job_career_paths: list[JobCareerPath] = field(default_factory=list)  # CounterfactualCareerAgent → 每个岗位的反事实轨迹
    insight_report: Optional[InsightReport] = None                     # InsightGeneratorAgent     → 最终洞察报告

    # ── Observability / 可观测性 ──────────────────────────────────────────────
    errors: dict[str, str] = field(default_factory=dict)        # agent_name → error message / Agent 名 → 错误信息
    timings: dict[str, float] = field(default_factory=dict)     # agent_name → elapsed seconds / Agent 名 → 耗时（秒）


class AgentBase(ABC):
    """
    Base class for all agents.
    Subclasses implement `run(ctx)`. The `__call__` wrapper handles:
    - Per-agent wall-clock timing recorded into ctx.timings
    - Per-agent timeout enforcement
    - Exception capture into ctx.errors (non-fatal — pipeline continues)

    所有 Agent 的基类。
    子类实现 `run(ctx)` 方法。`__call__` 包装器统一处理：
    - 记录每个 Agent 的实际耗时到 ctx.timings
    - 强制每个 Agent 的超时限制
    - 捕获异常写入 ctx.errors（非致命，管道继续运行）
    """
    name: str = "base"
    timeout: float = 60.0

    async def __call__(self, ctx: AgentContext) -> AgentContext:
        t0 = time.monotonic()
        try:
            result = await asyncio.wait_for(self.run(ctx), timeout=self.timeout)
            ctx.timings[self.name] = round(time.monotonic() - t0, 3)
            logger.info(f"[{ctx.request_id}] {self.name} finished in {ctx.timings[self.name]}s")
            return result
        except asyncio.TimeoutError:
            ctx.timings[self.name] = round(time.monotonic() - t0, 3)
            ctx.errors[self.name] = f"Timed out after {self.timeout}s"
            logger.error(f"[{ctx.request_id}] {self.name} timed out after {self.timeout}s")
            return ctx
        except Exception as e:
            ctx.timings[self.name] = round(time.monotonic() - t0, 3)
            ctx.errors[self.name] = f"{type(e).__name__}: {e}"
            logger.error(f"[{ctx.request_id}] {self.name} failed: {e}", exc_info=True)
            return ctx

    @abstractmethod
    async def run(self, ctx: AgentContext) -> AgentContext:
        """
        Core agent logic. Read from ctx, write results back to ctx, return ctx.
        核心 Agent 逻辑。从 ctx 读取上游数据，将结果写回 ctx 并返回。
        """
        ...  # ← 相当于 pass，告诉 Python "子类必须实现这个方法"

