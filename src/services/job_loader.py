from pathlib import Path
import json
from typing import List, Dict, Any

DATA_DIR = Path(__file__).resolve().parent / "data"

def load_jobs() -> List[Dict[str, Any]]:
    """
    加载岗位数据，假设是一个 JSON 文件，返回岗位列表
    """
    jobs_file = DATA_DIR / "job_mock.json"
    if not jobs_file.exists():
        raise FileNotFoundError(f"岗位数据文件 {jobs_file} 不存在")
    
    with open(jobs_file, "r", encoding="utf-8") as f:
        jobs = json.load(f)
    
    return jobs