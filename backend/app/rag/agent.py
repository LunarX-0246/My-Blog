"""按需检索（技术方案 §6.7，红线 R5）。

检索做成模型可调用的工具，由模型自行判断是否需要查知识库（FR-ASK-09）。
一期只有 search_kb 一个工具；二期扩展 list_posts / get_post_outline 时无需重构。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.rag import llm, retriever
from app.rag.generator import NO_RETRIEVAL_PROMPT, SYSTEM_PROMPT, build_context
from app.rag.store.base import ScoredChunk, SearchFilter

AGENT_PROMPT = (
    "你是「My Blog」的问答助手。判断当前问题是否需要检索博主的文章与知识库：\n"
    "- 涉及博主写过的内容、技术观点、站内资料时，调用 search_kb 检索。\n"
    "- 闲聊、常识性问题不需要检索，直接回答。"
)

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_kb",
            "description": (
                "检索博主的文章与知识库文档。当问题涉及博主写过的内容、技术观点"
                "或站内资料时使用；闲聊、常识性问题不要使用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "scope": {"type": "string", "enum": ["all", "posts", "docs"]},
                },
                "required": ["query"],
            },
        },
    }
]


@dataclass
class AgentResult:
    used_retrieval: bool
    sources: list[ScoredChunk] = field(default_factory=list)
    final_messages: list[dict] = field(default_factory=list)


def _merge_scope(base_flt: SearchFilter | None, tool_scope: str) -> SearchFilter:
    """工具 scope 只在未限定单篇时生效，避免覆盖 FR-ASK-14 的单篇限定。"""
    flt = base_flt if base_flt is not None else SearchFilter()
    if flt.src_id is None and tool_scope in ("posts", "docs"):
        flt.src_types = [tool_scope]
    return flt


def run_agent(
    db: Session, question: str, history: list[dict], base_flt: SearchFilter | None
) -> AgentResult:
    agent_messages = (
        [{"role": "system", "content": AGENT_PROMPT}]
        + history
        + [{"role": "user", "content": question}]
    )
    resp = llm.chat_with_tools(agent_messages, TOOLS)

    # 模型未调用工具 → 未检索，仍需在 R1 约束下作答（H1），走流式（H2）
    if not resp.tool_calls:
        final_messages = (
            [{"role": "system", "content": NO_RETRIEVAL_PROMPT}]
            + history
            + [{"role": "user", "content": question}]
        )
        return AgentResult(used_retrieval=False, final_messages=final_messages)

    # 执行 search_kb 检索
    sources: list[ScoredChunk] = []
    for tc in resp.tool_calls:
        if tc.name != "search_kb":
            continue
        args = json.loads(tc.arguments or "{}")
        query = args.get("query") or question
        flt = _merge_scope(base_flt, args.get("scope") or "all")
        sources = retriever.retrieve(db, query, flt=flt)
        break

    # 组装最终生成 messages：system prompt（含 R1 约束）注入检索上下文
    system = SYSTEM_PROMPT
    if sources:
        system += "\n\n参考资料：\n" + build_context(sources)
    final_messages = (
        [{"role": "system", "content": system}]
        + history
        + [{"role": "user", "content": question}]
    )
    return AgentResult(used_retrieval=True, sources=sources, final_messages=final_messages)
