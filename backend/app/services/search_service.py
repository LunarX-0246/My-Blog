"""全站搜索（FR-SEARCH-01~05）。

- 复用 rag/bm25.py 的 BM25 实现（N5：不另起一套检索）
- 只覆盖已发布内容（N6：草稿不可被搜到）
- 结果含关键词高亮的匹配片段、来源类型、日期、链接
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document, Post, PostStatus
from app.rag.bm25 import BM25, tokenize


@dataclass
class _Item:
    src_type: str
    title: str
    text: str
    date: datetime | None
    url: str


def _excerpt(text: str, terms: list[str], width: int = 120) -> str:
    """取第一个命中词附近的一段作为匹配片段。"""
    pos = -1
    for t in terms:
        i = text.find(t)
        if i >= 0 and (pos < 0 or i < pos):
            pos = i
    if pos < 0:
        return text[:width]
    start = max(0, pos - width // 3)
    return text[start : start + width]


def _highlight(text: str, terms: list[str]) -> str:
    """把命中的查询词包成 <mark>（长词优先，避免重复包裹）。"""
    for t in sorted(set(terms), key=len, reverse=True):
        if len(t) >= 2:
            text = text.replace(t, f"<mark>{t}</mark>")
    return text


def search(
    db: Session,
    query: str,
    *,
    src_type: str | None = None,
    tag: str | None = None,
    limit: int = 20,
) -> list[dict]:
    query = query.strip()
    if not query:
        return []

    # 只搜已发布内容（N6）
    posts = db.scalars(select(Post).where(Post.status == PostStatus.published)).all()
    docs = db.scalars(select(Document)).all()

    items: list[_Item] = []
    for p in posts:
        if src_type and src_type != "post":
            continue
        if tag and not any(t.slug == tag for t in p.tags):
            continue
        items.append(
            _Item("post", p.title, p.title + "\n" + p.content_md, p.published_at, f"/posts/{p.slug}")
        )
    for d in docs:
        if src_type and src_type != "document":
            continue
        if tag and not any(t.slug == tag for t in d.tags):
            continue
        items.append(
            _Item("document", d.title, d.title + "\n" + d.parsed_text, d.uploaded_at, f"/docs/{d.id}")
        )

    if not items:
        return []

    # 复用 BM25（N5）
    bm25 = BM25([i.text for i in items])
    terms = [t for t in tokenize(query) if len(t) >= 2]

    results: list[dict] = []
    for idx, _score in bm25.search(query, limit):
        item = items[idx]
        body = item.text[len(item.title) :].strip("\n")
        excerpt = _highlight(_excerpt(body, terms), terms)
        results.append(
            {
                "type": item.src_type,
                "title": item.title,
                "excerpt": excerpt,
                "date": item.date,
                "url": item.url,
            }
        )
    return results
