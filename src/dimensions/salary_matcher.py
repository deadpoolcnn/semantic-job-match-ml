"""
维度5: 薪资匹配 (10%)
规则引擎：期望薪资 vs 职位薪资范围
"""

import re
from typing import Optional
from src.models.schemas import CandidateProfile, JobPosting, DimensionScore, SalaryRange
from src.core.match_config import CURRENCY_TO_USD, PERIOD_MULTIPLIER

SALARY_PATTERN = re.compile(
    r"""
    (?:USD|EUR|GBP|CNY|¥|\$|€|£)?   # 货币符号
    \s*
    (\d{1,3}(?:,\d{3})*(?:\.\d+)?)  # 数值
    \s*
    (k|K|thousand|万)?               # 千位单位
    \s*
    (?:USD|EUR|GBP|CNY|per\s+year|/yr|/year|annually)?
    """,
    re.VERBOSE | re.IGNORECASE,
)

RANGE_PATTERN = re.compile(
    r"(\$[\d,kK.]+)\s*[-–—~to]+\s*(\$[\d,kK.]+)",
    re.IGNORECASE,
)

class SalaryMatcher:
    """
    薪资匹配评分规则：
    - 完全在范围内: 1.0
    - 偏差 <10%: 0.85
    - 偏差 10-20%: 0.65
    - 偏差 20-40%: 0.40
    - 偏差 >40%: 0.15
    - 无薪资信息: 0.5（中性）
    """
    OVERLAP_SCORES = [
        (1.00, 1.0),   # 完全覆盖
        (0.80, 0.90),
        (0.60, 0.75),
        (0.40, 0.55),
        (0.20, 0.35),
        (0.00, 0.15),  # 无交集
    ]
    def __init__(self):
        self.weight = 0.10
    
    def _normalize_to_usd_annual(self, salary_range: SalaryRange) -> tuple[float, float]:
        """将薪资范围归一化为年薪 USD"""
        rate = CURRENCY_TO_USD.get(salary_range.currency.upper(), 1.0)
        multiplier = PERIOD_MULTIPLIER.get(salary_range.period.lower(), 1.0)

        lo = (salary_range.min_salary or 0) * rate * multiplier
        hi = (salary_range.max_salary or lo * 1.3) * rate * multiplier  # 无上限时估算
        return lo, hi
    
    def _extract_salary_from_text(self, text: str) -> Optional[SalaryRange]:
        """从文本中提取薪资区间"""
        # 尝试提取范围 "$80k - $120k"
        range_match = RANGE_PATTERN.search(text)
        if range_match:
            lo_str, hi_str = range_match.group(1), range_match.group(2)
            lo = self._parse_value(lo_str)
            hi = self._parse_value(hi_str)
            if lo and hi:
                return SalaryRange(min_salary=lo, max_salary=hi)

        # 提取单值
        matches = SALARY_PATTERN.findall(text)
        values = [self._parse_value(f"{m[0]}{m[1]}") for m in matches if m[0]]
        values = [v for v in values if v and 10000 < v < 10_000_000]
        if len(values) >= 2:
            return SalaryRange(min_salary=min(values), max_salary=max(values))
        if len(values) == 1:
            v = values[0]
            return SalaryRange(min_salary=v * 0.9, max_salary=v * 1.1)
        return None
    
    def _parse_value(self, s: str) -> Optional[float]:
        """解析薪资数值字符串"""
        s = s.replace("$", "").replace(",", "").replace("€", "").replace("£", "").strip()
        multiplier = 1.0
        if s.lower().endswith("k"):
            s = s[:-1]
            multiplier = 1000.0
        try:
            return float(s) * multiplier
        except ValueError:
            return None
        
    def _compute_overlap_score(
        self,
        candidate_lo: float, candidate_hi: float,
        job_lo: float, job_hi: float,
    ) -> float:
        """计算两个区间的重叠比例，映射为分数"""
        overlap_lo = max(candidate_lo, job_lo)
        overlap_hi = min(candidate_hi, job_hi)

        if overlap_hi <= overlap_lo:
            # 无重叠，计算偏差距离
            gap = max(candidate_lo - job_hi, job_lo - candidate_hi)
            mid_job = (job_lo + job_hi) / 2
            relative_gap = gap / mid_job if mid_job > 0 else 1.0
            return max(0.05, 0.15 - relative_gap * 0.1)

        # 取候选人区间长度作为基准
        candidate_span = candidate_hi - candidate_lo or 1.0
        overlap_ratio = (overlap_hi - overlap_lo) / candidate_span
        overlap_ratio = min(1.0, overlap_ratio)

        # 查表映射
        for threshold, s in self.OVERLAP_SCORES:
            if overlap_ratio >= threshold:
                return s
        return 0.15
    
    def score(self, candidate: CandidateProfile, job: JobPosting) -> DimensionScore:
        # 获取候选人期望薪资
        candidate_salary = candidate.expected_salary
        if candidate_salary is None:
            candidate_salary = self._extract_salary_from_text(candidate.resume_text)

        # 获取职位薪资范围
        job_salary = job.salary_range
        if job_salary is None:
            job_salary = self._extract_salary_from_text(job.description)

        # 无薪资信息时返回中性分
        if candidate_salary is None or job_salary is None:
            return DimensionScore(
                score=0.5,
                weight=self.weight,
                weighted_score=0.5 * self.weight,
                confidence=0.3,
                details={
                    "note": "insufficient salary data",
                    "candidate_salary_found": candidate_salary is not None,
                    "job_salary_found": job_salary is not None,
                },
            )

        c_lo, c_hi = self._normalize_to_usd_annual(candidate_salary)
        j_lo, j_hi = self._normalize_to_usd_annual(job_salary)

        overlap_score = self._compute_overlap_score(c_lo, c_hi, j_lo, j_hi)

        return DimensionScore(
            score=overlap_score,
            weight=self.weight,
            weighted_score=overlap_score * self.weight,
            confidence=0.9,
            details={
                "candidate_range_usd": [round(c_lo), round(c_hi)],
                "job_range_usd":       [round(j_lo), round(j_hi)],
                "overlap_score":       round(overlap_score, 3),
            },
        )