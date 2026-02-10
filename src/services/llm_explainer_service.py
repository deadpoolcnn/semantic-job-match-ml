import os
from typing import List, Dict, Any

from google import genai
from google.genai import types as genai_types

from src.core.config import get_gemini_api_key, get_gemini_model

GEMINI_API_KEY = get_gemini_api_key()
GEMINI_MODEL = get_gemini_model()

client = genai.Client(api_key=GEMINI_API_KEY)

async def explain_match(
    resume_text: str,
    jobs: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    输入：原始简历文本 + 语义匹配出来的 job 列表（含 title/skills/description/score）
    输出：在每个 job dict 上加 why_match / skill_gaps 字段
    """
    explained: List[Dict[str, Any]] = []

    # 简单版：逐个岗位调用一次 Gemini（Top-K 不要太大，控制在 3–5）
    for job in jobs:
        prompt = _build_prompt(resume_text, job)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json" # 直接让 Gemini 输出 JSON，便于解析
            )
        )
        content = response.text or "{}"
        why_match, skill_gaps = _parse_llm_response(content)
        job_with_explanation = job.copy()
        job_with_explanation["why_match"] = why_match
        job_with_explanation["skill_gaps"] = skill_gaps
        explained.append(job_with_explanation)
    return explained

def _build_prompt(resume_text: str, job: Dict[str, Any]) -> str:
    """
    构建给 LLM 的 prompt，包含简历文本和岗位信息
    可以在这里设计一些提示词，引导 LLM 生成更有用的解释
    """
    title = job.get("job_title", "")
    company = job.get("company", "")
    desc = job.get("description", "")
    requirements = job.get("requirements", "")
    skills = job.get("skills", "")
    score = job.get("score", 0.0)

    return f"""
    You are a technical recruitment assistant. Analyze the candidate's resume and job description to provide match reasons and skill gaps.
    
    Candidate Resume:
    {resume_text}
    
    Job Information:
    Title: {title}
    Company: {company}
    Required Skills: {skills}
    Description: {desc}
    Semantic Match Score (0-1): {score:.2f}

    Output a valid JSON only, without any additional explanation. Structure:
    {{
    "why_match": ["reason 1", "reason 2", "reason 3"],
    "skill_gaps": ["missing skill 1", "missing skill 2"]
    }}
    """.strip()

def _parse_llm_response(content: str):
    """
    解析 LLM 输出的 JSON 内容，提取 why_match 和 skill_gaps
    """
    import json
    try:
        data = json.loads(content)
        why_match = data.get("why_match", [])
        skill_gaps = data.get("skill_gaps", [])
        if not isinstance(why_match, list):
            why_match = [str(why_match)]
        if not isinstance(skill_gaps, list):
            skill_gaps = [str(skill_gaps)]
        return why_match, skill_gaps
    except json.JSONDecodeError:
        # 解析失败，返回空列表
        return ["LLM 解释解析失败"], []