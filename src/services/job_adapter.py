"""
Convert raw job dicts from job_loader into JobPosting objects for FiveDimScorer.
"""

import re

from src.models.schemas import JobPosting, SalaryRange


def _parse_salary_string(salary_str: str) -> SalaryRange | None:
    """
    Parse salary strings like '$120k - $180k' or '$150k-$220k' into SalaryRange.
    """
    if not salary_str:
        return None
    # Match patterns: $120k, $120,000, 120k
    pattern = re.compile(r"\$?([\d,.]+)(k?)", re.IGNORECASE)
    matches = pattern.findall(salary_str.replace(",", ""))
    values = []
    for num_str, k_suffix in matches:
        try:
            val = float(num_str) * (1000 if k_suffix.lower() == "k" else 1)
            if val > 1000:  # sanity check
                values.append(val)
        except ValueError:
            pass
    if len(values) >= 2:
        return SalaryRange(min_salary=min(values), max_salary=max(values))
    if len(values) == 1:
        return SalaryRange(min_salary=values[0] * 0.85, max_salary=values[0] * 1.15)
    return None


def jobs_to_postings(raw_jobs: list[dict]) -> list[JobPosting]:
    """Convert raw job dicts from job_loader into JobPosting objects."""
    postings = []
    for job in raw_jobs:
        # Support structured salary fields OR the 'salary_range' string in job_mock.json
        if job.get("salary_min") or job.get("salary_max"):
            salary_range = SalaryRange(
                min_salary=job.get("salary_min"),
                max_salary=job.get("salary_max"),
                currency=job.get("salary_currency", "USD"),
                period=job.get("salary_period", "annual"),
            )
        else:
            salary_range = _parse_salary_string(job.get("salary_range", ""))

        postings.append(JobPosting(
            job_id=job.get("job_id", ""),
            title=job.get("job_title", ""),
            description=job.get("description", ""),
            required_skills=job.get("required_skills", []),
            # job_mock uses 'nice_to_have'; fall back to 'preferred_skills'
            preferred_skills=job.get("nice_to_have") or job.get("preferred_skills", []),
            # job_mock uses 'seniority'; fall back to 'seniority_level' / 'level'
            seniority_level=job.get("seniority") or job.get("seniority_level") or job.get("level"),
            salary_range=salary_range,
            culture_keywords=job.get("culture_keywords", []),
            company_values=job.get("company_values", []),
        ))
    return postings

