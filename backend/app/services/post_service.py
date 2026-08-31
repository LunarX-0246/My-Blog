"""文章业务逻辑（FR-POST-08~13）。

职责：文章 CRUD、slug 唯一性、草稿/发布状态流转、阅读时长估算。
删除（含级联清理块与配图，D1）在 T1-7 单独实现，避免与索引管线耦合。

依赖方向：services → models / schemas，不得反向。
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.errors import ApiError
from app.models import Category, Chunk, IndexStatus, Post, PostStatus, SourceType, Tag
from app.schemas import PostDetail, PostListItem, PostWrite

# 中文阅读速度约 300~400 字/分钟，取 300 做保守估算（FR-POST 阅读时长）
_CHARS_PER_MINUTE = 300


def _now() -> datetime:
    return datetime.now(timezone.utc)


def slugify_title(title: str) -> str:
    """从标题生成 URL slug：中文转拼音，ASCII 单词保留，其余字符转连字符。"""
    try:
        from pypinyin import lazy_pinyin

        base = " ".join(lazy_pinyin(title))
    except ImportError:  # 极端情况：无 pypinyin 时退回原标题
        base = title
    slug = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")
    return slug or "post"


def _unique_slug(db: Session, base: str) -> str:
    """确保 slug 全站唯一；冲突时追加 -2、-3…"""
    slug = base
    n = 2
    while db.scalar(select(Post.id).where(Post.slug == slug)):
        slug = f"{base}-{n}"
        n += 1
    return slug


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


def create_post(db: Session, data: PostWrite) -> Post:
    # 显式给出的 slug 冲突则报错（全站唯一）；未给出则由标题自动生成并去重
    if data.slug:
        slug = data.slug.strip()
        if db.scalar(select(Post.id).where(Post.slug == slug)):
            raise ApiError(409, "slug_conflict", "该 URL 别名已被占用")
    else:
        slug = _unique_slug(db, slugify_title(data.title) or "post")
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
