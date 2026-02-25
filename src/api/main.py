# src/api/main.py

# ✅ 最优先：确保 NLTK 数据已下载
import src.core.nltk_init  # noqa: F401

import asyncio
import logging
import torch

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.routes import router, get_five_dim_scorer  # 导入路由

logger = logging.getLogger(__name__)

# Prevent PyTorch OMP cross-thread deadlock when running encode() in ThreadPoolExecutor
torch.set_num_threads(1)

app = FastAPI(
    title="Semantic Job Matcher API",
    description="ML service for semantic resume–job matching with explanations.",
    version="0.1.0"
)

# CORS：如果你未来前端是 React，先放开个宽松配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载路由
app.include_router(router)


@app.on_event("startup")
async def _prewarm_scorer():
    """
    Pre-warm FiveDimScorer in a ThreadPoolExecutor thread at startup.
    This ensures PyTorch model weights AND OMP threads are both initialized
    inside a worker thread — matching the thread where score_batch() will run.
    Avoids cross-thread OMP deadlock that occurs with lazy init in the event loop.
    """
    logger.info("[startup] Pre-warming FiveDimScorer in executor thread...")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, get_five_dim_scorer)
    logger.info("[startup] FiveDimScorer pre-warm complete.")


@app.get("/")
def root():
    return {"message": "Semantic Job Matcher ML API is running", "version": "0.1.0"}

@app.get("/health")
def health():
    return {"status": "healthy"}
