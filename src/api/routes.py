from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any
from src.services.job_loader import load_jobs
from src.models.matcher import get_job_matcher
from src.services.llm_explainer_service import explain_match

router = APIRouter(prefix="/api", tags=["match"])

# 输入模型（前端简历传过来）
class ResumeInput(BaseModel):
    resume_text: str = Field(..., description="简历文本内容")
    top_k: int = Field(default=10, ge=1, le=50, description="返回匹配结果数量")  # 可选参数，默认返回前10个匹配结果

# 输出模型（每个job的匹配结果）
class JobMatch(BaseModel):
    job_id: str
    job_title: str
    company: str
    score: float = Field(..., ge=0.0, le=1.0, description="匹配分数")
    why_match: List[str] = Field(default_factory=list)
    skill_gaps: List[str] = Field(default_factory=list)

class MatchResponse(BaseModel):
    matches: List[JobMatch]

@router.post("/match_resume", response_model=MatchResponse)
async def match_resume(resume_input: ResumeInput):
    """
    语义匹配接口：输入简历文本，输出 Top-K 岗位 + 解释
    """
    matcher = get_job_matcher() # 获取全局单例的 JobMatcher 实例
    # 语义top-K匹配，返回岗位信息和匹配分数
    # 返回的是字典类型数组
    matched_jobs = matcher.semantic_match(resume_input.resume_text, top_k=resume_input.top_k)
    # 1. 调用 LLM 生成匹配解释（可以并行化）
    explain_jobs = await explain_match(resume_input.resume_text, matched_jobs)
    # 2. 转为 API schema输出
    matches = [
        JobMatch(
            job_id=job.get("job_id", str(idx)),
            job_title=job.get("job_title", ""),
            company=job.get("company", ""),
            score=job.get("score", 0.0),
            why_match=job.get("why_match", []), 
            skill_gaps=job.get("skill_gaps", [])
        )
        for idx, job in enumerate(explain_jobs)
    ]
    return MatchResponse(matches=matches)