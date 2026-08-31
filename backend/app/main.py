"""FastAPI 应用入口。

职责：
- 创建 FastAPI 实例，挂载各业务路由，注册统一错误处理。
- 提供健康检查接口（阶段 0 验收点：``GET /api/health`` 返回 200）。
- 后续在启动时做索引自检（FR-IDX-10）、恢复索引任务队列（技术方案 §7）。

依赖方向：main → api → services → rag。main 只做装配，不写业务。
"""
from __future__ import annotations

from fastapi import FastAPI

from app.api import admin, auth, images, posts, taxonomy
from app.errors import register_exception_handlers

app = FastAPI(
    title="My Blog API",
    description="个人技术博客与 RAG 知识库问答系统后端",
    version="0.1.0",
)

register_exception_handlers(app)

app.include_router(auth.router)
app.include_router(posts.router)
app.include_router(admin.router)
app.include_router(taxonomy.router)
app.include_router(images.router)


@app.get("/api/health", tags=["system"])
def health() -> dict[str, str]:
    """健康检查。供本机自验与容器 healthcheck 使用。"""
    return {"status": "ok"}


# 各业务路由在对应阶段开发时逐个挂载（posts / docs / ask / admin）。
# 见 api/ 目录下的 router 定义，保持这里只 import 不写逻辑。
