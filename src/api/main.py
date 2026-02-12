# src/api/main.py

# ✅ 最优先：确保 NLTK 数据已下载
import src.core.nltk_init  # noqa: F401

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.routes import router  # 导入路由

app = FastAPI(
    title="Semantic Job Matcher API",
    description="ML service for semantic resume–job matching with explanations.",
    version="0.1.0"
)

# CORS：如果你未来前端是 React，先放开个宽松配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载路由
app.include_router(router)

@app.get("/")
def root():
    return {"message": "Semantic Job Matcher ML API is running", "version": "0.1.0"}

@app.get("/health")
def health():
    return {"status": "healthy"}
