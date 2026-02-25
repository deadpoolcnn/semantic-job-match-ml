"""
维度4: 文化/价值观匹配 (15%)
独立 Embedding 空间，专注文化信号词汇
"""
import re
import numpy as np
from sentence_transformers import SentenceTransformer
from src.models.schemas import CandidateProfile, JobPosting, DimensionScore
from src.core.match_config import DIMENSION_ANCHORS, CULTURE_DIMENSIONS

class CultureMatcher:
    """
    独立 Embedding 空间的文化匹配：
    1. 从文本中提取文化信号词
    2. 对各文化维度分别 Embed
    3. 计算候选人文化向量 vs 职位文化向量的相似度
    """
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        # 轻量模型用于文化维度（速度优先）
        self.model = SentenceTransformer(model_name)
        self.weight = 0.15
        self._dimension_embeddings = self._precompute_anchors()

    def _precompute_anchors(self) -> dict[str, np.ndarray]:
        """预计算各文化维度锚点 Embedding"""
        return {
            dim: self.model.encode(anchor, normalize_embeddings=True)
            for dim, anchor in DIMENSION_ANCHORS.items()
        }
    
    def _extract_culture_text(self, text: str, keywords_list: list[str]) -> str:
        """从文本中提取含文化信号的句子"""
        sentences = re.split(r"[.!?\n]", text)
        all_keywords = {kw for kws in CULTURE_DIMENSIONS.values() for kw in kws}
        all_keywords.update(k.lower() for k in keywords_list)

        relevant = []
        for sent in sentences:
            sent_lower = sent.lower()
            if any(kw in sent_lower for kw in all_keywords):
                relevant.append(sent.strip())

        return " ".join(relevant) if relevant else text[:500]
    
    def _text_to_culture_vector(self, text: str, extra_keywords: list[str]) -> np.ndarray:
        """
        将文本映射为 N-维文化向量（N = 文化维度数）
        每个维度得分 = 文本 Embedding 与维度锚点的余弦相似度
        """
        culture_text = self._extract_culture_text(text, extra_keywords)
        text_emb = self.model.encode(culture_text, normalize_embeddings=True)

        vector = np.array([
            float(np.dot(text_emb, anchor_emb))
            for anchor_emb in self._dimension_embeddings.values()
        ])
        # 归一化到 [0, 1]
        vector = (vector + 1) / 2
        return vector
    
    def score(self, candidate: CandidateProfile, job: JobPosting) -> DimensionScore:
        candidate_text = candidate.resume_text
        job_text = f"{job.title}\n{job.description}\n{' '.join(job.company_values)}"

        candidate_vec = self._text_to_culture_vector(candidate_text, candidate.culture_keywords)
        job_vec = self._text_to_culture_vector(job_text, job.culture_keywords)

        # 余弦相似度（两个文化向量之间）
        norm_c = np.linalg.norm(candidate_vec)
        norm_j = np.linalg.norm(job_vec)
        if norm_c == 0 or norm_j == 0:
            similarity = 0.5  # 无信号时中性分
        else:
            similarity = float(np.dot(candidate_vec, job_vec) / (norm_c * norm_j))
            similarity = max(0.0, min(1.0, similarity))

        dim_names = list(CULTURE_DIMENSIONS.keys())
        dim_scores = {
            dim: round(float(candidate_vec[i]), 3)
            for i, dim in enumerate(dim_names)
        }

        return DimensionScore(
            score=similarity,
            weight=self.weight,
            weighted_score=similarity * self.weight,
            details={
                "culture_similarity": round(similarity, 3),
                "candidate_culture_vector": dim_scores,
                "job_culture_vector": {
                    dim: round(float(job_vec[i]), 3)
                    for i, dim in enumerate(dim_names)
                },
            },
        )
