from pathlib import Path
from typing import List, Dict, Any, Optional, Set
import re

import numpy as np
import faiss

from src.models.embedder import encode_texts
from src.services.resume_parser import extract_skills_from_resume
from src.core.match_config import SENIORITY_HIERARCHY, TECH_ECOSYSTEMS, SENIORITY_MATCH_SCORES, get_seniority_keywords

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
INDEX_DIR = DATA_DIR / "indices"
INDEX_PATH = INDEX_DIR / "jobs_faiss.index"
META_PATH = INDEX_DIR / "jobs_meta.json"

class JobMatcher:
    def __init__(self):
        # 加载FAISS索引和岗位元信息
        if not INDEX_PATH.exists() or not META_PATH.exists():
            raise FileNotFoundError(f"FAISS index not found at {INDEX_PATH} or metadata not found at {META_PATH}")
        
        self.index = faiss.read_index(str(INDEX_PATH))
        import json
        with open(META_PATH, "r", encoding="utf-8") as f:
            meta = json.load(f)
        self.jobs: List[Dict[str, Any]] = meta["jobs"]

        # sanity check 防止FAISS索引和岗位元信息不匹配
        if self.index.ntotal != len(self.jobs):
            raise ValueError(f"FAISS index contains {self.index.ntotal} vectors but metadata has {len(self.jobs)} jobs")
    
    def semantic_match(
        self,
        resume_text: str,
        top_k: int = 10,
        resume_skills: Optional[Set[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        输入简历文本，返回匹配岗位列表（包含岗位信息和匹配分数）
        增强匹配策略
        1. FAISS语义召回：基于简历文本的向量表示，在FAISS索引中搜索最相似的岗位向量，返回 top_k 个结果
        2. 多维度精排：对召回的岗位进行综合排序，考虑语义相似度、技能重叠度、规则加分等因素
        3. 必备技能硬过滤
        """
        # 1. 将简历文本编码为向量 语义召回（top_k * 3）
        resume_embedding = encode_texts([resume_text]).astype("float32") # (1, D) 的 numpy 数组
        # 归一化
        faiss.normalize_L2(resume_embedding)

        # 2. 在FAISS索引中搜索最相似的岗位向量，返回 top_k 个结果(搜索最临近)
        # top_k = min(top_k, self.index.ntotal) # 确保 top_k 不超过索引中的向量数量
        recall_size = min(top_k * 3, self.index.ntotal) # 召回数量可以适当大于 top_k，后续精排过滤掉一些结果
        # search() FAISS索引中搜索最相似的岗位向量，返回 top_k 个结果
        # 返回值：scores: 相似度分数(2D数组) indices: 对应的岗位索引编号
        scores, indices = self.index.search(resume_embedding, recall_size) # scores shape (1, recall_size)，indices shape (1, recall_size)
        
        scores = scores[0] # (recall_size,) 的 numpy 数组
        indices = indices[0] # (recall_size,) 的 numpy 数组

        # 3. 简历技能集合
        # if resume_skills is None:
        #     resume_skills = extract_skills_from_resume(resume_text)
        # resume_skills = { s.lower() for s in resume_skills } # 小写
        if resume_skills is None:
            resume_skills = set()
        elif not isinstance(resume_skills, set):
            resume_skills = set(s.lower().strip() for s in resume_skills)

        # ✅ 添加调试日志
        print(f"DEBUG: Resume skills for matching: {resume_skills}")
        print(f"DEBUG: Resume skills count: {len(resume_skills)}")

        results: List[Dict[str, Any]] = [] # 存储类型为 List[Dict[str, Any]] 的结果列表
        # 技能overlap过滤：如果岗位要求的技能和简历技能完全没有交集，可以考虑过滤掉（可选）
        for score, idx in zip(scores, indices):
            if idx < 0 or idx >= len(self.jobs):
                continue # 跳过无效索引
            job = self.jobs[idx].copy() # 获取岗位信息并复制，避免修改原数据
            # job["score"] = float(score) # 添加匹配分数到岗位信息中
            semantic_score = float(score)

            # 2. 技能重叠度计算
            job_skills_raw = job.get("skills", [])
            print(f"DEBUG: Job '{job.get('job_title')}' skills (raw): {job_skills_raw}")
            # ✅ 确保 job_skills 也是小写集合
            job_skills = set(s.lower().strip() for s in job_skills_raw if s) # 岗位要求的技能集合（小写）
            print(f"DEBUG: Job skills (lowercase): {job_skills}")
            # 必备技能硬过滤
            required_skills_raw = job.get("required_skills", [])
            required_skills = set(s.lower().strip() for s in required_skills_raw if s)
            if required_skills:
                missing_required = required_skills - resume_skills
                if len(missing_required) > 0:
                    # ✅ 缺少任何必备技能，直接跳过
                    continue
            # --- 2. 技能匹配度（50% 权重） ---
            if job_skills and resume_skills:
                overlap = resume_skills & job_skills # 简历技能和岗位技能的交集
                overlap_skill = len(overlap) / len(job_skills)
                print(f"DEBUG: Skill overlap: {overlap} ({overlap_skill:.2%})")
                # ✅ bonus for full skill match
                if len(overlap) == len(job_skills):
                    overlap_skill = min(1.0, overlap_skill + 0.1)
            else:
                overlap_skill = 0.0
                print(f"DEBUG: No overlap (job_skills empty: {not job_skills}, resume_skills empty: {not resume_skills})")
            # --- 3. 职级匹配（10% 权重） ---
            seniority_score = self._calculate_seniority_match(resume_text, job.get("job_title", ""))
            # --- 4. 技术栈匹配（10% 权重） ---
            tech_stack_score = self._calculate_tech_stack_match(resume_skills, job_skills)
            # 综合分数：调整权重：技能 > 语义（因为技能匹配更重要）
            w_sem, w_skill, w_sen, w_tech = 0.3, 0.5, 0.1, 0.1
            final_score = semantic_score * w_sem + overlap_skill * w_skill + seniority_score * w_sen + tech_stack_score * w_tech
            job["semantic_score"] = round(semantic_score, 4)
            job["skill_overlap"] = round(overlap_skill, 4)
            job["seniority_score"] = round(seniority_score, 4)
            job["tech_stack_score"] = round(tech_stack_score, 4)
            job["score"] = round(final_score, 4)
            results.append(job)
        results.sort(key=lambda x: x["score"], reverse=True) # 按照综合分数排序
        return results
    


def _calculate_seniority_match(self, resume_text: str, job_title: str) -> float:
        """
        职级匹配算法：根据简历文本和岗位标题中的关键词，判断职级匹配程度
        可以使用更复杂的 NLP 技术来提取职级信息，这里只是一个示例
        """
        resume_lower = resume_text.lower()
        job_title_lower = job_title.lower()

        resume_seniority_level = None
        job_seniority_level = None
        # 获取排序后的关键词（长关键词优先匹配）
        sorted_keywords = get_seniority_keywords()
        # 简历文本中匹配职级关键词
        for keyword in sorted_keywords:
            pattern = r'\b' + re.escape(keyword) + r'\b' # 使用正则表达式确保匹配完整单词
            if re.search(pattern, resume_lower):
                resume_seniority_level = SENIORITY_HIERARCHY[keyword]
                break
        # 岗位标题中匹配职级关键词
        for keyword in sorted_keywords:
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, job_title_lower):
                job_seniority_level = SENIORITY_HIERARCHY[keyword]
                break
        # 无法识别职级，返回中性分数
        if resume_seniority_level is None or job_seniority_level is None:
            return 0.5
        
        # 计算职级差异
        level_diff = resume_seniority_level - job_seniority_level
        # 使用配置的分数映射
        if level_diff in SENIORITY_MATCH_SCORES:
            return SENIORITY_MATCH_SCORES[level_diff]
        elif level_diff >= 3:
            return SENIORITY_MATCH_SCORES[3]
        elif level_diff <= -3:
            return SENIORITY_MATCH_SCORES[-3]
        else:
            return 0.5

def _calculate_tech_stack_match(self, resume_skills: Set[str], job_skills: Set[str]) -> float:
        """
        技术栈匹配算法：根据简历技能和岗位技能所属的技术生态系统，判断技术栈匹配程度
        例如，如果简历中有 React 和 Node.js，而岗位要求 React 和 Python，那么技术栈匹配度较高（同属 Web 开发生态）
        """
        if not resume_skills or not job_skills:
            return 0.0
        
        total_match_score = 0.0
        ecosystem_evaluated = 0

        for ecosystem_name, ecosystem_skills in TECH_ECOSYSTEMS.items():
            # 职位要求的该生态技能
            job_in_ecosystem = job_skills & ecosystem_skills
            if not job_in_ecosystem:
                continue # 岗位没有这个生态的技能要求，跳过
            # 简历拥有的该生态技能
            resume_in_ecosystem = resume_skills & ecosystem_skills
            if resume_in_ecosystem:
                # 计算该生态的匹配度（可以根据需求调整算法，这里简单计算交集占岗位要求的比例）
                match_score = len(resume_in_ecosystem) / len(job_in_ecosystem)
                total_match_score += match_score
            ecosystem_evaluated += 1
        if ecosystem_evaluated == 0:
            return 0.5
        return total_match_score / ecosystem_evaluated

    # 做一个全局单例，避免重复加载FAISS索引和岗位数据

_job_matcher_instance: JobMatcher | None = None


def get_job_matcher() -> JobMatcher:
    global _job_matcher_instance
    if _job_matcher_instance is None:
        _job_matcher_instance = JobMatcher()
    return _job_matcher_instance
