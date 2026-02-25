# scripts/run_server.py

import sys
import os
# 将项目根目录加入 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uvicorn
from src.api.main import app


if __name__ == "__main__":
    uvicorn.run(
        "src.api.main:app",  # 模块路径
        host="127.0.0.1",
        port=8000,
        reload=True,        # dev mode 自动重载
    )
