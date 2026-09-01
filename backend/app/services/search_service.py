"""全站搜索（FR-SEARCH-01~05）。

- 复用 rag/bm25.py 的 BM25 实现（N5：不另起一套检索）
- 只覆盖已发布内容（N6：草稿不可被搜到）
- 结果含关键词高亮的匹配片段、来源类型、日期、链接
- BM25 索引进程内缓存，内容变更时失效（B5）；与块级 BM25 缓存独立——语料粒度不同（整篇 vs 块）
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Document, Post, PostStatus
from app.rag.bm25 import BM25, tokenize


@dataclass
class _Item:
    src_type: str
    title: str
    text: str
    date: datetime | None
    url: str
    tags: list[str]  # 标签 slug 列表，供按标签过滤（B5：过滤改为结果期进行）


# ── 搜索用 BM25 缓存（B5，复用一期 M1 模式）─────────────────────────
# 语料是整篇文章/整份文档，粒度与检索用的块级 BM25 不同，故单独缓存、单独失效，
# 不与 retriever.invalidate_bm25 的那份混用。
_search_lock = threading.Lock()
_search_cache: tuple[list[_Item], BM25] | None = None


def _build_items(db: Session) -> list[_Item]:
    """从已发布文章 + 全部文档构建整篇语料条目。"""
    posts = db.scalars(
        select(Post)
        .options(selectinload(Post.tags))
        .where(Post.status == PostStatus.published)
    ).all()
    docs = db.scalars(select(Document).options(selectinload(Document.tags))).all()
    items: list[_Item] = []
    for p in posts:
        items.append(
            _Item(
                "post",
                p.title,
                p.title + "\n" + p.content_md,
                p.published_at,
                f"/posts/{p.slug}",
                [t.slug for t in p.tags],
            )
        )
    for d in docs:
        items.append(
            _Item(
                "document",
                d.title,
                d.title + "\n" + d.parsed_text,
                d.uploaded_at,
                f"/docs/{d.id}",
                [t.slug for t in d.tags],
            )
        )
    return items


def _get_cached(db: Session) -> tuple[list[_Item], BM25]:
    """取搜索用 BM25（首次构建后缓存，之后每次请求只做一次毫秒级 search）。"""
    global _search_cache
    with _search_lock:
        if _search_cache is None:
            items = _build_items(db)
            _search_cache = (items, BM25([i.text for i in items]))
        return _search_cache


def invalidate() -> None:
    """内容变更时失效搜索用 BM25 缓存（由 post/doc/index_service 在变更点调用）。"""
    global _search_cache
    with _search_lock:
        _search_cache = None


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

    items, bm25 = _get_cached(db)
    if not items:
        return []

    terms = [t for t in tokenize(query) if len(t) >= 2]

    results: list[dict] = []
    # 多取候选再按 src_type/tag 过滤，避免过滤后不足 limit（B5：缓存全量语料，过滤在结果期）
    for idx, _score in bm25.search(query, limit * 3):
        item = items[idx]
        if src_type and item.src_type != src_type:
            continue
        if tag and tag not in item.tags:
            continue
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
        if len(results) >= limit:
            break
    return results
