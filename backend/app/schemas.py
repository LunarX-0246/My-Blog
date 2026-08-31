"""请求 / 响应 Pydantic 模型（技术方案 §5 API 契约）。

与前端 ``lib/types.ts`` 对齐；字段命名用 snake_case，序列化按此输出。
后续阶段（文章、文档、问答）在此追加对应模型。
"""
from __future__ import annotations

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class MeResponse(BaseModel):
    authenticated: bool
    username: str | None = None
