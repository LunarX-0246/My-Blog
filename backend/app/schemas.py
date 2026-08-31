"""请求 / 响应 Pydantic 模型（技术方案 §5 API 契约）。

与前端 ``lib/types.ts`` 对齐；字段用 snake_case，序列化按此输出。
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ── 认证 ────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class MeResponse(BaseModel):
    authenticated: bool
    username: str | None = None


# ── 分类 / 标签 ─────────────────────────────────────────

class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str


class TagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str


class CategoryCreate(BaseModel):
    name: str


class TagCreate(BaseModel):
    name: str


# ── 文章 ───────────────────────────────────────────────

class PostWrite(BaseModel):
    """新建 / 保存文章共用的写入字段。状态只通过 publish / unpublish 变更。"""

    title: str
    slug: str | None = None
    summary: str = ""
    content_md: str = ""
    category_id: int | None = None
    tag_ids: list[int] = Field(default_factory=list)
    is_featured: bool = False


class TocItem(BaseModel):
    level: int
    text: str
    anchor: str


class PostListItem(BaseModel):
    """列表项（不含正文），公开与管理端共用。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    slug: str
    summary: str
    status: str
    is_featured: bool
    read_minutes: int
    view_count: int
    idx_status: str
    idx_error: str | None = None
    category: CategoryOut | None = None
    tags: list[TagOut] = Field(default_factory=list)
    published_at: datetime | None = None
    updated_at: datetime
    created_at: datetime


class PostDetail(PostListItem):
    """详情（含正文、分类/标签 id、TOC）。"""

    content_md: str
    category_id: int | None = None
    tag_ids: list[int] = Field(default_factory=list)
    toc: list[TocItem] = Field(default_factory=list)


class PostListResponse(BaseModel):
    items: list[PostListItem]
    total: int
