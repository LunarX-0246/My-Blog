"""文章业务逻辑（FR-POST-08~13）。

职责：文章 CRUD、slug 唯一性、草稿/发布状态流转、阅读时长估算。
删除（含级联清理块与配图，D1）在 T1-7 单独实现，避免与索引管线耦合。

依赖方向：services → models / schemas，不得反向。
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session, selectinload

from app.errors import ApiError
from app.models import (
    Category,
    Chunk,
    Image,
    IndexStatus,
    Post,
    PostStatus,
    SourceType,
    Tag,
)
from app.rag import llm
from app.schemas import PostDetail, PostListItem, PostWrite
from app.services.slug import slugify, unique_slug

# 中文阅读速度约 300~400 字/分钟，取 300 做保守估算（FR-POST 阅读时长）
_CHARS_PER_MINUTE = 300


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _read_minutes(content_md: str) -> int:
    return max(1, math.ceil(len(content_md) / _CHARS_PER_MINUTE))


def _load_full(db: Session, post_id: int) -> Post:
    """带 category / tags 预加载重新取回，避免返回半加载对象（关系懒加载踩坑）。"""
    return db.execute(
        select(Post)
        .options(selectinload(Post.category), selectinload(Post.tags))
        .where(Post.id == post_id)
    ).scalar_one()


def _assign_tags(db: Session, post: Post, tag_ids: list[int]) -> None:
    if tag_ids:
        post.tags = list(db.scalars(select(Tag).where(Tag.id.in_(tag_ids))).all())
    else:
        post.tags = []


# 正文里引用的图片 URL 形如 /api/images/<stored_name>
_IMAGE_URL_RE = re.compile(r"/api/images/([a-zA-Z0-9._-]+)")


def _associate_images(db: Session, post: Post) -> None:
    """把正文引用的图片关联到文章（post_id），供删除时级联清理（D1）。"""
    names = _IMAGE_URL_RE.findall(post.content_md)
    if names:
        db.execute(
            update(Image).where(Image.stored_name.in_(names)).values(post_id=post.id)
        )


def create_post(db: Session, data: PostWrite) -> Post:
    # 显式给出的 slug 冲突则报错（全站唯一）；未给出则由标题自动生成并去重
    if data.slug:
        slug = data.slug.strip()
        if db.scalar(select(Post.id).where(Post.slug == slug)):
            raise ApiError(409, "slug_conflict", "该 URL 别名已被占用")
    else:
        slug = unique_slug(db, Post, slugify(data.title, "post"))
    post = Post(
        title=data.title.strip(),
        slug=slug,
        summary=data.summary,
        content_md=data.content_md,
        category_id=data.category_id,
        is_featured=data.is_featured,
        status=PostStatus.draft,          # 新建一律为草稿，发布走 publish
        read_minutes=_read_minutes(data.content_md),
        idx_status=IndexStatus.pending,
    )
    _assign_tags(db, post, data.tag_ids)
    db.add(post)
    db.flush()  # 先拿到 post.id，供图片关联使用
    _associate_images(db, post)
    db.commit()
    return _load_full(db, post.id)


def update_post(db: Session, post: Post, data: PostWrite) -> Post:
    if data.slug and data.slug != post.slug:
        if db.scalar(select(Post.id).where(Post.slug == data.slug, Post.id != post.id)):
            raise ApiError(409, "slug_conflict", "该 URL 别名已被占用")
        post.slug = data.slug
    post.title = data.title.strip()
    post.summary = data.summary
    post.content_md = data.content_md
    post.category_id = data.category_id
    post.is_featured = data.is_featured
    post.read_minutes = _read_minutes(data.content_md)
    _assign_tags(db, post, data.tag_ids)
    # 已发布文章保存即生效：更新 updated_at 并标记需重新索引（FR-POST-12）
    if post.status == PostStatus.published:
        post.updated_at = _now()
        post.idx_status = IndexStatus.pending
    _associate_images(db, post)
    db.commit()
    return _load_full(db, post.id)


def get_published_by_slug(db: Session, slug: str) -> Post:
    post = db.execute(
        select(Post)
        .options(selectinload(Post.category), selectinload(Post.tags))
        .where(Post.slug == slug, Post.status == PostStatus.published)
    ).scalar_one_or_none()
    if not post:
        raise ApiError(404, "not_found", "文章不存在")
    return post


def get_by_id(db: Session, post_id: int) -> Post:
    post = db.execute(
        select(Post)
        .options(selectinload(Post.category), selectinload(Post.tags))
        .where(Post.id == post_id)
    ).scalar_one_or_none()
    if not post:
        raise ApiError(404, "not_found", "文章不存在")
    return post


def list_published(
    db: Session,
    category_slug: str | None = None,
    tag_slug: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Post], int]:
    count_stmt = select(func.count(func.distinct(Post.id))).where(
        Post.status == PostStatus.published
    )
    stmt = (
        select(Post)
        .options(selectinload(Post.category), selectinload(Post.tags))
        .where(Post.status == PostStatus.published)
    )
    if category_slug:
        count_stmt = count_stmt.join(Post.category).where(Category.slug == category_slug)
        stmt = stmt.join(Post.category).where(Category.slug == category_slug)
    if tag_slug:
        count_stmt = count_stmt.join(Post.tags).where(Tag.slug == tag_slug)
        stmt = stmt.join(Post.tags).where(Tag.slug == tag_slug)

    total = db.scalar(count_stmt) or 0
    items = db.scalars(
        stmt.order_by(Post.published_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(items), total


def list_admin(db: Session, status: PostStatus | None = None) -> list[Post]:
    stmt = select(Post).options(selectinload(Post.category), selectinload(Post.tags))
    if status is not None:
        stmt = stmt.where(Post.status == status)
    return list(db.scalars(stmt.order_by(Post.updated_at.desc())).all())


def publish(db: Session, post: Post) -> Post:
    if post.status != PostStatus.published:
        post.status = PostStatus.published
        if post.published_at is None:
            post.published_at = _now()   # 首次发布记录时间
        post.updated_at = _now()
        post.idx_status = IndexStatus.pending  # 触发索引（3a 的 worker 消费）
        db.commit()
    return _load_full(db, post.id)


def unpublish(db: Session, post: Post) -> Post:
    if post.status != PostStatus.draft:
        post.status = PostStatus.draft
        # 撤回立即从索引移除块（FR-POST-13），不等异步 worker
        db.execute(
            delete(Chunk).where(
                Chunk.src_type == SourceType.post, Chunk.src_id == post.id
            )
        )
        post.idx_status = IndexStatus.pending
        db.commit()
    return _load_full(db, post.id)


def to_detail(post: Post) -> PostDetail:
    """把 ORM 对象组装为详情响应（含正文、分类/标签 id；TOC 由 T1-8 填充）。"""
    return PostDetail(
        **PostListItem.model_validate(post).model_dump(),
        content_md=post.content_md,
        category_id=post.category_id,
        tag_ids=[t.id for t in post.tags],
        toc=[],
    )


# 摘要生成：截断超长正文，避免 token 浪费
_SUMMARY_MAX_CHARS = 6000
_SUMMARY_PROMPT = (
    "你是博主的内容助手。请根据下面这篇文章的正文，用一句话（不超过 60 字）"
    "概括其核心内容。直接输出摘要，不要任何前缀、解释或引号。\n\n正文：\n{content}"
)


def generate_summary(db: Session, post: Post) -> str:
    """AI 生成摘要（FR-POST-11）。失败转成面向用户的中文提示，不暴露堆栈。"""
    if not post.content_md.strip():
        raise ApiError(400, "empty_content", "正文为空，无法生成摘要")
    prompt = _SUMMARY_PROMPT.format(content=post.content_md[:_SUMMARY_MAX_CHARS])
    try:
        summary = llm.chat([{"role": "user", "content": prompt}], max_tokens=128)
    except Exception:
        raise ApiError(502, "llm_error", "摘要生成失败，请稍后再试")
    summary = summary.strip().strip('"“”')
    if not summary:
        raise ApiError(502, "llm_error", "摘要生成失败，请稍后再试")
    return summary
