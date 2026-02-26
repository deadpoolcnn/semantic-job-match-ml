"""
JobAnalyzerAgent: LLM-powered JD analysis with mtime-based process-level cache.

Cache invalidation strategy:
  - Cache key: mtime of data/jobs/job_mock.json
  - On hit: return cached AnalyzedJob list immediately (0 LLM calls)
  - On miss/invalidation: re-analyze all JDs concurrently via asyncio.gather

用 LLM 深度“解读”所有职位描述（JD），自动抽取每个岗位的隐含要求和文化信号，
并按 job 文件修改时间做缓存，避免重复分析
缓存失效策略：
- 缓存键：data/jobs/job_mock.json 的修改时间

- 命中时：立即返回缓存的 AnalyzedJob 列表（0 次 LLM 调用）

- 未命中/失效时：通过 asyncio.gather 并发重新分析所有 JD。
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

from openai import AsyncOpenAI

from src.agents.base import AgentBase, AgentContext
from src.models.agent_schemas import AnalyzedJob
from src.models.schemas import JobPosting
from src.services.job_loader import load_jobs
from src.services.job_adapter import jobs_to_postings
from src.core.config import get_moonshot_api_key, get_moonshot_model

logger = logging.getLogger(__name__)

# Path to job data file — used for mtime-based cache invalidation
_JOB_FILE = Path(__file__).resolve().parents[2] / "data" / "jobs" / "job_mock.json"

_client = AsyncOpenAI(
    api_key=get_moonshot_api_key(),
    base_url="https://api.moonshot.ai/v1",
)
MOONSHOT_MODEL = get_moonshot_model()

# ── Process-level JD cache ────────────────────────────────────────────────────
# Structure: {"mtime": float | None, "results": dict[job_id, AnalyzedJob]}
_cache: dict = {"mtime": None, "results": {}}


def _get_mtime() -> Optional[float]:
    try:
        return _JOB_FILE.stat().st_mtime
    except FileNotFoundError:
        return None


async def _analyze_single_job(posting: JobPosting, company: str = "") -> AnalyzedJob:
    """Async Moonshot call to extract implicit requirements and culture signals for one JD."""
    prompt = f"""Analyze the following job description and extract two things:

        1. Implicit requirements — unstated but implied expectations not listed in the official requirements
        (e.g. "startup experience", "comfortable with ambiguity", "self-starter")
        2. Culture fit signals — words or phrases that reveal company culture
        (e.g. "fast-paced", "collaborative", "data-driven", "remote-first")

        Job Title: {posting.title}
        Description: {posting.description}
        Required Skills: {posting.required_skills}
        Preferred Skills: {posting.preferred_skills}

        Respond ONLY with valid JSON:
        {{
        "implicit_requirements": ["requirement 1", "requirement 2"],
        "culture_fit_signals": ["signal 1", "signal 2", "signal 3"]
        }}
    """

    try:
        response = await _client.chat.completions.create(
            model=MOONSHOT_MODEL,
            messages=[
                {"role": "system", "content": "You are a job analysis expert. Output only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        data = json.loads(content)
        return AnalyzedJob(
            posting=posting,
            company=company,
            implicit_requirements=data.get("implicit_requirements", []),
            culture_fit_signals=data.get("culture_fit_signals", []),
        )
    except Exception as e:
        logger.warning(f"JD analysis failed for job_id={posting.job_id}: {e}")
        return AnalyzedJob(posting=posting, company=company)


async def prewarm() -> None:
    """
    Pre-warm the JD cache at server startup.
    Called from main.py startup event so the first real request hits the cache.
    在服务启动时就把所有 JD 跑一遍 _analyze_single_job，把结果放进 _cache["results"]。
    """
    logger.info("[JobAnalyzerAgent] Pre-warming JD cache...")
    current_mtime = _get_mtime()
    if current_mtime is None:
        logger.warning("[JobAnalyzerAgent] Job file not found, skipping pre-warm")
        return
    if _cache["mtime"] == current_mtime:
        logger.info("[JobAnalyzerAgent] JD cache already warm")
        return

    raw_jobs = load_jobs()
    postings = jobs_to_postings(raw_jobs)
    companies = [j.get("company", "") for j in raw_jobs]

    analyzed = await asyncio.gather(
        *[_analyze_single_job(p, c) for p, c in zip(postings, companies)]
    )
    _cache["mtime"] = current_mtime
    _cache["results"] = {a.posting.job_id: a for a in analyzed}
    logger.info(f"[JobAnalyzerAgent] JD cache warmed: {len(_cache['results'])} jobs analyzed")


class JobAnalyzerAgent(AgentBase):
    """
    Analyzes all job postings with LLM to extract implicit requirements and
    culture signals. Results are cached at process level, keyed by file mtime.
    使用 LLM 分析所有职位发布信息，提取隐含要求和文化信号。结果以文件修改时间为键，缓存到进程级别。
    """
    name = "job_analyzer"
    timeout = 180.0     # up to N jobs × ~3s each, bounded by asyncio.gather concurrency

    async def run(self, ctx: AgentContext) -> AgentContext:
        current_mtime = _get_mtime()

        if _cache["mtime"] is not None and _cache["mtime"] == current_mtime and _cache["results"]:
            logger.info(
                f"[{ctx.request_id}] JD cache hit — {len(_cache['results'])} jobs, skipping LLM analysis"
            )
            ctx.analyzed_jobs = list(_cache["results"].values())
            return ctx

        logger.info(f"[{ctx.request_id}] JD cache miss/invalidated — re-analyzing all JDs...")
        raw_jobs = load_jobs()
        postings = jobs_to_postings(raw_jobs)
        companies = [j.get("company", "") for j in raw_jobs]

        analyzed = await asyncio.gather(
            *[_analyze_single_job(p, c) for p, c in zip(postings, companies)]
        )
        analyzed_list = list(analyzed)

        _cache["mtime"] = current_mtime
        _cache["results"] = {a.posting.job_id: a for a in analyzed_list}

        ctx.analyzed_jobs = analyzed_list
        logger.info(f"[{ctx.request_id}] JD analysis complete: {len(analyzed_list)} jobs cached")
        return ctx
