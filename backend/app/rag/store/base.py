"""向量存储抽象接口（技术方案 §6.5）。

pgvector（生产）与 numpy（对比实验）共用同一接口，切换后端只改一处。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from sqlalchemy.orm import Session


@dataclass
class ChunkVec:
    """待写入存储的块（含向量）。"""

    src_type: str
    src_id: int
    seq: int
    content: str
    context_prefix: str
    embed_text: str
    fingerprint: str
    page_no: int | None
    anchor: str | None
    embedding: list[float]


@dataclass
class ScoredChunk:
    """检索命中的块（含相似度分数）。"""

    src_type: str
    src_id: int
    seq: int
    content: str
    context_prefix: str
    page_no: int | None
    anchor: str | None
    score: float


@dataclass
class SearchFilter:
    """范围过滤（RAG-RETR-03）。"""

    src_types: list[str] | None = None    # ['post'] / ['document']
    tag_ids: list[int] | None = None
    dir_prefix: str | None = None         # 只在某个知识库目录下检索
    src_id: int | None = None             # FR-ASK-14 限定单篇


@dataclass
class StoreStats:
    total_chunks: int
    backend: str


class VectorStore(ABC):
    @abstractmethod
    def upsert(self, db: Session, chunks: list[ChunkVec]) -> None: ...

    @abstractmethod
    def delete_by_source(self, db: Session, src_type: str, src_id: int) -> None: ...

    @abstractmethod
    def search(
        self, db: Session, query_vec: list[float], top_k: int, flt: SearchFilter | None = None
    ) -> list[ScoredChunk]: ...

    @abstractmethod
    def rebuild(self, db: Session, chunks: list[ChunkVec]) -> None: ...

    @abstractmethod
    def stats(self, db: Session) -> StoreStats: ...


_numpy_store: VectorStore | None = None


def get_store() -> VectorStore:
    """按 VECTOR_BACKEND 配置返回对应后端。

    ★ numpy 后端必须复用同一实例：向量常驻实例内存，每次 new 都要重新读盘
      反序列化；更要命的是不同实例之间的 upsert 互相看不见，会出现
      「刚写进去的块检索不到」这种极难定位的问题。
      pgvector 后端无状态（数据都在库里），每次新建无妨。
    """
    global _numpy_store
    from app.config import settings

    if settings.vector_backend == "numpy":
        if _numpy_store is None:
            from app.rag.store.numpy_store import NumpyStore

            _numpy_store = NumpyStore()
        return _numpy_store
    from app.rag.store.pgvector_store import PgvectorStore

    return PgvectorStore()
