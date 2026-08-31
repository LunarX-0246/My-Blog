"""模型调用封装（DeepSeek，兼容 openai 协议；技术方案 §6.10）。

- ``chat``：非流式，返回文本（AI 摘要等一次性调用）
- ``chat_with_tools``：非流式 + 工具调用，返回内容与 tool_calls（按需检索判定）
- ``stream_chat``：流式，逐 token 产出文本（最终回答）

主模型失败自动降级到备用模型（LLM_FALLBACK_MODEL，留空则不降级）。
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

from openai import OpenAI

from app.config import settings

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )
    return _client


def _models() -> list[str]:
    """主模型 + 备用模型（配置了才降级）。"""
    models = [settings.deepseek_model]
    if settings.llm_fallback_model:
        models.append(settings.llm_fallback_model)
    return models


def _create(model: str, messages: list[dict], *, tools=None, stream=False, **kwargs):
    return _get_client().chat.completions.create(
        model=model, messages=messages, tools=tools, stream=stream, **kwargs
    )


def chat(
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 512,
    temperature: float = 0.3,
) -> str:
    """非流式对话，返回回复文本。主模型失败时降级到备用模型。"""
    last: Exception | None = None
    for model in _models():
        try:
            resp = _create(model, messages, max_tokens=max_tokens, temperature=temperature)
            return resp.choices[0].message.content or ""
        except Exception as e:  # noqa: BLE001
            last = e
    raise last if last else RuntimeError("LLM 调用失败")


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass
class ToolMessage:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)


def chat_with_tools(
    messages: list[dict], tools: list[dict], *, temperature: float = 0.0
) -> ToolMessage:
    """带工具的非流式调用，返回内容与 tool_calls（用于按需检索判定）。"""
    last: Exception | None = None
    for model in _models():
        try:
            resp = _create(model, messages, tools=tools, temperature=temperature)
            msg = resp.choices[0].message
            calls = [
                ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments)
                for tc in (msg.tool_calls or [])
            ]
            return ToolMessage(content=msg.content, tool_calls=calls)
        except Exception as e:  # noqa: BLE001
            last = e
    raise last if last else RuntimeError("LLM 调用失败")


def stream_chat(
    messages: list[dict], *, temperature: float = 0.3, max_tokens: int = 1024
) -> Iterator[str]:
    """流式对话，逐 token 产出文本。"""
    last: Exception | None = None
    for model in _models():
        try:
            stream = _create(model, messages, stream=True, temperature=temperature, max_tokens=max_tokens)
            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield delta.content
            return
        except Exception as e:  # noqa: BLE001
            last = e
    raise last if last else RuntimeError("LLM 调用失败")
