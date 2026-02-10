from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any

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
    # TODO: 这里后面接入你的 models/matcher.py
    # 目前先 mock 数据（模拟你的 FAISS + LLM 结果）
    mock_matches = [
        JobMatch(
            job_id="1",
            job_title="Full-stack Web3 Engineer",
            company="CryptoXYZ",
            score=0.85,
            why_match=[
                "你的 Next.js 项目与岗位要求的 React + Next.js 完全匹配",
                "Web3 技能经验高度相关"
            ],
            skill_gaps=["Solidity 智能合约经验"]
        ),
        JobMatch(
            job_id="2",
            job_title="Senior ML Engineer",
            company="AI Labs",
            score=0.72,
            why_match=[
                "你的 Next.js 项目与岗位要求的 React + Next.js 完全匹配",
                "Web3 技能经验高度相关"
            ],
            skill_gaps=["Solidity 智能合约经验"]
        ),
        JobMatch(
            job_id="2",
            job_title="Senior ML Engineer",
            company="AI Labs",
            score=0.72,
            why_match=["ML 项目经验匹配"],
            skill_gaps=["深度学习框架"]
        )
    ]
    return MatchResponse(matches=mock_matches)