"""
维度3: 职级匹配 (20%)
规则引擎（正则 + 关键词）+ 可选 LLM 兜底
"""
import re
import logging
from typing import Optional
from src.models.schemas import CandidateProfile, JobPosting, DimensionScore
from src.core.match_config import SENIORITY_HIERARCHY, SENIORITY_MATCH_SCORES, YEARS_TO_LEVEL, get_seniority_keywords

logger = logging.getLogger(__name__)

class SeniorityMatcher:
    """
    职级匹配策略（优先级由高到低）：
    1. 候选人自报职级 → 直接映射
    2. 从 resume_text 提取年限 → 推算职级
    3. 从 resume_text 职称关键词 → 推算职级
    4. LLM 兜底（可选）
    """
    # 年限提取正则
    YEARS_PATTERN = re.compile(
        r"(\d+)\+?\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience|exp)",
        re.IGNORECASE,
    )

    def __init__(self, llm_client=None):
        """
        Args:
            llm_client: 可选 LLM 客户端（如 openai.OpenAI），用于兜底判断
        """
        self.llm_client = llm_client
        self.weight = 0.20
        self._seniority_keywords = get_seniority_keywords()  # 已按长度降序
    
    def _extract_level_from_keyword(self, text: str) -> Optional[int]:
        """从文本中提取职级关键词"""
        text_lower = text.lower()
        for keyword in self._seniority_keywords:
            # 使用词边界匹配，避免 "senior" 匹配到 "seniority"
            pattern = r"\b" + re.escape(keyword) + r"\b"
            if re.search(pattern, text_lower):
                return SENIORITY_HIERARCHY[keyword]
        return None
    
    def _extract_years_from_resume(self, resume_text: str) -> Optional[float]:
        """从简历文本中提取工作年限"""
        matches = self.YEARS_PATTERN.findall(resume_text)
        if not matches:
            return None
        # 取最大年限值
        return float(max(int(m) for m in matches))
    
    def _years_to_level(self, years: float) -> int:
        for (lo, hi), level in self.YEARS_TO_LEVEL.items():
            if lo <= years < hi:
                return level
        return 3  # default: Senior
    
    def _llm_extract_seniority(self, resume_text: str) -> Optional[int]:
        """使用 LLM 判断候选人职级（兜底策略）"""
        if not self.llm_client:
            return None
        try:
            prompt = f"""
Based on the resume below, determine the seniority level.
Reply with ONLY one of: intern(0), junior(1), mid(2), senior(3), staff(4), manager(5), director(6), executive(7)
Format: LEVEL_NAME(NUMBER)

Resume:
{resume_text[:2000]}
"""
            response = self.llm_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=20,
                temperature=0,
            )
            text = response.choices[0].message.content.strip()
            match = re.search(r"\((\d+)\)", text)
            if match:
                return int(match.group(1))
        except Exception as e:
            logger.warning(f"LLM seniority extraction failed: {e}")
        return None
    
    def _get_candidate_level(self, candidate: CandidateProfile) -> tuple[int, str]:
        """
        获取候选人职级，返回 (level, source)
        source: 'self_reported' | 'resume_keyword' | 'years_of_experience' | 'llm' | 'default'
        """
        # 1. 自报职级
        if candidate.seniority_self_reported:
            level = self._extract_level_from_keyword(candidate.seniority_self_reported)
            if level is not None:
                return level, "self_reported"

        # 2. 简历关键词
        level = self._extract_level_from_keyword(candidate.resume_text)
        if level is not None:
            return level, "resume_keyword"

        # 3. 工作年限推算
        if candidate.years_of_experience is not None:
            return self._years_to_level(candidate.years_of_experience), "years_of_experience"

        years = self._extract_years_from_resume(candidate.resume_text)
        if years is not None:
            return self._years_to_level(years), "years_extracted"

        # 4. LLM 兜底
        level = self._llm_extract_seniority(candidate.resume_text)
        if level is not None:
            return level, "llm"

        # 5. 默认 Mid Level
        return 2, "default"
    
    def _get_job_level(self, job: JobPosting) -> tuple[int, str]:
        """获取职位要求职级"""
        if job.seniority_level:
            level = self._extract_level_from_keyword(job.seniority_level)
            if level is not None:
                return level, "job_field"

        # 从职位标题提取
        level = self._extract_level_from_keyword(job.title)
        if level is not None:
            return level, "job_title"

        # 从 JD 正文提取
        level = self._extract_level_from_keyword(job.description)
        if level is not None:
            return level, "job_description"

        return 2, "default"
    
    def score(self, candidate: CandidateProfile, job: JobPosting) -> DimensionScore:
        candidate_level, candidate_source = self._get_candidate_level(candidate)
        job_level, job_source = self._get_job_level(job)

        gap = candidate_level - job_level  # 正数=候选人高于要求，负数=低于要求

        # 查表获取分数
        clamped_gap = max(-3, min(3, gap))
        raw_score = SENIORITY_MATCH_SCORES.get(clamped_gap, 0.1)

        return DimensionScore(
            score=raw_score,
            weight=self.weight,
            weighted_score=raw_score * self.weight,
            details={
                "candidate_level": candidate_level,
                "candidate_source": candidate_source,
                "job_level": job_level,
                "job_source": job_source,
                "gap": gap,
            },
        )



