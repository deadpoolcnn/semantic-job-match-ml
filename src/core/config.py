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

@lru_cache(maxsize=1)
def get_gemini_api_key() -> str:
    load_env()
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        raise ValueError("GEMINI_API_KEY is not set in the environment variables.")
    return key

@lru_cache(maxsize=1)
def get_gemini_model() -> str:
    load_env()
    return os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

@lru_cache(maxsize=1)
def get_moonshot_api_key() -> str:
    load_env()
    key = os.getenv("MOONSHOT_API_KEY", "").strip()
    if not key:
        raise ValueError("MOONSHOT_API_KEY is not set in the environment variables.")
    return key

@lru_cache(maxsize=1)
def get_moonshot_model() -> str:
    load_env()
    return os.getenv("MOONSHOT_MODEL", "kimi-k2.5")