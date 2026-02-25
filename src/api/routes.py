from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel, Field
from typing import List, Dict, Any
import asyncio
import logging
import json
from datetime import datetime
from functools import partial

from src.services.job_loader import load_jobs
from src.models.matcher import get_job_matcher
from src.services.llm_explainer_service import explain_match_loop
from src.services.resume_parser import parse_resume_file
from src.services.build_candidate_profile import build_candidate_profile, five_dim_result_to_job_dict

# ── 新增：五维评分导入 ──────────────────────────────────────
from src.core.five_dim_scorer import FiveDimScorer
from src.models.schemas import CandidateProfile, JobPosting, SalaryRange
from src.services.job_adapter import jobs_to_postings


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["match"])

# ── 全局单例（避免重复加载模型）──────────────────────────────
_five_dim_scorer: FiveDimScorer | None = None

def get_five_dim_scorer() -> FiveDimScorer:
    global _five_dim_scorer
    if _five_dim_scorer is None:
        logger.info("Initializing FiveDimScorer singleton...")
        _five_dim_scorer = FiveDimScorer()
    return _five_dim_scorer

# 输入模型（前端简历传过来）
class ResumeInput(BaseModel):
    resume_text: str = Field(..., description="简历文本内容")
    top_k: int = Field(default=10, ge=1, le=50, description="返回匹配结果数量")  # 可选参数，默认返回前10个匹配结果

# 输出模型（每个job的匹配结果）扩展五维分数字段
class FiveDimScoreDetail(BaseModel):
    score: float
    weight: float
    weighted_score: float
    details: Dict[str, Any] = Field(default_factory=dict)

class JobMatch(BaseModel):
    job_id: str
    job_title: str
    company: str
    score: float = Field(..., ge=0.0, le=1.0, description="匹配分数")
    semantic_score: float | None = None
    skill_overlap: float | None = None
    rule_bonus: float | None = None
    # 新增五维评分字段
    five_dim_score: Dict[str, FiveDimScoreDetail] | None = None
    why_match: List[str] = Field(default_factory=list)
    skill_gaps: List[str] = Field(default_factory=list)

class MatchResponse(BaseModel):
    matches: List[JobMatch]

# ============================================================
# 工具：dict list → MatchResponse
# ============================================================
def _build_match_response(explain_jobs: list[dict]) -> MatchResponse:
    matches = []
    for idx, job in enumerate(explain_jobs):
        five_dim_raw = job.get("_five_dim", {})
        five_dim_scores = {
            dim: FiveDimScoreDetail(
                score=d.get("score", 0),
                weight=d.get("weight", 0),
                weighted_score=d.get("weighted_score", 0),
                details=d.get("details", {}),
            )
            for dim, d in five_dim_raw.items()
        } if five_dim_raw else None

        matches.append(JobMatch(
            job_id=job.get("job_id", str(idx)),
            job_title=job.get("job_title", ""),
            company=job.get("company", ""),
            score=job.get("score", 0.0),
            # 兼容旧字段
            semantic_score=job.get("semantic_score"),
            skill_overlap=job.get("skill_overlap"),
            rule_bonus=job.get("rule_bonus"),
            # 新增
            five_dim_score=five_dim_scores,
            why_match=job.get("why_match", []),
            skill_gaps=job.get("skill_gaps", []),
        ))
    return MatchResponse(matches=matches)

@router.post("/match_resume_org", response_model=MatchResponse)
async def match_resume_org(resume_input: ResumeInput):
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

@router.post("/match_resume", response_model=MatchResponse)
async def match_resume(resume_input: ResumeInput):
    """
    语义匹配接口（已升级为五维评分）
    """
    scorer = get_five_dim_scorer()
    all_jobs = load_jobs()              # 加载全量职位列表（你原有的函数）
    job_postings = jobs_to_postings(all_jobs)   # dict → JobPosting

    # 构造候选人 Profile（纯文本，无解析的技能拆分）
    candidate = CandidateProfile(
        resume_text=resume_input.resume_text,
        skills=[],   # 文本接口暂不解析技能列表，技能图谱维度会降权
    )

    results = await asyncio.get_event_loop().run_in_executor(
        None, partial(scorer.score_batch, candidate, job_postings, top_k=resume_input.top_k)
    )

    # 将五维结果转为 explain_match_loop 兼容格式
    job_meta_map = {j.get("job_id"): j for j in all_jobs}
    matched_jobs = [
        five_dim_result_to_job_dict(r, job_meta_map.get(r.job_id, {}))
        for r in results
    ]

    explain_jobs = await explain_match_loop(resume_input.resume_text, matched_jobs)
    return _build_match_response(explain_jobs)

@router.post("/match_resume_file_org", response_model=MatchResponse)
async def match_resume_file_org(
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
        parsed = await asyncio.get_event_loop().run_in_executor(
            None, partial(parse_resume_file, file_bytes, file.filename)
        )
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


# ============================================================
# 文件上传接口 - 改为五维评分（核心改造点）
# ============================================================
@router.post("/match_resume_file", response_model=MatchResponse)
async def match_resume_file(
    file: UploadFile = File(..., description="PDF or DOCX resume file"),
    top_k: int = 3,
):
    """
    文件上传接口：输入简历文件，输出 Top-K 岗位 + 解释
    """
    request_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    logger.info(f"[{request_id}] 📥 File upload | {file.filename} | top_k={top_k}")

    # ── 1. 类型校验 ────────────────────────────────────────
    ALLOWED_TYPES = {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    if file.content_type not in ALLOWED_TYPES:
        logger.warning(f"[{request_id}] ❌ Unsupported file type: {file.content_type}")
        raise HTTPException(status_code=400, detail="Only PDF/DOCX supported.")

    # ── 2. 解析简历 ────────────────────────────────────────
    file_bytes = await file.read()
    logger.info(f"[{request_id}] 📄 Size: {len(file_bytes)/1024:.1f} KB")

    try:
        # parse_resume_file calls sync Moonshot API – run in executor to avoid blocking event loop
        parsed = await asyncio.get_event_loop().run_in_executor(
            None, partial(parse_resume_file, file_bytes, file.filename)
        )
        logger.info(f"[{request_id}] ✅ Parsed | skills={parsed.get('skills', [])}")
    except Exception as e:
        logger.error(f"[{request_id}] ❌ Parse failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Parse error: {e}")

    resume_text = parsed.get("text", "")
    if not resume_text:
        raise HTTPException(status_code=400, detail="No text extracted from file.")

    # ── 3. 构建 CandidateProfile（关键：把解析到的所有信息塞进去）────
    candidate = build_candidate_profile(resume_text, parsed)
    logger.info(
        f"[{request_id}] 👤 Candidate | "
        f"skills={candidate.skills} | "
        f"exp={candidate.years_of_experience}yr | "
        f"seniority={candidate.seniority_self_reported} | "
        f"salary={candidate.expected_salary}"
    )

    # ── 4. 五维评分 ────────────────────────────────────────
    scorer   = get_five_dim_scorer()
    all_jobs = load_jobs()
    job_postings = jobs_to_postings(all_jobs)

    logger.info(f"[{request_id}] 🔎 Scoring {len(job_postings)} jobs (5-dim)...")
    results = await asyncio.get_event_loop().run_in_executor(
        None, partial(scorer.score_batch, candidate, job_postings, top_k=top_k)
    )
    logger.info(f"[{request_id}] ✅ Top-{len(results)} results ready")

    # 打印 Top-3 评分详情
    for i, r in enumerate(results[:3], 1):
        logger.info(
            f"[{request_id}] #{i} {r.job_id} | final={r.final_score:.3f} | "
            f"sem={r.semantic.score:.2f} skill={r.skill_graph.score:.2f} "
            f"sen={r.seniority.score:.2f} cul={r.culture.score:.2f} sal={r.salary.score:.2f}"
        )

    # ── 5. 转换为 LLM 解释器兼容格式 ──────────────────────
    job_meta_map = {j.get("job_id"): j for j in all_jobs}
    matched_jobs = [
        five_dim_result_to_job_dict(r, job_meta_map.get(r.job_id, {}))
        for r in results
    ]

    # ── 6. LLM 生成 why_match / skill_gaps ─────────────
    logger.info(f"[{request_id}] 🤖 Calling LLM explainer...")
    explain_jobs = await explain_match_loop(resume_text, matched_jobs)
    logger.info(f"[{request_id}] ✅ Explanations done")

    response = _build_match_response(explain_jobs)
    logger.info(f"[{request_id}] 🏁 Done, {len(response.matches)} matches returned")
    return response