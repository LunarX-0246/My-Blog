"""numpy 存储后端（对比实验用，技术方案 §12）。

启动时载入 .npy 到内存，矩阵乘法暴力检索（精确）。范围过滤仅支持 src_types / src_id
（对比实验不测 tag/dir 过滤）。
"""
from __future__ import annotations

import json

import numpy as np
from sqlalchemy.orm import Session

from app.config import settings
from app.rag.store.base import ChunkVec, ScoredChunk, SearchFilter, StoreStats, VectorStore


class NumpyStore(VectorStore):
    def __init__(self) -> None:
        self._chunks: list[ChunkVec] = []
        self._matrix: np.ndarray | None = None

    def _refresh(self) -> None:
        self._matrix = (
            np.asarray([c.embedding for c in self._chunks], dtype=np.float32)
            if self._chunks
            else None
        )

    def upsert(self, db: Session, chunks: list[ChunkVec]) -> None:
        for c in chunks:
            self._chunks = [
                x
                for x in self._chunks
                if not (x.src_type == c.src_type and x.src_id == c.src_id and x.seq == c.seq)
            ]
            self._chunks.append(c)
        self._refresh()
        self._save()

    def delete_by_source(self, db: Session, src_type: str, src_id: int) -> None:
        self._chunks = [x for x in self._chunks if not (x.src_type == src_type and x.src_id == src_id)]
        self._refresh()
        self._save()

    def search(
        self, db: Session, query_vec: list[float], top_k: int, flt: SearchFilter | None = None
    ) -> list[ScoredChunk]:
        if self._matrix is None:
            return []
        sims = self._matrix @ np.asarray(query_vec, dtype=np.float32)
        scored: list[tuple[int, float]] = []
        for i, c in enumerate(self._chunks):
            if flt and flt.src_types and c.src_type not in flt.src_types:
                continue
            if flt and flt.src_id is not None and c.src_id != flt.src_id:
                continue
            scored.append((i, float(sims[i])))
        scored.sort(key=lambda x: -x[1])
        return [
            ScoredChunk(
                src_type=self._chunks[i].src_type,
                src_id=self._chunks[i].src_id,
                seq=self._chunks[i].seq,
                content=self._chunks[i].content,
                context_prefix=self._chunks[i].context_prefix,
                page_no=self._chunks[i].page_no,
                anchor=self._chunks[i].anchor,
                score=s,
            )
            for i, s in scored[:top_k]
        ]

    def rebuild(self, db: Session, chunks: list[ChunkVec]) -> None:
        self._chunks = list(chunks)
        self._refresh()
        self._save()

    def stats(self, db: Session) -> StoreStats:
        return StoreStats(total_chunks=len(self._chunks), backend="numpy")

    def _save(self) -> None:
        vectors_dir = settings.data_dir_path / "vectors"
        vectors_dir.mkdir(parents=True, exist_ok=True)
        if self._matrix is not None:
            np.save(vectors_dir / "embeddings.npy", self._matrix)
        meta = [
            {
                "src_type": c.src_type,
                "src_id": c.src_id,
                "seq": c.seq,
                "content": c.content,
                "context_prefix": c.context_prefix,
                "page_no": c.page_no,
                "anchor": c.anchor,
            }
            for c in self._chunks
        ]
        (vectors_dir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False), encoding="utf-8"
        )
