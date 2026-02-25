from typing import List
# 文本转化为向量的工具类，使用 SentenceTransformer
from sentence_transformers import SentenceTransformer
import numpy as np
# 自动缓存模型加载结果，避免重复加载
from functools import lru_cache

# 模型名称，可以根据需要替换为其他 SentenceTransformer 模型
# 模型为通用语义模型，不理解招聘领域特定语义导致匹配效果不好时，可以考虑换成在招聘领域微调过的模型（如果有的话）
# MODEL_NAME = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2" # 这个模型支持多语言，适合中文文本编码
MODEL_NAME = "all-mpnet-base-v2" # 这个模型在英文文本上表现更好，如果主要处理英文简历和岗位描述，可以使用这个模型

@lru_cache(maxsize=1)
def get_model() -> SentenceTransformer:
    """
    获取 SentenceTransformer 模型实例，使用 LRU 缓存避免重复加载,单例模式
    """
    model = SentenceTransformer(MODEL_NAME)
    return model

def encode_texts(texts: List[str]) -> np.ndarray:
    """
    将文本列表编码为向量数组,返回 shape = (N, D) 的 numpy 数组（默认 768 维）
    """
    model = get_model()
    embeddings = model.encode(
        texts, 
        convert_to_numpy=True,
        show_progress_bar=False,
        batch_size=32
    )
    return embeddings

def encode_text_for_search(text: str) -> np.ndarray:
    """
    为搜索查询编码单个文本（简历）
    """
    return encode_texts([text])

def encode_texts_for_indexing(texts: List[str]) -> np.ndarray:
    """
    为索引构建编码多个文本（职位描述）
    """
    return encode_texts(texts)