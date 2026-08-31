"""元数据工具（RAG-DEC-03 演进，二期 T5-1~T5-3）。

list_posts / get_post_outline / get_post_section 返回的是「事实」——标题、日期、数量、
目录、章节正文。模型只能陈述这些事实，不得据此发挥或补充通用知识（红线 N1）。
"""
from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category, Chunk, Post, PostStatus, SourceType, Tag, post_tags
from app.rag.markdown import build_toc


def _parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.strptime(s, "%Y-%m-%d").date()
        return datetime.combine(d, time.min)
    except (ValueError, TypeError):
        return None


def list_posts(
    db: Session,
    *,
    tag: str | None = None,
    category: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 20,
) -> str:
    """列出已发布文章清单：标题、slug、发布日期、标签。"""
    stmt = select(Post).where(Post.status == PostStatus.published)
    if tag:
        tag_id = db.scalar(select(Tag.id).where(Tag.slug == tag))
        if tag_id is None:
            return "没有符合条件的文章。"
        post_ids = db.scalars(select(post_tags.c.post_id).where(post_tags.c.tag_id == tag_id)).all()
        stmt = stmt.where(Post.id.in_(post_ids))
    if category:
        cat_id = db.scalar(select(Category.id).where(Category.slug == category))
        stmt = stmt.where(Post.category_id == cat_id)
    if date_from:
        df = _parse_date(date_from)
        if df:
            stmt = stmt.where(Post.published_at >= df)
    if date_to:
        dt = _parse_date(date_to)
        if dt:
            stmt = stmt.where(Post.published_at < dt)

    posts = db.scalars(stmt.order_by(Post.published_at.desc()).limit(limit)).all()
    if not posts:
        return "没有符合条件的文章。"
    lines = [f"共 {len(posts)} 篇："]
    for p in posts:
        tags = "、".join(t.name for t in p.tags) or "无标签"
        pub = p.published_at.strftime("%Y-%m-%d") if p.published_at else "未发布"
        lines.append(f"- 《{p.title}》 /{p.slug}/ 发布于 {pub} 标签：{tags}")
    return "\n".join(lines)


def get_post_outline(db: Session, *, slug: str) -> str:
    """返回某篇已发布文章的标题目录（含锚点）。"""
    post = db.scalar(select(Post).where(Post.slug == slug, Post.status == PostStatus.published))
    if not post:
        return "文章不存在或未发布。"
    headings = build_toc(post.content_md)
    if not headings:
        return f"《{post.title}》没有标题结构。"
    lines = [f"《{post.title}》目录："]
    for h in headings:
        indent = "  " * (h.level - 1)
        lines.append(f"{indent}{h.text}（锚点 {h.anchor}）")
    return "\n".join(lines)


def get_post_section(db: Session, *, slug: str, anchor: str) -> str:
    """返回某篇已发布文章某一节（按锚点）的完整正文。"""
    post = db.scalar(select(Post).where(Post.slug == slug, Post.status == PostStatus.published))
    if not post:
        return "文章不存在或未发布。"
    chunk = db.scalar(
        select(Chunk)
        .where(
            Chunk.src_type == SourceType.post,
            Chunk.src_id == post.id,
            Chunk.anchor == anchor,
        )
        .order_by(Chunk.seq)
        .limit(1)
    )
    if not chunk:
        return f"未找到锚点为「{anchor}」的章节，请用 get_post_outline 确认锚点。"
    return chunk.content
