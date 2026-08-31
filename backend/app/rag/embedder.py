"""向量化（技术方案 §6.4）。

千问 text-embedding-v3（openai 兼容协议），批量提交、失败重试 3 次并退避，
L2 归一化后返回 —— 余弦相似度退化为内积，检索只需一次矩阵乘法。
"""
from __future__ import annotations

import time

import numpy as np
from openai import OpenAI

from app.config import settings

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=settings.dashscope_api_key,
            base_url=settings.dashscope_base_url,
        )
    return _client


def _embed_with_retry(client: OpenAI, batch: list[str]) -> tuple[list[list[float]], int]:
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            resp = client.embeddings.create(model=settings.embedding_model, input=batch)
            vectors = [item.embedding for item in resp.data]
            total_tokens = getattr(resp.usage, "total_tokens", 0) or 0
            # L2 归一化
            arr = np.asarray(vectors, dtype=np.float32)
            norms = np.linalg.norm(arr, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            arr = arr / norms
            return [row.tolist() for row in arr], total_tokens
        except Exception as e:  # noqa: BLE001 —— 网络/限流错误统一重试
            last_exc = e
            time.sleep(2 ** attempt)  # 1s / 2s / 4s 退避
    raise last_exc if last_exc else RuntimeError("embedding failed")


def embed_batch(texts: list[str], *, usage_out: list[int] | None = None) -> list[list[float]]:
    """批量向量化，返回 L2 归一化后的向量列表（与输入顺序一致）。

    usage_out 传入时追加每批的 total_tokens，供索引环节累计消耗（M3）。
    """
    result: list[list[float]] = []
    for i in range(0, len(texts), settings.embed_batch_size):
        batch = texts[i : i + settings.embed_batch_size]
        vectors, total_tokens = _embed_with_retry(_get_client(), batch)
        if usage_out is not None:
            usage_out.append(total_tokens)
        result.extend(vectors)
    return result


def embed_one(text: str) -> list[float]:
    """向量化单条文本。"""
    return embed_batch([text])[0]
