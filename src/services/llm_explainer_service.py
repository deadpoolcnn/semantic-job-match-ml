import asyncio
from typing import List, Dict, Any

from openai import AsyncOpenAI

from src.core.config import get_moonshot_api_key, get_moonshot_model

_client = AsyncOpenAI(
    api_key=get_moonshot_api_key(),
    base_url="https://api.moonshot.ai/v1",
)
MOONSHOT_MODEL = get_moonshot_model()


async def _explain_single_job(resume_text: str, job: Dict[str, Any]) -> Dict[str, Any]:
    """Asynchronously generate match explanation for a single job."""
    prompt = _build_prompt(resume_text, job)
    response = await _client.chat.completions.create(
        model=MOONSHOT_MODEL,
        messages=[
            {"role": "system", "content": "You are a technical recruitment assistant. Always respond with valid JSON only, no extra text."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or "{}"
    why_match, skill_gaps = _parse_llm_response(content)
    job_with_explanation = job.copy()
    job_with_explanation["why_match"] = why_match
    job_with_explanation["skill_gaps"] = skill_gaps
    return job_with_explanation


async def explain_match_loop(resume_text: str, jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Concurrently explain all matched jobs."""
    tasks = [_explain_single_job(resume_text, job) for job in jobs]
    explained = await asyncio.gather(*tasks)
    return list(explained)


async def explain_match(
    resume_text: str,
    jobs: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    return await explain_match_loop(resume_text, jobs)

def _build_prompt(resume_text: str, job: Dict[str, Any]) -> str:
    """Build the LLM prompt containing resume and job information."""
    title = job.get("job_title", "")
    company = job.get("company", "")
    desc = job.get("description", "")
    requirements = job.get("requirements", "")
    skills = job.get("required_skills", [])
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
    """Parse LLM JSON output and extract why_match and skill_gaps."""
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
        return ["Failed to parse LLM response."], []