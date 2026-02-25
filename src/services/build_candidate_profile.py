"""
工具函数：构建候选人简历的结构化信息（CandidateProfile），以便后续进行匹配和评分。
"""

from src.models.schemas import CandidateProfile, SalaryRange


def build_candidate_profile(resume_text: str, parsed: dict,) -> CandidateProfile:
    """
    输入：简历文本
    输出：CandidateProfile对象，包含结构化的技能、职级、期望薪资等信息
    处理流程：
    1. 使用resume_parser解析简历文本，提取技能列表、职级信息、期望薪资等字段。
    2. 对提取的信息进行清洗和标准化（如技能名称统一、职级映射等）。
    3. 构建CandidateProfile对象并返回。

    将 parse_resume_file 的输出转为 CandidateProfile
    parsed 结构示例:
    {
      "text": "...",
      "skills": ["python", "docker"],
      "raw": { "experience_years": 5, "expected_salary": {...} }
    }
    """
    raw = parsed.get("raw", {})
    # 薪资提取（如果解析器已提取）
    salary_info = raw.get("expected_salary")
    expected_salary = None
    if salary_info and isinstance(salary_info, dict):
        expected_salary = SalaryRange(
            min_salary=salary_info.get("min"),
            max_salary=salary_info.get("max"),
            currency=salary_info.get("currency", "USD"),
            period=salary_info.get("period", "annual"),
        )

    # skills may be a set (from resume_parser); ensure it's a list
    raw_skills = parsed.get("skills", [])
    skills_list = list(raw_skills) if raw_skills else []

    return CandidateProfile(
        resume_text=resume_text,
        skills=skills_list,
        years_of_experience=raw.get("experience_years"),
        seniority_self_reported=raw.get("seniority"),
        expected_salary=expected_salary,
        culture_keywords=raw.get("culture_keywords", []),
    )

def five_dim_result_to_job_dict(result, job_meta: dict) -> dict:
    """将五维评分结果转换为API输出的JobMatch格式"""
    return {
        "job_id": result.job_id,
        "job_title": job_meta.get("job_title") or job_meta.get("title", ""),
        "company": job_meta.get("company", ""),
        "score": result.final_score,
        "semantic_score": result.semantic.score,
        "skill_overlap": result.skill_graph.score,
        "rule_bonus": result.seniority.score,
        "_five_dim": {
            "semantic":    result.semantic.__dict__,
            "skill_graph": result.skill_graph.__dict__,
            "seniority":   result.seniority.__dict__,
            "culture":     result.culture.__dict__,
            "salary":      result.salary.__dict__,
        },
        # LLM 解释器需要的原始描述（保持透传）
        "description": job_meta.get("description", ""),
        "required_skills": job_meta.get("required_skills", []),
    }
