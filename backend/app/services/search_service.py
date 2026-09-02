"""全站搜索（FR-SEARCH-01~05）。

- 复用 rag/bm25.py 的 BM25 实现（N5：不另起一套检索）
- 只覆盖已发布内容（N6：草稿不可被搜到）
- 结果含关键词高亮的匹配片段、来源类型、日期、链接
- BM25 索引进程内缓存，内容变更时失效（B5）；与块级 BM25 缓存独立——语料粒度不同（整篇 vs 块）
"""
from __future__ import annotations

import re
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


# 承载固定页面的保留 slug，其规范地址不是 /posts/<slug>。
# 「关于」页正文是一篇 slug 为 about 的文章（FR-VIEW-24），
# 搜到它时要跳去 /about，而不是 /posts/about —— 后者能打开，但是同一份内容的第二个地址。
_RESERVED_URL = {"about": "/about"}


def _post_url(slug: str) -> str:
    return _RESERVED_URL.get(slug, f"/posts/{slug}")


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
                _post_url(p.slug),
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


def _plain(text: str) -> str:
    """把 Markdown 记号抹掉，只留可读文字，供搜索片段展示（FR-SEARCH-02）。

    片段是从正文中间随手截的一段，很容易切进代码围栏、标题井号、列表符号里，
    直接显示出来是 "## 纯向量检索 ```python" 这种夹生文本。
    这里只做最轻的清理：去围栏、去行首记号、去强调符号，不做完整的 Markdown 解析
    —— 片段只需要看得懂，不需要还原排版。
    """
    text = re.sub(r"```[^\n]*", "", text)          # 代码围栏
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)   # 标题井号
    text = re.sub(r"^\s{0,3}[-*+>]\s+", "", text, flags=re.M)   # 列表 / 引用
    text = re.sub(r"^\s*\|", "", text, flags=re.M)              # 表格行首竖线
    text = text.replace("**", "").replace("`", "")
    return re.sub(r"\n{2,}", "\n", text).strip()


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
    """把命中的查询词包成 <mark>（FR-SEARCH-02）。

    ★ 单趟正则替换，不逐词 str.replace。逐词替换有两个坑：
      1. 第一轮插入的 `<mark>` 会成为后续词的匹配对象 —— 搜 "mark" 时，
         第二个词会把标签本身again包一层，输出的 HTML 结构就烂了；
      2. 词之间互相嵌套（如同时命中「检索」和「混合检索」）会重复包裹。
      按长度降序放进一个 alternation 里一次扫完，长词优先匹配，两个坑都不存在。

    这里不再限制词长：terms 已经在 search() 里筛过一遍，
    只有整个查询都是单字时才会保留单字词 —— 那种情况下就该照常高亮，
    否则会出现「搜得到、但片段里一个高亮都没有」的怪结果。
    """
    words = [t for t in sorted(set(terms), key=len, reverse=True) if t]
    if not words:
        return text
    pattern = re.compile("|".join(re.escape(w) for w in words))
    return pattern.sub(lambda m: f"<mark>{m.group(0)}</mark>", text)


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

    # 用于「高亮 / 判定是否真的命中」的词：只取长度 >= 2 的。
    # 中文分词会切出「的」「不」「了」这类单字，它们几乎出现在每篇内容里，
    # 拿来高亮毫无意义。查询整个都是单字时（如搜「块」）就退回用全部词，
    # 否则会一条都筛不出来。
    all_tokens = tokenize(query)
    terms = [t for t in all_tokens if len(t) >= 2] or all_tokens

    results: list[dict] = []
    # 多取候选再按 src_type/tag 过滤，避免过滤后不足 limit（B5：缓存全量语料，过滤在结果期）
    for idx, _score in bm25.search(query, limit * 3):
        item = items[idx]
        if src_type and item.src_type != src_type:
            continue
        if tag and tag not in item.tags:
            continue
        # ★ 必须真的含有某个查询词才算命中。
        #   BM25 的 idf 平滑保证了「的」「不」这种词权重极低，但**不为零**，
        #   于是任何中文查询都能给每一篇内容凑出一个正分 —— 搜「不存在的词xyz」
        #   会把全站内容原样列出来，每张卡片还没有任何高亮片段（违反 FR-SEARCH-02），
        #   而 FR-SEARCH-04「无结果时引导去 AI 问答」那条分支永远走不到。
        if not any(t in item.text for t in terms):
            continue
        body = item.text[len(item.title) :].strip("\n")
        excerpt = _highlight(_excerpt(_plain(body), terms), terms)
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
