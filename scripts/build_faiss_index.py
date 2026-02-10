from pathlib import Path
import json
from typing import List, Dict, Any

import numpy as np
import faiss
from src.models.embedder import encode_texts

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
JOBS_PATH = DATA_DIR / "jobs" / "job_mock.json"
INDEX_DIR = DATA_DIR / "indices"
INDEX_DIR.mkdir(parents=True, exist_ok=True)
INDEX_PATH = INDEX_DIR / "jobs_faiss.index"
META_PATH = INDEX_DIR / "jobs_meta.json"

def load_jobs() -> List[Dict]:
    with open(JOBS_PATH, "r", encoding="utf-8") as f:
        jobs = json.load(f)
    return jobs

def build_corpus_text(job: Dict[str, Any]) -> str:
    """
    构建岗位文本语料，包含岗位描述、要求等信息
    """
    title = job.get("job_title", "")
    company = job.get("company", "")
    desc = job.get("description", "")
    requirements = job.get("requirements", "")
    skills = job.get("skills", "")
    text = f"{title}\nCompany: {company}\nRequirements: {requirements}\nSkills: {skills}\nDescription: {desc}"
    return text

def main():
    jobs = load_jobs()
    if not jobs:
         raise RuntimeError("No jobs found in jobs_mock.json")
    texts = [build_corpus_text(job) for job in jobs]
    # 已做L2正则化，直接使用内积索引相当于余弦相似度
    embeddings = encode_texts(texts) # (N, D) 的 numpy 数组（10， 768） 

    # L2正则化，确保每个向量的模长为1，这样内积相当于余弦相似度
    faiss.normalize_L2(embeddings) # 原地操作，修改 embeddings 数组

    num_jobs, dim = embeddings.shape # 职位数 10，向量维度 768
    print(f"Loaded {num_jobs} jobs, embedding dim = {dim}")

    # 使用内积IndexFlatIP(因为上面已 normalize，相当于余弦相似度）暴力搜索，内积索引不需要训练，直接添加向量即可
    # 存储内容：向量+索引编号 快速搜索相似职位
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings.astype("float32")) # 将岗位向量添加到索引中

    faiss.write_index(index, str(INDEX_PATH)) # 保存索引到磁盘
    print(f"FAISS index saved to {INDEX_PATH}")

    # 存储内容：完整职位信息，根据索引还原原始数据
    # 保存岗位元信息（id、title、company等）到 JSON 文件，供后续查询使用
    meta = {
        "jobs": jobs
    }
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"Job metadata saved to {META_PATH}")

if __name__ == "__main__":
    main()