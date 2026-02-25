"""
五维度评分体系数据模型
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

class SeniorityLevel(str, Enum):
    INTERN = "intern"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    STAFF = "staff"
    MANAGER = "manager"
    DIRECTOR = "director"
    EXECUTIVE = "executive"

@dataclass
class SalaryRange:
    min_salary: Optional[float] = None
    max_salary: Optional[float] = None
    currency: str = "USD"
    period: str = "annual"  # annual / monthly

@dataclass
class CandidateProfile:
    """候选人画像"""
    resume_text: str
    skills: list[str] = field(default_factory=list)
    seniority_self_reported: Optional[str] = None          # 简历中自述职级
    expected_salary: Optional[SalaryRange] = None
    culture_keywords: list[str] = field(default_factory=list)  # 文化偏好关键词
    years_of_experience: Optional[float] = None


@dataclass
class JobPosting:
    """职位信息"""
    job_id: str
    title: str
    description: str
    required_skills: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list)
    seniority_level: Optional[str] = None
    salary_range: Optional[SalaryRange] = None
    culture_keywords: list[str] = field(default_factory=list)
    company_values: list[str] = field(default_factory=list)

@dataclass
class DimensionScore:
    """单维度评分结果"""
    score: float                        # 0.0 ~ 1.0
    weight: float                       # 权重
    weighted_score: float               # = score * weight
    details: dict = field(default_factory=dict)  # 调试细节
    confidence: float = 1.0            # 评分置信度

@dataclass
class FiveDimScore:
    """五维度综合评分"""
    # 各维度分数
    semantic: DimensionScore
    skill_graph: DimensionScore
    seniority: DimensionScore
    culture: DimensionScore
    salary: DimensionScore

    # 综合得分
    final_score: float = 0.0
    job_id: str = ""

    def compute_final(self) -> float:
        dims = [self.semantic, self.skill_graph,
                self.seniority, self.culture, self.salary]
        self.final_score = sum(d.weighted_score for d in dims)
        return self.final_score

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "final_score": round(self.final_score, 4),
            "dimensions": {
                "semantic":    {"score": self.semantic.score,    "weight": self.semantic.weight,    "details": self.semantic.details},
                "skill_graph": {"score": self.skill_graph.score, "weight": self.skill_graph.weight, "details": self.skill_graph.details},
                "seniority":   {"score": self.seniority.score,   "weight": self.seniority.weight,   "details": self.seniority.details},
                "culture":     {"score": self.culture.score,     "weight": self.culture.weight,     "details": self.culture.details},
                "salary":      {"score": self.salary.score,      "weight": self.salary.weight,      "details": self.salary.details},
            }
        }