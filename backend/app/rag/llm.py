"""模型调用封装（DeepSeek，兼容 openai 协议；技术方案 §6.10）。

- ``chat``：非流式，返回文本（AI 摘要等一次性调用）
- ``chat_with_tools``：非流式 + 工具调用，返回内容与 tool_calls（按需检索判定）
- ``stream_chat``：流式，逐 token 产出文本（最终回答）

主模型失败自动降级到备用模型（LLM_FALLBACK_MODEL，留空则不降级）。
"""
from __future__ import annotations

import re
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
    usage: "Usage" = field(default_factory=lambda: Usage())


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0


def _usage(resp_usage) -> Usage:
    return Usage(
        prompt_tokens=getattr(resp_usage, "prompt_tokens", 0) or 0,
        completion_tokens=getattr(resp_usage, "completion_tokens", 0) or 0,
    )


def chat_with_tools(
    messages: list[dict], tools: list[dict], *, temperature: float = 0.0
) -> ToolMessage:
    """带工具的非流式调用，返回内容、tool_calls 与 usage（用于按需检索判定与 token 统计）。"""
    last: Exception | None = None
    for model in _models():
        try:
            resp = _create(model, messages, tools=tools, temperature=temperature)
            msg = resp.choices[0].message
            calls = [
                ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments)
                for tc in (msg.tool_calls or [])
            ]
            return ToolMessage(content=msg.content, tool_calls=calls, usage=_usage(resp.usage))
        except Exception as e:  # noqa: BLE001
            last = e
    raise last if last else RuntimeError("LLM 调用失败")


# 模型内部的工具调用标记。最终生成阶段不传 tools，但模型偶尔仍"想"继续调工具，
# 于是把整套标记当成普通文本吐出来 —— 用户看到的是
# `<｜｜DSML｜｜tool_calls><｜｜DSML｜｜invoke name="get_post_outline">…` 这样的乱码。
# 注意标记里是**全角**竖线，不是 ASCII 的 |。
#
# ★ 必须**整块剔除**，包括标签之间的参数值。只删标签的话，
#   参数值（文章 slug、章节名）会作为正文留下来，看着更像是回答，实际是垃圾。
_TOOL_BLOCK = re.compile(
    r"<\s*[｜|]*\s*DSML\s*[｜|]*\s*tool_calls\b.*?<\s*/\s*[｜|]*\s*DSML\s*[｜|]*\s*tool_calls\s*>"
    r"|<\s*tool_calls\b.*?</\s*tool_calls\s*>"
    r"|<\s*[｜|]*\s*DSML\s*[｜|]*\s*invoke\b.*?<\s*/\s*[｜|]*\s*DSML\s*[｜|]*\s*invoke\s*>"
    r"|<\s*invoke\b.*?</\s*invoke\s*>",
    re.S,
)
# 兜底：残留的单个标签（块被截断时可能只剩半边）
_TOOL_TAG = re.compile(
    r"<\s*/?\s*[｜|]*\s*DSML\s*[｜|]*[^>]*>"
    r"|<\s*/?\s*(?:tool_calls|invoke|parameter)\b[^>]*>"
)


# 工具块的开头标记。流式时一旦出现，说明后面是工具调用而非正文，
# 此时必须停止向外产出（闭合标签还在后面的 chunk 里）。
_TOOL_OPEN = re.compile(
    r"<\s*[｜|]*\s*DSML\s*[｜|]*\s*(?:tool_calls|invoke)\b|<\s*(?:tool_calls|invoke)\b"
)


def _strip_tool_markup(text: str) -> str:
    return _TOOL_TAG.sub("", _TOOL_BLOCK.sub("", text))


def stream_chat(
    messages: list[dict],
    *,
    temperature: float = 0.3,
    max_tokens: int = 1024,
    usage_out: list[Usage] | None = None,
) -> Iterator[str]:
    """流式对话，逐 token 产出文本；usage 追加到 usage_out（开启 include_usage）。

    ★ 产出前剔除模型内部的工具调用标记（见 ``_TOOL_MARKUP``）。
      最终生成阶段不传 tools，但模型偶尔仍"想"调工具，就把这套标记
      当普通文本吐出来，用户看到的是一堆乱码。在最靠近输出的地方统一过滤，
      比指望上游不产生更可靠。

      标记可能被切分在相邻两个 chunk 里，因此保留一个小缓冲：
      只产出确认不可能再构成标记的部分。
    """
    last: Exception | None = None
    for model in _models():
        try:
            stream = _create(
                model, messages, stream=True, temperature=temperature,
                max_tokens=max_tokens, stream_options={"include_usage": True},
            )
            buf = ""
            suppressing = False   # 一旦发现工具块开头，就停止吐出、缓冲到流结束再统一过滤
            for chunk in stream:
                if chunk.usage and usage_out is not None:
                    usage_out.append(_usage(chunk.usage))
                delta = chunk.choices[0].delta if chunk.choices else None
                if not (delta and delta.content):
                    continue
                buf += delta.content
                if suppressing:
                    continue
                if _TOOL_OPEN.search(buf):
                    # 工具块可能跨很多 chunk，闭合标签还没到；此时不能按「截断到最后一个 <」
                    # 往外放，否则块前半截的参数值会漏成正文
                    suppressing = True
                    continue
                # 末尾若有未闭合的 '<'，标记可能被切断，留到下一轮再判断
                cut = buf.rfind("<")
                out, buf = (buf, "") if cut == -1 else (buf[:cut], buf[cut:])
                if out:
                    yield out
            tail = _strip_tool_markup(buf).strip()
            if tail:
                yield tail
            return
        except Exception as e:  # noqa: BLE001
            last = e
    raise last if last else RuntimeError("LLM 调用失败")
