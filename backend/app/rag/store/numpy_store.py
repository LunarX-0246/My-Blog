"""numpy 存储后端（对比实验用，技术方案 §12）。

向量常驻内存，检索是一次矩阵乘法 —— **精确**、无近似误差。因此在对比实验中
它充当 Recall 的 ground truth：pgvector + HNSW 是近似检索，要拿它来对照。

范围过滤仅支持 src_types / src_id。对比实验不测 tag / dir 过滤，
生产环境用的是 pgvector 后端，那边的过滤是完整的。

★ 持久化：向量存 `vectors/embeddings.npy`，元数据存 `vectors/meta.json`。
  **实例化时必须从磁盘载入** —— 缺了这一步，进程重启或换一个实例后
  `_chunks` 恒为空，`search()` 永远返回空列表，而且不报任何错。
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from sqlalchemy.orm import Session

from app.config import settings
from app.rag.store.base import ChunkVec, ScoredChunk, SearchFilter, StoreStats, VectorStore


class NumpyStore(VectorStore):
    def __init__(self, *, autoload: bool = True) -> None:
        self._chunks: list[ChunkVec] = []
        self._matrix: np.ndarray | None = None
        if autoload:
            self._load()

    # ── 持久化 ──────────────────────────────────────────────────────

    def _paths(self) -> tuple[Path, Path, Path]:
        d = settings.data_dir_path / "vectors"
        return d, d / "embeddings.npy", d / "meta.json"

    def _load(self) -> None:
        """从磁盘载入已保存的向量与元数据。

        两个文件缺一、或条数对不上，都当作空索引处理 ——
        **半个索引比空索引危险得多**：向量与元数据错位时，检索会返回
        张冠李戴的结果，而且完全看不出异常。
        """
        _, npy, meta_path = self._paths()
        if not (npy.exists() and meta_path.exists()):
            return
        matrix = np.load(npy)
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if len(meta) != matrix.shape[0]:
            return
        self._chunks = [
            ChunkVec(
                src_type=m["src_type"],
                src_id=m["src_id"],
                seq=m["seq"],
                content=m["content"],
                context_prefix=m["context_prefix"],
                embed_text=m.get("embed_text", ""),
                fingerprint=m.get("fingerprint", ""),
                page_no=m["page_no"],
                anchor=m["anchor"],
                embedding=matrix[i].tolist(),
            )
            for i, m in enumerate(meta)
        ]
        self._matrix = matrix.astype(np.float32)

    def _save(self) -> None:
        vectors_dir, npy, meta_path = self._paths()
        vectors_dir.mkdir(parents=True, exist_ok=True)
        if self._matrix is not None:
            np.save(npy, self._matrix)
        # embed_text / fingerprint 也要存，否则 load 后再 save 会把它们抹掉
        meta = [
            {
                "src_type": c.src_type,
                "src_id": c.src_id,
                "seq": c.seq,
                "content": c.content,
                "context_prefix": c.context_prefix,
                "embed_text": c.embed_text,
                "fingerprint": c.fingerprint,
                "page_no": c.page_no,
                "anchor": c.anchor,
            }
            for c in self._chunks
        ]
        meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    def _refresh(self) -> None:
        self._matrix = (
            np.asarray([c.embedding for c in self._chunks], dtype=np.float32)
            if self._chunks
            else None
        )

    # ── VectorStore 接口 ────────────────────────────────────────────

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
        self._chunks = [
            x for x in self._chunks if not (x.src_type == src_type and x.src_id == src_id)
        ]
        self._refresh()
        self._save()

    def search(
        self, db: Session, query_vec: list[float], top_k: int, flt: SearchFilter | None = None
    ) -> list[ScoredChunk]:
        """暴力检索：一次矩阵乘法算出全部相似度，排序取前 k。

        向量写入前已 L2 归一化，内积即余弦相似度，与 pgvector 的
        ``1 - cosine_distance`` 是同一口径 —— 两个后端的分数可直接比较，
        这是 T9-4 一致性校验成立的前提。
        """
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
        # 分数相同时按 (src_type, src_id, seq) 定序，保证结果可复现（N9）
        scored.sort(
            key=lambda x: (
                -x[1],
                self._chunks[x[0]].src_type,
                self._chunks[x[0]].src_id,
                self._chunks[x[0]].seq,
            )
        )
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
