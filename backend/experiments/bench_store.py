"""向量存储后端对比实验（技术方案 §12，二期 T9-1 ~ T9-5）。

对比三种后端在同一份数据、同一组查询下的表现：

    numpy       内存矩阵乘法，暴力全扫  —— **精确**，作为 Recall 的 ground truth
    pg-seq      pgvector 顺序扫描      —— 精确，但走数据库
    pg-hnsw     pgvector + HNSW 索引   —— **近似**，用召回率衡量它漏了多少

指标：P50 / P95 检索延迟、Recall@k、常驻内存。

★ 可复现性（N9）：固定随机种子、固定查询集、记录运行环境。
★ 数据真实性（N8）：合成数据以真实向量为基底扰动重采样，
  真实样本不足时直接报错拒绝运行，见 datagen.py。

用法：
    python -m experiments.bench_store --check          # 只做后端一致性校验（T9-4）
    python -m experiments.bench_store --bench          # 跑完整对比
    python -m experiments.bench_store --bench -n 2000  # 合成扩充到 2000 条
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sqlalchemy import text

from app.config import settings
from app.db import SessionLocal
from app.rag.store.base import ChunkVec, ScoredChunk
from app.rag.store.numpy_store import NumpyStore
from app.rag.store.pgvector_store import PgvectorStore
from experiments import datagen

OUT_DIR = Path(__file__).parent / "output"

# 检索评测的 top-k。与生产的 RETRIEVE_TOP_K 一致，保证结论对生产有参考意义。
TOP_K = settings.retrieve_top_k
SEED = 42


# ══════════════════════════════════════════════════════════════════
#  工具
# ══════════════════════════════════════════════════════════════════

def _key(c: ScoredChunk) -> tuple[str, int, int]:
    return (c.src_type, c.src_id, c.seq)


def _rss_mb() -> float:
    """当前进程常驻内存（MB）。无 psutil 时退化为 0，不影响其余指标。"""
    try:
        import psutil

        return psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
    except Exception:
        return 0.0


def _set_hnsw(db, enabled: bool) -> None:
    """开关 HNSW 索引。

    关掉索引时用 `enable_indexscan=off` 强制顺序扫描 —— 比删了重建快得多，
    也避免在实验中反复 DDL。
    """
    db.execute(text(f"SET enable_indexscan = {'on' if enabled else 'off'}"))
    db.execute(text(f"SET enable_bitmapscan = {'on' if enabled else 'off'}"))


# ══════════════════════════════════════════════════════════════════
#  T9-4 · 后端一致性校验
# ══════════════════════════════════════════════════════════════════

@dataclass
class ConsistencyResult:
    queries: int
    identical: int
    mismatched: int
    max_score_diff: float
    passed: bool


def check_consistency(chunks: list[ChunkVec], queries: list[list[float]]) -> ConsistencyResult:
    """校验 numpy 与 pgvector 顺序扫描返回一致的 top-k（T9-4）。

    两者都是**精确**检索，同一份数据、同一个查询下结果集与排序必须一致；
    分数允许浮点误差（numpy 用 float32，pgvector 内部是 float4，
    两边的舍入路径不同）。

    这不是性能测试，与数据量无关 —— 15 个块也能测。
    此时不测，等有了大数据量再发现两边不一致，差异会被误当成「实验结果」，
    极难定位到是后端实现本身有 bug。
    """
    np_store = NumpyStore(autoload=False)
    np_store.rebuild(None, chunks)  # numpy 后端不用 db

    identical = 0
    mismatched = 0
    max_diff = 0.0

    with SessionLocal() as db:
        _set_hnsw(db, False)  # 强制顺序扫描，保证 pgvector 侧也是精确的
        pg_store = PgvectorStore()
        for q in queries:
            a = np_store.search(None, q, TOP_K)
            b = pg_store.search(db, q, TOP_K)
            if [_key(x) for x in a] == [_key(x) for x in b]:
                identical += 1
                for x, y in zip(a, b):
                    max_diff = max(max_diff, abs(x.score - y.score))
            else:
                mismatched += 1
                if mismatched <= 3:  # 只打印前几条，避免刷屏
                    print(f"  ✗ 结果不一致：")
                    print(f"      numpy : {[_key(x) for x in a][:5]}")
                    print(f"      pg-seq: {[_key(x) for x in b][:5]}")

    return ConsistencyResult(
        queries=len(queries),
        identical=identical,
        mismatched=mismatched,
        max_score_diff=round(max_diff, 6),
        passed=(mismatched == 0),
    )


# ══════════════════════════════════════════════════════════════════
#  T9-2 · 指标采集
# ══════════════════════════════════════════════════════════════════

@dataclass
class BenchResult:
    backend: str
    n_chunks: int
    p50_ms: float
    p95_ms: float
    recall_at_k: float
    rss_mb: float


def _latencies(search_fn, queries: list[list[float]]) -> tuple[list[float], list[list[tuple]]]:
    """跑一遍查询集，返回每次耗时与命中结果。"""
    lats: list[float] = []
    hits: list[list[tuple]] = []
    for q in queries:
        t = time.perf_counter()
        res = search_fn(q)
        lats.append((time.perf_counter() - t) * 1000)
        hits.append([_key(x) for x in res])
    return lats, hits


def _recall(truth: list[list[tuple]], got: list[list[tuple]]) -> float:
    """Recall@k：以精确检索为 ground truth，看近似检索找回了多少。"""
    total = hit = 0
    for t, g in zip(truth, got):
        s = set(g)
        total += len(t)
        hit += sum(1 for x in t if x in s)
    return round(hit / total, 4) if total else 0.0


def run_bench(chunks: list[ChunkVec], queries: list[list[float]]) -> list[BenchResult]:
    results: list[BenchResult] = []

    # ── numpy（精确，ground truth）─────────────────────────────
    np_store = NumpyStore(autoload=False)
    np_store.rebuild(None, chunks)
    lats, truth = _latencies(lambda q: np_store.search(None, q, TOP_K), queries)
    results.append(
        BenchResult(
            backend="numpy",
            n_chunks=len(chunks),
            p50_ms=round(statistics.median(lats), 3),
            p95_ms=round(sorted(lats)[int(len(lats) * 0.95) - 1], 3),
            recall_at_k=1.0,  # 自己就是 ground truth
            rss_mb=round(_rss_mb(), 1),
        )
    )

    # ── pgvector 两种模式 ──────────────────────────────────────
    with SessionLocal() as db:
        pg_store = PgvectorStore()
        for name, use_index in (("pg-seq", False), ("pg-hnsw", True)):
            _set_hnsw(db, use_index)
            lats, got = _latencies(lambda q: pg_store.search(db, q, TOP_K), queries)
            results.append(
                BenchResult(
                    backend=name,
                    n_chunks=len(chunks),
                    p50_ms=round(statistics.median(lats), 3),
                    p95_ms=round(sorted(lats)[int(len(lats) * 0.95) - 1], 3),
                    recall_at_k=_recall(truth, got),
                    rss_mb=round(_rss_mb(), 1),
                )
            )
    return results


# ══════════════════════════════════════════════════════════════════
#  运行环境记录（N9）
# ══════════════════════════════════════════════════════════════════

def env_info(n_real: int, n_total: int) -> dict:
    return {
        "时间": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "Python": platform.python_version(),
        "平台": f"{platform.system()} {platform.release()}",
        "numpy": np.__version__,
        "embedding_model": settings.embedding_model,
        "embedding_dim": settings.embedding_dim,
        "top_k": TOP_K,
        "随机种子": SEED,
        "真实块数": n_real,
        "参与实验的块数": n_total,
    }


# ══════════════════════════════════════════════════════════════════
#  入口
# ══════════════════════════════════════════════════════════════════

def _main() -> int:
    ap = argparse.ArgumentParser(description="向量存储后端对比实验")
    ap.add_argument("--check", action="store_true", help="只做后端一致性校验（T9-4）")
    ap.add_argument("--bench", action="store_true", help="跑完整对比实验")
    ap.add_argument("-n", "--target", type=int, default=0, help="合成扩充到多少条（0=只用真实数据）")
    ap.add_argument("-q", "--queries", type=int, default=20, help="查询条数")
    args = ap.parse_args()

    if not (args.check or args.bench):
        ap.print_help()
        return 1

    real = datagen.load_real_chunks()
    print(f"真实块：{len(real)} 条")
    if not real:
        print("✗ 数据库里没有带向量的块，先发布内容并完成索引。")
        return 1

    chunks = real
    if args.target:
        try:
            chunks = datagen.synthesize(real, args.target, seed=SEED)
            print(f"合成扩充至：{len(chunks)} 条")
        except datagen.InsufficientRealData as e:
            print(f"\n✗ {e}")
            return 1

    queries = datagen.build_queries(chunks, args.queries, seed=SEED)
    print(f"查询集：{len(queries)} 条（种子 {SEED}）\n")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload: dict = {"环境": env_info(len(real), len(chunks))}

    if args.check:
        print("── T9-4 后端一致性校验（numpy 暴力 vs pgvector 顺序扫描）──")
        r = check_consistency(chunks, queries)
        payload["一致性校验"] = asdict(r)
        print(f"  查询数      : {r.queries}")
        print(f"  结果一致    : {r.identical}")
        print(f"  结果不一致  : {r.mismatched}")
        print(f"  最大分数差  : {r.max_score_diff}")
        print(f"  {'✓ 通过' if r.passed else '✗ 未通过'}\n")

    if args.bench:
        print("── 对比实验 ──")
        rs = run_bench(chunks, queries)
        payload["对比结果"] = [asdict(x) for x in rs]
        print(f"  {'后端':<10}{'块数':>8}{'P50(ms)':>10}{'P95(ms)':>10}{'Recall@'+str(TOP_K):>12}{'RSS(MB)':>10}")
        for x in rs:
            print(f"  {x.backend:<10}{x.n_chunks:>8}{x.p50_ms:>10.3f}{x.p95_ms:>10.3f}"
                  f"{x.recall_at_k:>12.4f}{x.rss_mb:>10.1f}")
        print()

    out = OUT_DIR / f"bench_{len(chunks)}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"结果已写入 {out}")

    if args.check and not payload["一致性校验"]["passed"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(_main())
