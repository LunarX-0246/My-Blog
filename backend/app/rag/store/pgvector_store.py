"""pgvector 存储后端（生产，技术方案 §6.5）。"""
from __future__ import annotations

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.orm import Session

from app.models import Chunk, Document, SourceType, document_tags, post_tags
from app.rag.store.base import ChunkVec, ScoredChunk, SearchFilter, StoreStats, VectorStore


def _to_enum(src_type: str) -> SourceType:
    return SourceType.post if src_type == "post" else SourceType.document


class PgvectorStore(VectorStore):
    def upsert(self, db: Session, chunks: list[ChunkVec]) -> None:
        for c in chunks:
            existing = db.scalar(
                select(Chunk).where(
                    Chunk.src_type == _to_enum(c.src_type),
                    Chunk.src_id == c.src_id,
                    Chunk.seq == c.seq,
                )
            )
            if existing:
                existing.content = c.content
                existing.context_prefix = c.context_prefix
                existing.embed_text = c.embed_text
                existing.fingerprint = c.fingerprint
                existing.page_no = c.page_no
                existing.anchor = c.anchor
                existing.embedding = c.embedding
            else:
                db.add(
                    Chunk(
                        src_type=_to_enum(c.src_type),
                        src_id=c.src_id,
                        seq=c.seq,
                        content=c.content,
                        context_prefix=c.context_prefix,
                        embed_text=c.embed_text,
                        fingerprint=c.fingerprint,
                        page_no=c.page_no,
                        anchor=c.anchor,
                        embedding=c.embedding,
                    )
                )
        db.commit()

    def delete_by_source(self, db: Session, src_type: str, src_id: int) -> None:
        db.execute(
            delete(Chunk).where(Chunk.src_type == _to_enum(src_type), Chunk.src_id == src_id)
        )
        db.commit()

    def search(
        self, db: Session, query_vec: list[float], top_k: int, flt: SearchFilter | None = None
    ) -> list[ScoredChunk]:
        distance = Chunk.embedding.cosine_distance(query_vec)
        stmt = select(Chunk, (1 - distance).label("score")).where(Chunk.embedding.is_not(None))

        if flt:
            if flt.src_types:
                stmt = stmt.where(Chunk.src_type.in_([_to_enum(t) for t in flt.src_types]))
            if flt.src_id is not None:
                stmt = stmt.where(Chunk.src_id == flt.src_id)
            if flt.dir_prefix:
                doc_ids = select(Document.id).where(
                    Document.dir_path.like(f"{flt.dir_prefix}%")
                )
                stmt = stmt.where(
                    and_(Chunk.src_type == SourceType.document, Chunk.src_id.in_(doc_ids))
                )
            if flt.tag_ids:
                post_ids = select(post_tags.c.post_id).where(
                    post_tags.c.tag_id.in_(flt.tag_ids)
                )
                doc_ids = select(document_tags.c.document_id).where(
                    document_tags.c.tag_id.in_(flt.tag_ids)
                )
                stmt = stmt.where(
                    or_(
                        and_(Chunk.src_type == SourceType.post, Chunk.src_id.in_(post_ids)),
                        and_(Chunk.src_type == SourceType.document, Chunk.src_id.in_(doc_ids)),
                    )
                )

        rows = db.execute(stmt.order_by(distance).limit(top_k)).all()
        return [
            ScoredChunk(
                src_type=chunk.src_type.value,
                src_id=chunk.src_id,
                seq=chunk.seq,
                content=chunk.content,
                context_prefix=chunk.context_prefix,
                page_no=chunk.page_no,
                anchor=chunk.anchor,
                score=float(score),
            )
            for chunk, score in rows
        ]

    def rebuild(self, db: Session, chunks: list[ChunkVec]) -> None:
        # 全量重建：清空后重写
        db.execute(delete(Chunk))
        db.commit()
        self.upsert(db, chunks)

    def stats(self, db: Session) -> StoreStats:
        total = db.scalar(select(func.count()).select_from(Chunk)) or 0
        return StoreStats(total_chunks=int(total), backend="pgvector")
