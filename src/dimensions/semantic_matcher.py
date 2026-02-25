"""
维度1: 语义匹配 (30%)
MPNet + FAISS 语义相似度
"""

import numpy as np
from sentence_transformers import SentenceTransformer
from src.models.schemas import CandidateProfile, JobPosting, DimensionScore

class SemanticMatcher:
    """
    使用 all-mpnet-base-v2 计算简历与 JD 语义相似度
    """
    def __init__(self, model_name: str = "sentence-transformers/all-mpnet-base-v2"):
        self.model = SentenceTransformer(model_name)
        self.weight = 0.30
    
    def _encode(self, text: str) -> np.ndarray:
        return self.model.encode(text, normalize_embeddings=True)
    
    def score(self, candidate: CandidateProfile, job: JobPosting) -> DimensionScore:
        resume_emb = self._encode(candidate.resume_text)
        job_text = f"{job.title}\n{job.description}"
        job_emb = self._encode(job_text)

        # cosine similarity（已 normalize，直接点积）
        similarity = float(np.dot(resume_emb, job_emb))
        similarity = max(0.0, min(1.0, similarity))

        return DimensionScore(
            score=similarity,
            weight=self.weight,
            weighted_score=similarity * self.weight,
            details={"cosine_similarity": similarity},
        )