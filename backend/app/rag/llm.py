"""模型调用封装（DeepSeek，兼容 openai 协议）。

一期只提供非流式 ``chat``（用于 AI 生成摘要等一次性调用）。
T3c-1 会在此扩展：流式输出 + 主模型失败自动降级到备用模型（技术方案 §14）。
"""
from __future__ import annotations

from openai import OpenAI

from app.config import settings

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    """惰性创建客户端（单例），避免每次调用都重建连接。"""
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )
    return _client


def chat(
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 512,
    temperature: float = 0.3,
) -> str:
    """非流式对话，返回回复文本。失败时抛出异常，由调用方转成面向用户的中文提示。"""
    resp = _get_client().chat.completions.create(
        model=settings.deepseek_model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return resp.choices[0].message.content or ""
