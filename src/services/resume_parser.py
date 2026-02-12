from typing import Set
from pathlib import Path
from typing import Dict, Any
import tempfile
import io
import pdfplumber

from google import genai
from google.genai import types as genai_types

from src.core.config import get_gemini_api_key, get_gemini_model

GEMINI_API_KEY = get_gemini_api_key()
GEMINI_MODEL = get_gemini_model()

client = genai.Client(api_key=GEMINI_API_KEY)

# TODO: 这个模块的功能是从简历文本中提取技能关键词，目前实现非常简单，后续可以考虑用更复杂的 NLP 模型来做（比如基于 LLM 的信息抽取）
KNOWN_SKILLS: Set[str] = {
    "react", "next.js", "nextjs", "node.js", "node", "typescript",
    "python", "pytorch", "tensorflow", "solidity", "web3", "rust",
    "docker", "kubernetes", "aws", "gcp"
}

def extract_skills_from_resume(resume_text: str) -> Set[str]:
    """
    从简历文本中提取技能关键词，目前实现非常简单，就是在文本中查找已知技能列表中的词
    后续可以考虑用更复杂的 NLP 模型来做（比如基于 LLM 的信息抽取）
    """
    resume_text = resume_text.lower()
    found = set()
    for skill in KNOWN_SKILLS:
        if skill in resume_text:
            found.add(skill)
    return found

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    从 PDF 文件的二进制内容中提取文本，目前使用 pdfplumber 库实现
    """
    textchunk = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            textchunk.append(page.extract_text())
    return "\n".join(textchunk).strip()

def parse_resume_file(file_bytes: bytes, filename: str) -> str:
    """
    新版解析：pdfplumber 抽原文 + Gemini 结构化解析。
    输出结构保持和之前类似：
      {
        "text": "...用于 embedding 的简历摘要...",
        "skills": [...],
        "raw": {...}   # LLM 返回的完整 JSON
      }
    """
    raw_text = extract_text_from_pdf(file_bytes)
    if not raw_text:
        raise ValueError("无法从 PDF 中提取文本，可能是扫描件或加密文件")
    # 2. 调 Gemini 做结构化解析（JSON 输出）
    gemini_json = _call_gemini_for_structured_resume(raw_text)
    # 3. 从 Gemini 输出中提取技能关键词（如果有的话）
    name = gemini_json.get("name", "")
    email = gemini_json.get("email", "")
    skills = set(gemini_json.get("skills", []))
    total_exp_years = gemini_json.get("total_experience_years")
    current_title = gemini_json.get("current_title", "")
    summary = gemini_json.get("summary", "")
    # 4. 构造用于 embedding 的简历摘要文本（可以根据需要调整格式）
    parts = [
        f"Name: {name}" if name else "",
        f"Email: {email}" if email else "",
        f"Current title: {current_title}" if current_title else "",
        f"Total experience (years): {total_exp_years}" if total_exp_years is not None else "",
        f"Skills: {', '.join(skills)}" if skills else "",
        f"Summary: {summary}" if summary else "",
        f"Raw text: {raw_text}",
    ]
    resume_text = "\n".join(part for part in parts if part).strip()
    return {
        "text": resume_text,
        "skills": skills,
        "raw": gemini_json,
    }

def _call_gemini_for_structured_resume(raw_text: str) -> Dict[str, Any]:
    """
    调用 Gemini 生成式模型，输入简历原文，输出结构化的 JSON 数据
    这里的 prompt 设计非常关键，可以根据需要调整以获得更准确的解析结果
    """
    prompt = f"""
    You are a resume parsing assistant. 
    Extract key structured information from the following resume text.

    简历文本：
    \"\"\"{raw_text}\"\"\"

    请严格以 JSON 格式输出，不要添加多余说明，字段包括：
    {{
        "name": "Candidate's full name (if identifiable)",
        "email": "Email address (if found)",
        "phone": "Phone number (if found)",
        "current_title": "Current or most recent job title",
        "total_experience_years": 3.5,
        "skills": ["React", "Next.js", "Node.js", "Python"],
        "summary": "Brief professional summary in one sentence or short paragraph"
    }}
    """.strip()
    
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            temperature=0.2,
            response_mime_type="application/json" # 直接让 Gemini 输出 JSON，便于解析
        )
    )
    import json
    try:
        content = response.text or "{}"
        data = json.loads(content)
        if not isinstance(data, dict):
            raise ValueError("Gemini 输出的 JSON 不是一个对象")
        return data
    except json.JSONDecodeError as e:
        return {
            "name": "",
            "email": "",
            "phone": "",
            "current_title": "",
            "total_experience_years": None,
            "skills": [],
            "summary": "",
            "raw_text_fallback": raw_text,
        }
    