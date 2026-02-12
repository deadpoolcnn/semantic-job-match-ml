from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel, Field
from typing import List, Dict, Any
import logging
import json
from datetime import datetime

from src.services.job_loader import load_jobs
from src.models.matcher import get_job_matcher
from src.services.llm_explainer_service import explain_match_loop
from src.services.resume_parser import parse_resume_file

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
    semantic_score: float | None = None
    skill_overlap: float | None = None
    rule_bonus: float | None = None
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
    explain_jobs = await explain_match_loop(resume_input.resume_text, matched_jobs)
    # 2. 转为 API schema输出
    matches = [
        JobMatch(
            job_id=job.get("job_id", str(idx)),
            job_title=job.get("job_title", ""),
            company=job.get("company", ""),
            score=job.get("score", 0.0),
            semantic_score=job.get("semantic_score"),
            skill_overlap=job.get("skill_overlap"),
            rule_bonus=job.get("rule_bonus"),
            why_match=job.get("why_match", []), 
            skill_gaps=job.get("skill_gaps", [])
        )
        for idx, job in enumerate(explain_jobs)
    ]
    return MatchResponse(matches=matches)

@router.post("match_resume_file", response_model=MatchResponse)
async def match_resume_file(
    file: UploadFile = File(..., description="PDF or DOCX resume file"),
    top_k: int = 3
):
    """
    文件上传接口：输入简历文件，输出 Top-K 岗位 + 解释
    """
    request_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    logger.info(f"[{request_id}] 📥 Received file upload request")
    logger.info(f"[{request_id}] File: {file.filename}, Content-Type: {file.content_type}, top_k: {top_k}")
    
    # 1. 类型校验
    if file.content_type not in [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ]:
        logger.warning(f"[{request_id}] ❌ Unsupported file type: {file.content_type}")
        raise HTTPException(status_code=400, detail="Unsupported file type. Please upload a PDF or DOCX file.")
    
    # 2. 读取文件内容 传给解析服务
    file_bytes = await file.read()
    file_size_kb = len(file_bytes) / 1024
    logger.info(f"[{request_id}] 📄 File size: {file_size_kb:.2f} KB")
    
    try:
        logger.info(f"[{request_id}] 🔍 Parsing resume file...")
        parsed = parse_resume_file(file_bytes, file.filename)
        
        # 记录解析结果详情
        logger.info(f"[{request_id}] ✅ Resume parsed successfully")
        logger.info(f"[{request_id}] Extracted text length: {len(parsed.get('text', ''))} characters")
        logger.info(f"[{request_id}] Extracted skills: {parsed.get('skills', [])}")
        logger.info(f"[{request_id}] Raw data keys: {list(parsed.get('raw', {}).keys())}")
        
        # 打印前200个字符的文本内容
        text_preview = parsed.get('text', '')[:200]
        logger.debug(f"[{request_id}] Text preview: {text_preview}...")
        
    except Exception as e:
        logger.error(f"[{request_id}] ❌ Error parsing resume file: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error parsing resume file: {e}")
    
    resume_text = parsed.get("text", "")
    if not resume_text:
        logger.warning(f"[{request_id}] ⚠️  No text extracted from resume")
        raise HTTPException(status_code=400, detail="Failed to extract text from resume file.")
    
    # 解析出来的技能,后面接进 hybrid score
    resume_skills = parsed.get("skills", [])
    logger.info(f"[{request_id}] 🎯 Resume skills for matching: {resume_skills}")
    logger.info(f"[{request_id}] 🎯 Resume skills for matching: {resume_skills}")
    resume_skills_set = set(s.lower() for s in resume_skills) if resume_skills else set()
    
    # 3. 调用之前的文本接口逻辑
    logger.info(f"[{request_id}] 🔎 Starting semantic matching...")
    matcher = get_job_matcher() # 获取全局单例的 JobMatcher 实例
    matched_jobs = matcher.semantic_match(resume_text, top_k=top_k, resume_skills=resume_skills_set)
    
    logger.info(f"[{request_id}] ✅ Found {len(matched_jobs)} matched jobs")
    for i, job in enumerate(matched_jobs[:3], 1):  # 只记录前3个
        logger.info(
            f"[{request_id}] Match #{i}: {job.get('job_title')} @ {job.get('company')} | "
            f"score={job.get('score', 0):.3f}, semantic={job.get('semantic_score', 0):.3f}, "
            f"skill_overlap={job.get('skill_overlap', 0):.3f}"
        )
    
    # 4. 调用 LLM 生成匹配解释（可以并行化）
    logger.info(f"[{request_id}] 🤖 Generating AI explanations...")
    explain_jobs = await explain_match_loop(resume_text, matched_jobs)
    logger.info(f"[{request_id}] ✅ AI explanations generated")
    
    # 5. 转为 API schema输出
    matches = [
        JobMatch(
            job_id=job.get("job_id", str(idx)),
            job_title=job.get("job_title", ""), 
            company=job.get("company", ""),
            score=job.get("score", 0.0),
            semantic_score=job.get("semantic_score"),
            skill_overlap=job.get("skill_overlap"),
            rule_bonus=job.get("rule_bonus"),
            why_match=job.get("why_match", []), 
            skill_gaps=job.get("skill_gaps", [])
        )
        for idx, job in enumerate(explain_jobs)
    ]
    
    logger.info(f"[{request_id}] ✅ Request completed successfully, returning {len(matches)} matches")
    logger.info(f"[{request_id}] {'='*60}")
    
    return MatchResponse(matches=matches)