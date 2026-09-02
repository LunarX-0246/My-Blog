"""对比实验的数据准备（技术方案 §12，红线 N8 / N9）。

两件事：
  1. 从数据库读出**真实**的块与向量，作为实验语料
  2. 需要更大规模看趋势时，以真实向量为基底扰动重采样

★★ 为什么绝不能用 np.random.randn 造向量 ★★

1024 维空间里，独立随机向量几乎两两正交 —— 任意两个向量的余弦相似度都集中在 0 附近，
彼此距离几乎相等（高维空间的「距离集中」现象）。而 HNSW 的工作原理正是利用真实
embedding 的**聚类结构**建立近邻图：语义相近的向量扎堆，图上跳几步就能找到邻居。

用随机向量测 HNSW，等于让它在一个没有任何聚类结构的空间里找近邻 ——
召回率会显著偏低，而且**这个数字看起来完全正常**，不会报错、不会异常，
你会得出「HNSW 召回率很差」的错误结论并且找不到原因。

因此本模块在真实样本不足时**直接抛错拒绝运行**，不提供任何降级到随机向量的路径。
这条防线写在代码里，不是写在注释里。
"""
from __future__ import annotations

import numpy as np
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Chunk
from app.rag.store.base import ChunkVec

# 合成扩充所需的最少真实样本数。低于此值，扰动重采样得到的向量
# 会高度自相关，同样不能代表真实分布。
MIN_REAL_SAMPLES = 50


class InsufficientRealData(RuntimeError):
    """真实样本不足以支撑实验（N8）。"""


def load_real_chunks() -> list[ChunkVec]:
    """从数据库读出全部带向量的真实块。"""
    with SessionLocal() as db:
        rows = db.scalars(select(Chunk).where(Chunk.embedding.is_not(None))).all()
        return [
            ChunkVec(
                src_type=c.src_type.value,
                src_id=c.src_id,
                seq=c.seq,
                content=c.content,
                context_prefix=c.context_prefix,
                embed_text=c.embed_text,
                fingerprint=c.fingerprint,
                page_no=c.page_no,
                anchor=c.anchor,
                embedding=list(c.embedding),
            )
            for c in rows
        ]


def synthesize(
    real: list[ChunkVec], target_n: int, *, seed: int = 42, noise: float = 0.05
) -> list[ChunkVec]:
    """以真实向量为基底扰动重采样，扩充到 target_n 条（N8）。

    做法：随机挑一条真实向量 → 叠加一个小幅高斯扰动 → 重新 L2 归一化。
    扰动幅度 noise 控制「新点离原型多远」：太小则新点几乎与原型重合，
    太大则聚类结构被抹平、退化成随机向量。0.05 量级下相似度约 0.99，
    既保留了原有的簇结构，又不是简单复制。

    :param real: 真实块（必须 ≥ MIN_REAL_SAMPLES 条）
    :param target_n: 目标条数
    :param seed: 随机种子，固定以保证结论可复现（N9）
    :param noise: 高斯扰动的标准差
    :raises InsufficientRealData: 真实样本不足时直接拒绝，不降级为随机向量
    """
    if len(real) < MIN_REAL_SAMPLES:
        raise InsufficientRealData(
            f"真实样本仅 {len(real)} 条，少于 {MIN_REAL_SAMPLES} 条，"
            f"不足以支撑合成扩充。\n"
            f"请先通过导入脚本灌入真实内容（见 二期实施说明 §3 阶段 8）。\n"
            f"※ 本模块不提供退化为随机向量的路径 —— 1024 维随机向量两两近似等距，"
            f"没有 HNSW 赖以工作的聚类结构，测出的召回率是失真的。"
        )
    if target_n <= len(real):
        return list(real[:target_n])

    rng = np.random.default_rng(seed)
    base = np.asarray([c.embedding for c in real], dtype=np.float32)
    out = list(real)
    dim = base.shape[1]

    for i in range(target_n - len(real)):
        proto_idx = int(rng.integers(0, len(real)))
        v = base[proto_idx] + rng.normal(0, noise, dim).astype(np.float32)
        v = v / np.linalg.norm(v)  # 重新归一化，与真实向量保持同一口径
        proto = real[proto_idx]
        out.append(
            ChunkVec(
                src_type=proto.src_type,
                src_id=900000 + i,          # 合成数据用独立 id 段，不与真实内容冲突
                seq=0,
                content=proto.content,
                context_prefix=f"[合成] {proto.context_prefix}",
                embed_text=proto.embed_text,
                fingerprint=f"synthetic-{i}",
                page_no=None,
                anchor=None,
                embedding=v.tolist(),
            )
        )
    return out


def build_queries(chunks: list[ChunkVec], n: int = 20, *, seed: int = 42) -> list[list[float]]:
    """构造查询向量集：从语料里随机取若干条，各自加轻微扰动。

    这样每个查询都有明确的「应该命中谁」，且不是原样照抄（否则相似度恒为 1，
    测不出排序能力）。固定种子保证每次跑的是同一组查询（N9）。
    """
    rng = np.random.default_rng(seed)
    mat = np.asarray([c.embedding for c in chunks], dtype=np.float32)
    idx = rng.choice(len(chunks), size=min(n, len(chunks)), replace=False)
    out = []
    for i in idx:
        v = mat[i] + rng.normal(0, 0.02, mat.shape[1]).astype(np.float32)
        out.append((v / np.linalg.norm(v)).tolist())
    return out
