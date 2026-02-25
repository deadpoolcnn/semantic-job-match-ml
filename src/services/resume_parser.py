from typing import Set, Dict, Any
import io
import json
import pdfplumber
from openai import OpenAI

from src.core.config import get_moonshot_api_key, get_moonshot_model

_client = OpenAI(
    api_key=get_moonshot_api_key(),
    base_url="https://api.moonshot.ai/v1",
)
MOONSHOT_MODEL = get_moonshot_model()

# TODO: Extract skill keywords from resume text. Currently a simple keyword lookup;
# consider replacing with a proper NLP/LLM-based extractor.
KNOWN_SKILLS: Set[str] = {
    "react", "next.js", "nextjs", "node.js", "node", "typescript",
    "python", "pytorch", "tensorflow", "solidity", "web3", "rust",
    "docker", "kubernetes", "aws", "gcp"
}

def extract_skills_from_resume(resume_text: str) -> Set[str]:
    """Extract skill keywords from resume text via simple keyword matching."""
    resume_text = resume_text.lower()
    found = set()
    for skill in KNOWN_SKILLS:
        if skill in resume_text:
            found.add(skill)
    return found

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract plain text from PDF bytes using pdfplumber."""
    textchunk = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            textchunk.append(page.extract_text())
    return "\n".join(textchunk).strip()

def parse_resume_file(file_bytes: bytes, filename: str) -> dict:
    """
    Parse a resume file: extract raw text with pdfplumber, then call
    Moonshot Kimi for structured JSON extraction.
    Returns: {"text": <embedding-ready summary>, "skills": <set>, "raw": <full LLM JSON>}
    """
    raw_text = extract_text_from_pdf(file_bytes)
    if not raw_text:
        raise ValueError("No text extracted from PDF. The file may be scanned or encrypted.")
    # 2. Call Moonshot for structured JSON extraction
    gemini_json = _call_moonshot_for_structured_resume(raw_text)
    # 3. Unpack structured fields from Moonshot response
    name = gemini_json.get("name", "")
    email = gemini_json.get("email", "")
    skills = set(gemini_json.get("skills", []))
    total_exp_years = gemini_json.get("total_experience_years")
    current_title = gemini_json.get("current_title", "")
    summary = gemini_json.get("summary", "")
    seniority = gemini_json.get("seniority")
    culture_keywords = gemini_json.get("culture_keywords", [])
    expected_salary = gemini_json.get("expected_salary")
    # 4. Build embedding-ready resume summary
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
        "raw": {
            **gemini_json,
            "experience_years": total_exp_years,    # consumed by build_candidate_profile
            "seniority": seniority,
            "culture_keywords": culture_keywords,
            "expected_salary": expected_salary,
        },
    }

def _call_moonshot_for_structured_resume(raw_text: str) -> Dict[str, Any]:
    """Call Moonshot Kimi to extract structured JSON from raw resume text."""
    prompt = f"""You are a professional resume parsing assistant.
Extract key structured information from the resume text below.

Resume text:
\"\"\"{raw_text}\"\"\"

Respond with ONLY a valid JSON object, no extra explanation. Required fields:
{{
    "name": "Candidate full name (if identifiable, else empty string)",
    "email": "Email address (if found, else empty string)",
    "phone": "Phone number (if found, else empty string)",
    "current_title": "Current or most recent job title",
    "total_experience_years": 3.5,
    "skills": ["React", "Next.js", "Node.js", "Python"],
    "summary": "One-sentence or short-paragraph professional summary",
    "seniority": "Inferred level: intern | junior | mid | senior | staff | manager | director",
    "culture_keywords": ["remote", "collaborative", "fast-paced"],
    "expected_salary": {{"min": 120000, "max": 150000, "currency": "USD", "period": "annual"}}
}}"""

    response = _client.chat.completions.create(
        model=MOONSHOT_MODEL,
        messages=[
            {"role": "system", "content": "You are a professional resume parsing assistant. Output only valid JSON, nothing else."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    try:
        content = response.choices[0].message.content or "{}"
        data = json.loads(content)
        if not isinstance(data, dict):
            raise ValueError("Moonshot response is not a JSON object.")
        return data
    except json.JSONDecodeError:
        return {
            "name": "",
            "email": "",
            "phone": "",
            "current_title": "",
            "total_experience_years": None,
            "skills": [],
            "summary": "",
            "seniority": None,
            "culture_keywords": [],
            "expected_salary": None,
        }
    