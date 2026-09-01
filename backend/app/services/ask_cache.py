"""问答结果缓存（FR-ASK-23）。

- 键：问题归一化后（去空白、小写、去标点）。
- 命中时直接返回，不重复调用模型。
- 内容变更时清空全部缓存（N7，决策 A：全清而非精确失效）。
"""
from __future__ import annotations

import re
import threading

_cache: dict[str, dict] = {}
_lock = threading.Lock()


def normalize(question: str) -> str:
    """归一化问题：去首尾空白、小写、去常见标点。"""
    q = question.strip().lower()
    return re.sub(r"[\s，。！？、,.!?；;：:\"'“”‘’]+", "", q)


def get(key: str) -> dict | None:
    with _lock:
        return _cache.get(key)


def put(key: str, value: dict) -> None:
    with _lock:
        _cache[key] = value


def clear() -> None:
    """内容变更时清空全部缓存（N7）。"""
    with _lock:
        _cache.clear()
