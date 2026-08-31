"""多轮上下文分层压缩（技术方案 §6.9，RAG-GEN-05）。

无状态：历史由前端 localStorage 传入，每次请求现算压缩。
依据：刚发生的事需要细节，久远的事只需要结论。
"""
from __future__ import annotations

from app.config import settings

# 更早轮次保留的答案长度上限（「结论」）
_OLD_ANSWER_MAX = 200


def compress_history(history: list[dict]) -> list[dict]:
    """分层压缩：最近 keep_full_turns 轮完整保留，更早的仅保留问题 + 截断答案。"""
    if not history:
        return []

    keep = settings.memory_keep_full_turns
    # 按轮分组（user 与紧随的 assistant 为一轮）
    turns: list[tuple[dict, dict | None]] = []
    i = 0
    while i < len(history):
        msg = history[i]
        if msg.get("role") == "user":
            assistant = history[i + 1] if i + 1 < len(history) and history[i + 1].get("role") == "assistant" else None
            turns.append((msg, assistant))
            i += 2 if assistant else 1
        else:
            i += 1

    result: list[dict] = []
    for idx, (q, a) in enumerate(turns):
        is_recent = idx >= len(turns) - keep
        result.append(q)
        if a is None:
            continue
        if is_recent:
            result.append(a)
        else:
            # 更早轮次：仅保留结论（截断答案）
            content = (a.get("content") or "")[:_OLD_ANSWER_MAX]
            result.append({"role": "assistant", "content": content})
    return result
