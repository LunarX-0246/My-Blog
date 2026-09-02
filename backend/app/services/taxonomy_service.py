"""分类与标签（FR-POST-16：编辑界面内可直接新建，无需单独管理页）。

创建按名称 get-or-create：同名返回已有，否则新建并生成 slug。
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import Category, Post, PostStatus, Tag, document_tags, post_tags
from app.services.slug import slugify, unique_slug


def list_categories(db: Session) -> list[Category]:
    return list(db.scalars(select(Category).order_by(Category.name)).all())


def list_tags(db: Session) -> list[Tag]:
    return list(db.scalars(select(Tag).order_by(Tag.name)).all())


def list_hot_tags(db: Session, limit: int = 10) -> list[tuple[Tag, int]]:
    """热门标签：按关联内容数量（文章 + 文档）降序（FR-HOME-03）。"""
    # ★ 只数已发布的文章。草稿对访客不可见，标签页也不会列出它，
    #   若算进热度计数，首页标签上的数字就会大于点进去看到的条数。
    post_counts = (
        select(post_tags.c.tag_id, func.count().label("c"))
        .join(Post, Post.id == post_tags.c.post_id)
        .where(Post.status == PostStatus.published)
        .group_by(post_tags.c.tag_id)
    )
    doc_counts = select(document_tags.c.tag_id, func.count().label("c")).group_by(
        document_tags.c.tag_id
    )
    unioned = post_counts.union_all(doc_counts).subquery()
    grouped = (
        select(unioned.c.tag_id, func.sum(unioned.c.c).label("total"))
        .group_by(unioned.c.tag_id)
        .subquery()
    )
    rows = db.execute(
        select(Tag, grouped.c.total)
        .join(grouped, Tag.id == grouped.c.tag_id)
        .order_by(grouped.c.total.desc(), Tag.name)
        .limit(limit)
    ).all()
    return [(tag, int(total)) for tag, total in rows]


def create_category(db: Session, name: str) -> Category:
    name = name.strip()
    if not name:
        raise ApiError(400, "bad_request", "分类名称不能为空")
    existing = db.scalar(select(Category).where(Category.name == name))
    if existing:
        return existing
    category = Category(name=name, slug=unique_slug(db, Category, slugify(name, "category")))
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


def create_tag(db: Session, name: str) -> Tag:
    name = name.strip()
    if not name:
        raise ApiError(400, "bad_request", "标签名称不能为空")
    existing = db.scalar(select(Tag).where(Tag.name == name))
    if existing:
        return existing
    tag = Tag(name=name, slug=unique_slug(db, Tag, slugify(name, "tag")))
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag
