"""分类与标签（FR-POST-16：编辑界面内可直接新建，无需单独管理页）。

创建按名称 get-or-create：同名返回已有，否则新建并生成 slug。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import Category, Tag
from app.services.slug import slugify, unique_slug


def list_categories(db: Session) -> list[Category]:
    return list(db.scalars(select(Category).order_by(Category.name)).all())


def list_tags(db: Session) -> list[Tag]:
    return list(db.scalars(select(Tag).order_by(Tag.name)).all())


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
