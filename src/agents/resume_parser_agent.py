"""
ResumeParserAgent：PDF/DOCX 文本提取 + Moonshot 结构化解析。

封装了 run_in_executor 中现有的同步 resume_parser 服务。
"""

import asyncio
import logging
from functools import partial

from src.agents.base import AgentBase, AgentContext
from src.models.agent_schemas import ResumeProfile
from src.models.schemas import SalaryRange
from src.services.resume_parser import parse_resume_file

logger = logging.getLogger(__name__)


class ResumeParserAgent(AgentBase):
    name = "resume_parser"
    timeout = 90.0          # PDF parse + Moonshot call can take ~30s

    async def run(self, ctx: AgentContext) -> AgentContext:
        logger.info(f"[{ctx.request_id}] ResumeParserAgent: parsing {ctx.filename!r}...")
        loop = asyncio.get_event_loop()

        # PDF/DOCX 解析 + LLM 调用都是同步的，放到 executor 里跑避免阻塞事件循环
        # 默认使用 ThreadPoolExecutor，因为 PDF 解析和 HTTP 请求都是 I/O 密集型的
        # parse_resume_file is sync (pdfplumber + sync OpenAI) — run in executor
        # PDF文件 → pdfplumber提取纯文本 → OpenAI LLM结构化解析 → parsed字典
        parsed = await loop.run_in_executor(
            None, partial(parse_resume_file, ctx.file_bytes, ctx.filename)
        )
        # 未进一步处理的原始LLM输出，不是完全结构化数据。
        raw = parsed.get("raw", {})

        # Build SalaryRange from LLM-extracted salary dict
        salary_info = raw.get("expected_salary")
        expected_salary = None
        if salary_info and isinstance(salary_info, dict):
            expected_salary = SalaryRange(
                min_salary=salary_info.get("min"),
                max_salary=salary_info.get("max"),
                currency=salary_info.get("currency", "USD"),
                period=salary_info.get("period", "annual"),
            )

        raw_skills = parsed.get("skills", [])
        skills_list = list(raw_skills) if raw_skills else []

        ctx.candidate_profile = ResumeProfile(
            resume_text=parsed.get("text", ""),
            skills=skills_list,
            seniority_self_reported=raw.get("seniority"),
            expected_salary=expected_salary,
            culture_keywords=raw.get("culture_keywords", []),
            years_of_experience=raw.get("experience_years"),
            name=raw.get("name", ""),
            email=raw.get("email", ""),
            current_title=raw.get("current_title", ""),
            education=raw.get("education", []),
            soft_skills=raw.get("soft_skills", []),
            career_objective=raw.get("summary", ""),
        )

        logger.info(
            f"[{ctx.request_id}] ResumeParserAgent done — "
            f"name={ctx.candidate_profile.name!r} "
            f"skills={ctx.candidate_profile.skills} "
            f"seniority={ctx.candidate_profile.seniority_self_reported}"
        )
        return ctx
