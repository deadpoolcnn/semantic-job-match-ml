# src/api/main.py

# ✅ 最优先：确保 NLTK 数据已下载
import src.core.nltk_init  # noqa: F401

import asyncio
import logging
import torch

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.routes import router, get_five_dim_scorer
from src.api.routes_v2 import router_v2

logger = logging.getLogger(__name__)

# Prevent PyTorch OMP cross-thread deadlock when running encode() in ThreadPoolExecutor
torch.set_num_threads(1)

app = FastAPI(
    title="Semantic Job Matcher API",
    description="ML service for semantic resume–job matching with explanations.",
    version="0.1.0"
)

# CORS：只允许前端域名访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://analysis.fuppuccino.vip",
        "http://localhost:5173",             # 本地开发环境
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载路由
app.include_router(router)
app.include_router(router_v2)


@app.on_event("startup")
async def _prewarm():
    """
    Pre-warm FiveDimScorer (PyTorch models) in executor thread.
    Pre-warm JD cache (Moonshot LLM analysis) concurrently.
    Both run at startup so the first real request pays zero cold-start cost.
    """
    from src.agents.job_analyzer_agent import prewarm as prewarm_jd_cache

    logger.info("[startup] Pre-warming FiveDimScorer + JD cache...")
    loop = asyncio.get_event_loop()
    await asyncio.gather(
        loop.run_in_executor(None, get_five_dim_scorer),
        prewarm_jd_cache(),
    )
    logger.info("[startup] Pre-warm complete.")


@app.get("/")
def root():
    return {"message": "Semantic Job Matcher ML API is running", "version": "0.1.0"}

@app.get("/health")
def health():
    return {"status": "healthy"}
