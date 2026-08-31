"""混合检索（技术方案 §6.6，红线 R4）。

向量 + BM25 两路检索，RRF 融合排序。BM25 不可省略——技术内容里大量专有名词、
函数名、报错信息，纯语义检索容易失准，BM25 一击命中。

可独立运行自测：python -m app.rag.retriever --query "混合检索"
"""
from __future__ import annotations

import argparse
import logging
import threading
import time
from collections import defaultdict

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Chunk, Document, SourceType, document_tags, post_tags
from app.rag.bm25 import BM25
from app.rag.embedder import embed_one
from app.rag.store.base import ScoredChunk, SearchFilter, get_store

logger = logging.getLogger(__name__)


def _apply_filter(stmt, flt: SearchFilter | None):
    """给 chunks 查询应用范围过滤（与 pgvector_store 的过滤一致）。"""
    if not flt:
        return stmt
    if flt.src_types:
        stmt = stmt.where(
            Chunk.src_type.in_([SourceType.post if t == "post" else SourceType.document for t in flt.src_types])
        )
    if flt.src_id is not None:
        stmt = stmt.where(Chunk.src_id == flt.src_id)
    if flt.dir_prefix:
        doc_ids = select(Document.id).where(Document.dir_path.like(f"{flt.dir_prefix}%"))
        stmt = stmt.where(and_(Chunk.src_type == SourceType.document, Chunk.src_id.in_(doc_ids)))
    if flt.tag_ids:
        post_ids = select(post_tags.c.post_id).where(post_tags.c.tag_id.in_(flt.tag_ids))
        doc_ids = select(document_tags.c.document_id).where(document_tags.c.tag_id.in_(flt.tag_ids))
        stmt = stmt.where(
            or_(
                and_(Chunk.src_type == SourceType.post, Chunk.src_id.in_(post_ids)),
                and_(Chunk.src_type == SourceType.document, Chunk.src_id.in_(doc_ids)),
            )
        )
    return stmt


def load_chunks(db: Session, flt: SearchFilter | None = None) -> list[ScoredChunk]:
    """加载带过滤条件的全部块（供 BM25 建索引）。"""
    stmt = _apply_filter(select(Chunk), flt)
    rows = db.scalars(stmt).all()
    return [
        ScoredChunk(
            src_type=c.src_type.value,
            src_id=c.src_id,
            seq=c.seq,
            content=c.content,
            context_prefix=c.context_prefix,
            page_no=c.page_no,
            anchor=c.anchor,
            score=0.0,
        )
        for c in rows
    ]


def _key(c: ScoredChunk) -> tuple[str, int, int]:
    return (c.src_type, c.src_id, c.seq)


# ── BM25 索引缓存（M1）─────────────────────────────────────────
# 每次提问都全量重建 BM25 会威胁「首字 3 秒」；进程内缓存，索引任务完成时失效重建。
_bm25_lock = threading.Lock()
_bm25_cache: tuple[BM25, list[ScoredChunk]] | None = None


def _get_cached_bm25(db: Session) -> tuple[BM25, list[ScoredChunk]]:
    global _bm25_cache
    with _bm25_lock:
        if _bm25_cache is None:
            chunks = load_chunks(db)  # 全量块（无 flt）
            _bm25_cache = (BM25([c.content for c in chunks]), chunks)
        return _bm25_cache


def invalidate_bm25() -> None:
    """索引内容变化时失效缓存（由 index_service 调用）。"""
    global _bm25_cache
    with _bm25_lock:
        _bm25_cache = None


def _flt_src_ids(db: Session, flt: SearchFilter | None) -> set[tuple[str, int]] | None:
    """返回 flt 里 tag_ids / dir_prefix 允许的 (src_type, src_id) 集合；该维度不过滤返回 None。"""
    if not flt or (not flt.tag_ids and not flt.dir_prefix):
        return None
    src_ids: set[tuple[str, int]] | None = None
    if flt.tag_ids:
        post_ids = set(db.scalars(select(post_tags.c.post_id).where(post_tags.c.tag_id.in_(flt.tag_ids))).all())
        doc_ids = set(db.scalars(select(document_tags.c.document_id).where(document_tags.c.tag_id.in_(flt.tag_ids))).all())
        src_ids = {("post", i) for i in post_ids} | {("document", i) for i in doc_ids}
    if flt.dir_prefix:
        doc_ids = set(db.scalars(select(Document.id).where(Document.dir_path.like(f"{flt.dir_prefix}%"))).all())
        ids = {("document", i) for i in doc_ids}
        src_ids = src_ids & ids if src_ids is not None else ids
    return src_ids


def _match_flt(c: ScoredChunk, flt: SearchFilter | None, src_ids: set[tuple[str, int]] | None) -> bool:
    if not flt:
        return True
    if flt.src_types and c.src_type not in flt.src_types:
        return False
    if flt.src_id is not None and c.src_id != flt.src_id:
        return False
    if src_ids is not None and (c.src_type, c.src_id) not in src_ids:
        return False
    return True


def rrf_fusion(ranked_lists: list[list[ScoredChunk]], k: int, top_k: int) -> list[ScoredChunk]:
    """RRF 融合：score = Σ 1/(k + rank)，k 为常数。"""
    scores: dict[tuple, float] = defaultdict(float)
    items: dict[tuple, ScoredChunk] = {}
    for ranked in ranked_lists:
        for rank, item in enumerate(ranked):
            key = _key(item)
            scores[key] += 1.0 / (k + rank + 1)
            items[key] = item
    result = []
    for key, score in sorted(scores.items(), key=lambda x: -x[1])[:top_k]:
        item = items[key]
        item.score = round(score, 4)
        result.append(item)
    return result


def retrieve(
    db: Session,
    query: str,
    top_k: int | None = None,
    flt: SearchFilter | None = None,
) -> list[ScoredChunk]:
    """混合检索：向量 + BM25 + RRF 融合。"""
    top_k = top_k or settings.context_top_k

    # 1. 向量检索
    t_embed = time.monotonic()
    query_vec = embed_one(query)
    embed_ms = (time.monotonic() - t_embed) * 1000
    t_search = time.monotonic()
    vec_results = get_store().search(db, query_vec, settings.retrieve_top_k, flt)

    # 2. BM25 检索
    bm25_results: list[ScoredChunk] = []
    if flt and flt.src_id is not None:
        # 限定单篇（FR-ASK-14）：候选块少，直接在候选集上临时建 BM25（R2）。
        # 若走全局缓存的事后过滤，单篇里的精确术语可能排在全局前 N 名之外，BM25 空手而归。
        chunks = load_chunks(db, flt)
        bm25 = BM25([c.content for c in chunks])
        for i, score in bm25.search(query, settings.retrieve_top_k):
            c = chunks[i]
            bm25_results.append(
                ScoredChunk(
                    src_type=c.src_type, src_id=c.src_id, seq=c.seq, content=c.content,
                    context_prefix=c.context_prefix, page_no=c.page_no, anchor=c.anchor, score=score,
                )
            )
    else:
        # 全局缓存路径（M1）：命中缓存时每次只做一次毫秒级 search，事后按 flt 过滤
        bm25, all_chunks = _get_cached_bm25(db)
        src_ids = _flt_src_ids(db, flt)
        for i, score in bm25.search(query, settings.retrieve_top_k * 3):
            c = all_chunks[i]
            if not _match_flt(c, flt, src_ids):
                continue
            bm25_results.append(
                ScoredChunk(
                    src_type=c.src_type, src_id=c.src_id, seq=c.seq, content=c.content,
                    context_prefix=c.context_prefix, page_no=c.page_no, anchor=c.anchor, score=score,
                )
            )
            if len(bm25_results) >= settings.retrieve_top_k:
                break

    # 3. RRF 融合
    fused = rrf_fusion([vec_results, bm25_results], settings.rrf_k, top_k)
    search_ms = (time.monotonic() - t_search) * 1000
    logger.info("retrieve.timing embed=%.0fms search=%.0fms", embed_ms, search_ms)
    return fused


def _main() -> None:
    parser = argparse.ArgumentParser(description="命令行混合检索自测")
    parser.add_argument("--query", required=True, help="查询语句")
    parser.add_argument("--type", default=None, choices=["post", "document"], help="限定内容类型")
    parser.add_argument("--top-k", type=int, default=None)
    args = parser.parse_args()

    flt = SearchFilter(src_types=[args.type]) if args.type else None
    from app.db import SessionLocal

    with SessionLocal() as db:
        results = retrieve(db, args.query, top_k=args.top_k, flt=flt)

    print(f"查询：{args.query}　命中 {len(results)} 条")
    for i, r in enumerate(results, 1):
        print(f"[{i}] RRF={r.score:.4f} ({r.src_type}:{r.src_id}#{r.seq}) {r.context_prefix}")
        print(f"    {r.content[:100].replace(chr(10), ' ')}")


if __name__ == "__main__":
    _main()
