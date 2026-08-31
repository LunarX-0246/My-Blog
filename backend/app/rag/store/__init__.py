# 向量存储层：抽象接口 + pgvector / numpy 双后端（技术方案 §6.5）。
from app.rag.store.base import (
    ChunkVec,
    ScoredChunk,
    SearchFilter,
    StoreStats,
    VectorStore,
    get_store,
)

__all__ = [
    "ChunkVec",
    "ScoredChunk",
    "SearchFilter",
    "StoreStats",
    "VectorStore",
    "get_store",
]
