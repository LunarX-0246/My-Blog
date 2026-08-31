"""URL slug 生成工具：中文转拼音（文章 / 分类 / 标签共用）。"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session


def slugify(text: str, fallback: str = "item") -> str:
    """中文转拼音、ASCII 单词保留，其余字符转连字符；结果为空时用 fallback。"""
    try:
        from pypinyin import lazy_pinyin

        base = " ".join(lazy_pinyin(text))
    except ImportError:  # 极端情况：无 pypinyin 时退回原文
        base = text
    s = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")
    return s or fallback


def unique_slug(db: Session, model, base: str) -> str:
    """确保 slug 全站唯一；冲突时追加 -2、-3…。model 需含 id / slug 列。"""
    slug = base
    n = 2
    while db.scalar(select(model.id).where(model.slug == slug)):
        slug = f"{base}-{n}"
        n += 1
    return slug
