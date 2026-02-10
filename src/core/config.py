from functools import lru_cache
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
import os

@lru_cache(maxsize=1) # 使用 LRU 缓存装饰器，确保全局单例
def load_env() -> None:
    """
    加载环境变量，优先从 .env 文件加载，如果环境变量已设置则使用现有值
    """
    root = Path(__file__).resolve().parents[2] # 获取项目根目录
    env_path = root / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path) # 从 .env 文件加载环境变量

@lru_cache(maxsize=1) # 使用 LRU 缓存装饰器，确保全局单例
def get_gemini_api_key() -> str:
    """
    获取 Gemini API Key，优先从环境变量获取，如果未设置则返回 None
    """
    load_env() # 确保环境变量已加载
    key = os.getenv("GEMINI_API_KEY", "") # 从环境变量获取 API Key，默认为空字符串
    if not key:
        raise ValueError("GEMINI_API_KEY is not set in the environment variables.")
    return key

@lru_cache(maxsize=1) # 使用 LRU 缓存装饰器，确保全局单例
def get_gemini_model() -> str:
    """
    获取 Gemini 模型名称，优先从环境变量获取，如果未设置则返回默认值 "gemini-1.5-pro"
    """
    load_env() # 确保环境变量已加载
    model = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview") # 从环境变量获取模型名称，默认为 "gemini-3-flash-preview"
    return model