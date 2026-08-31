"""FastAPI 应用入口。

职责：
- 创建 FastAPI 实例，挂载各业务路由，注册统一错误处理。
- 启动时做向量模型自检（FR-IDX-10）、恢复索引任务队列（技术方案 §7）。
- 提供健康检查接口。

依赖方向：main → api → services → rag。main 只做装配，不写业务。
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import admin, ask, auth, docs, images, posts, taxonomy
from app.config import settings
from app.db import SessionLocal
from app.errors import register_exception_handlers
from app.models import Setting
from app.services import index_service


def _check_embedding_model() -> None:
    """启动自检：校验索引的向量模型/维度与当前配置一致（FR-IDX-10）。

    首次启动（settings 无记录）时写入当前配置；之后不一致则抛错拒绝启动，
    不允许带着错误的索引静默运行。
    """
    current = {"model": settings.embedding_model, "dim": settings.embedding_dim}
    with SessionLocal() as db:
        row = db.get(Setting, "embedding_model")
        if row is None:
            db.add(Setting(key="embedding_model", value=current))
            db.commit()
        elif row.value != current:
            raise RuntimeError(
                f"向量模型配置与索引不一致：索引={row.value}，当前={current}。"
                "请全量重建索引或恢复一致配置。"
            )


@asynccontextmanager
async def lifespan(_: FastAPI):
    _check_embedding_model()
    index_service.start_worker()
    yield


app = FastAPI(
    title="My Blog API",
    description="个人技术博客与 RAG 知识库问答系统后端",
    version="0.1.0",
    lifespan=lifespan,
)

register_exception_handlers(app)

app.include_router(auth.router)
app.include_router(posts.router)
app.include_router(admin.router)
app.include_router(taxonomy.router)
app.include_router(images.router)
app.include_router(docs.router)
app.include_router(ask.router)


@app.get("/api/health", tags=["system"])
def health() -> dict[str, str]:
    """健康检查。供本机自验与容器 healthcheck 使用。"""
    return {"status": "ok"}
