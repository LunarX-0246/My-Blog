"""混合检索（技术方案 §6.6，红线 R4）。

向量 + BM25 两路检索，RRF 融合排序。BM25 不可省略——技术内容里大量专有名词、
函数名、报错信息，纯语义检索容易失准，BM25 一击命中。

可独立运行自测：python -m app.rag.retriever --query "混合检索"
"""
from __future__ import annotations

import argparse
from collections import defaultdict

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Chunk, Document, SourceType, document_tags, post_tags
from app.rag.bm25 import BM25
from app.rag.embedder import embed_one
from app.rag.store.base import ScoredChunk, SearchFilter, get_store


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
    query_vec = embed_one(query)
    vec_results = get_store().search(db, query_vec, settings.retrieve_top_k, flt)

    # 2. BM25 检索
    chunks = load_chunks(db, flt)
    bm25 = BM25([c.content for c in chunks])
    bm25_results = [
        ScoredChunk(
            src_type=chunks[i].src_type,
            src_id=chunks[i].src_id,
            seq=chunks[i].seq,
            content=chunks[i].content,
            context_prefix=chunks[i].context_prefix,
            page_no=chunks[i].page_no,
            anchor=chunks[i].anchor,
            score=score,
        )
        for i, score in bm25.search(query, settings.retrieve_top_k)
    ]

    # 3. RRF 融合
    return rrf_fusion([vec_results, bm25_results], settings.rrf_k, top_k)


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
