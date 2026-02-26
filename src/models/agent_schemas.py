"""
Extended schemas for the multi-agent pipeline.
Separate from schemas.py to avoid circular imports.
"""

from dataclasses import dataclass, field
from typing import Optional

from src.models.schemas import CandidateProfile, JobPosting, SalaryRange


# ── Candidate ─────────────────────────────────────────────────────────────────

@dataclass
class ResumeProfile:
    """
    Extended candidate profile produced by ResumeParserAgent.
    Mirrors all CandidateProfile fields plus richer LLM-extracted data.
    """
    # Core fields (used by FiveDimScorer via to_candidate_profile())
    resume_text: str
    skills: list[str] = field(default_factory=list)
    seniority_self_reported: Optional[str] = None
    expected_salary: Optional[SalaryRange] = None
    culture_keywords: list[str] = field(default_factory=list)
    years_of_experience: Optional[float] = None

    # Extended fields
    name: str = ""
    email: str = ""
    current_title: str = ""
    education: list[dict] = field(default_factory=list) # e.g. [{"school": "MIT", "degree": "B.S.", "major": "CS", "year": 2020}]
    soft_skills: list[str] = field(default_factory=list) # e.g. ["communication", "leadership", "problem solving"]
    career_objective: str = ""          # Candidate's stated career goal extracted by LLM

    def to_candidate_profile(self) -> CandidateProfile:
        """
        Convert to the CandidateProfile used by FiveDimScorer.
        转换为 FiveDimScorer 使用的 CandidateProfile，包含所有扩展字段。
        """
        return CandidateProfile(
            resume_text=self.resume_text,
            skills=self.skills,
            seniority_self_reported=self.seniority_self_reported,
            expected_salary=self.expected_salary,
            culture_keywords=self.culture_keywords,
            years_of_experience=self.years_of_experience,
            education=self.education,
            soft_skills=self.soft_skills,
            career_objective=self.career_objective,
        )


# ── Job ───────────────────────────────────────────────────────────────────────

@dataclass
class AnalyzedJob:
    """
    JobPosting enriched with LLM-inferred analysis produced by JobAnalyzerAgent.
    Wraps a JobPosting so MatchScorerAgent can extract the posting directly.
    职位发布信息已通过 JobAnalyzerAgent 生成的 LLM 推断分析进行增强。
    对职位发布信息进行封装，以便 MatchScorerAgent 可以直接提取职位信息。
    """
    posting: JobPosting
    company: str = ""                           # from raw job dict (not in JobPosting)
    implicit_requirements: list[str] = field(default_factory=list)
    culture_fit_signals: list[str] = field(default_factory=list)


# ── Career Prediction ─────────────────────────────────────────────────────────

@dataclass
class Milestone:
    year: int
    title: str
    skills_needed: list[str] = field(default_factory=list)


@dataclass
class CareerPrediction:
    current_level: str
    target_role_in_5yr: str
    milestones: list[Milestone] = field(default_factory=list)
    skill_gaps_to_bridge: list[str] = field(default_factory=list)
    confidence_note: str = ""


# ── Insight Report ────────────────────────────────────────────────────────────

@dataclass
class JobInsight:
    job_id: str
    job_title: str
    company: str
    score: float
    five_dim_score: dict                        # dim → {score, weight, weighted_score}
    why_match: list[str]
    skill_gaps: list[str]
    career_fit_commentary: str = ""
    implicit_requirements: list[str] = field(default_factory=list)


@dataclass
class InsightReport:
    overall_summary: str
    top_jobs: list[JobInsight]
    development_plan: str = ""
