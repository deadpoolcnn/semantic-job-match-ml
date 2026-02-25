"""
维度2: 技能图谱匹配 (25%)
构建 Skill Graph，通过图游走计算技能相关性，
避免"会 PyTorch 但不会 TensorFlow"被直接判 0 分
"""

import numpy as np
import networkx as nx
from collections import defaultdict
from typing import Optional
from src.models.schemas import CandidateProfile, JobPosting, DimensionScore
from src.core.match_config import TECH_ECOSYSTEMS, SKILL_RELATIONS

# ============================================
# 技能图谱构建
# ============================================

def build_skill_graph() -> nx.Graph:
    """
    构建全局技能关系图：
    - 节点: 技能名
    - 边权重: 相关性强度 (0~1)
    - 同生态系统技能自动添加弱关联边
    """
    G = nx.Graph()
    # 1. 添加显式关系
    for skill_a, skill_b, weight in SKILL_RELATIONS:
        G.add_edge(skill_a, skill_b, weight=weight)
    
    # 2. 添加生态系统内的弱关联
    for ecosystem, skills in TECH_ECOSYSTEMS.items():
        skill_list = list(skills)
        for i in range(len(skill_list)):
            for j in range(i + 1, len(skill_list)):
                s_a, s_b = skill_list[i], skill_list[j]
                if not G.has_edge(s_a, s_b):
                    G.add_edge(s_a, s_b, weight=0.4)
    return G

class SkillGraphMatcher:
    """
    基于图游走的技能相关性评分：
    - 精确匹配: 满分
    - 图中邻居 (hop=1): 按边权重折扣
    - 图中邻居 (hop=2): 更大折扣
    - 无关联: 0 分
    """
    # 图游走折扣系数
    HOP1_DISCOUNT = 0.7   # 1跳邻居得分折扣
    HOP2_DISCOUNT = 0.4   # 2跳邻居得分折扣

    def __init__(self):
        self.graph = build_skill_graph()
        self.weight = 0.25
        # 预计算节点列表（小写归一化）
        self._nodes = {n.lower() for n in self.graph.nodes()}
    
    def _normalize_skill(self, skill: str) -> str:
        return skill.lower().strip()
    
    def _skill_similarity(self, candidate_skill: str, required_skill: str) -> float:
        """计算单个候选技能 vs 要求技能的相似度"""
        c = self._normalize_skill(candidate_skill)
        r = self._normalize_skill(required_skill)

        # 精确匹配
        if c == r:
            return 1.0

        # 子串匹配（处理别名如 react.js / reactjs）
        if c in r or r in c:
            return 0.95

        # 图中查找
        if c not in self._nodes or r not in self._nodes:
            return 0.0

        # Hop-1 邻居
        if self.graph.has_edge(c, r):
            edge_weight = self.graph[c][r]["weight"]
            return edge_weight * self.HOP1_DISCOUNT

        # Hop-2 邻居（通过公共邻居）
        c_neighbors = set(self.graph.neighbors(c))
        r_neighbors = set(self.graph.neighbors(r))
        common = c_neighbors & r_neighbors
        if common:
            # 取最强路径
            best = max(
                self.graph[c][m]["weight"] * self.graph[m][r]["weight"]
                for m in common
            )
            return best * self.HOP2_DISCOUNT

        return 0.0
    
    def _match_skill_set(
        self,
        candidate_skills: list[str],
        required_skills: list[str],
        skill_weight: float = 1.0,
    ) -> tuple[float, list[dict]]:
        """
        候选人技能集 vs 要求技能集：
        贪心匹配，每个要求技能找候选人中最高分
        """
        if not required_skills:
            return 1.0, []

        details = []
        total_score = 0.0

        for req in required_skills:
            best_score = 0.0
            best_match = None
            for cand in candidate_skills:
                sim = self._skill_similarity(cand, req)
                if sim > best_score:
                    best_score = sim
                    best_match = cand

            total_score += best_score * skill_weight
            details.append({
                "required": req,
                "matched_with": best_match,
                "score": round(best_score, 3),
            })

        avg_score = total_score / len(required_skills)
        return avg_score, details
    
    def score(self, candidate: CandidateProfile, job: JobPosting) -> DimensionScore:
        # 必需技能 (权重 0.7) + 优选技能 (权重 0.3)
        required_score, req_details = self._match_skill_set(
            candidate.skills, job.required_skills, skill_weight=1.0
        )
        preferred_score, pref_details = self._match_skill_set(
            candidate.skills, job.preferred_skills, skill_weight=1.0
        )

        # 加权合并
        if job.preferred_skills:
            final_score = required_score * 0.7 + preferred_score * 0.3
        else:
            final_score = required_score

        final_score = max(0.0, min(1.0, final_score))

        return DimensionScore(
            score=final_score,
            weight=self.weight,
            weighted_score=final_score * self.weight,
            details={
                "required_skill_score": round(required_score, 3),
                "preferred_skill_score": round(preferred_score, 3),
                "required_details": req_details,
                "preferred_details": pref_details,
                "graph_nodes": self.graph.number_of_nodes(),
                "graph_edges": self.graph.number_of_edges(),
            },
        )