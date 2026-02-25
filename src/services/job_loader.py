from pathlib import Path
import json
from typing import List, Dict, Any

# Project root → data/jobs/
DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "jobs"

def load_jobs() -> List[Dict[str, Any]]:
    """Load job postings from the mock JSON file."""
    jobs_file = DATA_DIR / "job_mock.json"
    if not jobs_file.exists():
        raise FileNotFoundError(f"Job data file not found: {jobs_file}")
    
    with open(jobs_file, "r", encoding="utf-8") as f:
        jobs = json.load(f)
    
    return jobs