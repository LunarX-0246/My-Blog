"""多工具 Agent（技术方案 §6.7 演进，RAG-DEC-03）。

一期只有 search_kb 一个工具；二期扩展到 list_posts / get_post_outline / get_post_section，
让 AI 能回答检索答不了的元数据问题（「写过几篇」「目录」「某节讲了什么」）。
多轮工具调用循环，模型可串联使用（先 get_post_outline 再 get_post_section）。

N1：元数据工具返回的是事实，模型只能陈述，不得据此发挥。
N2：used_retrieval 仅当 search_kb 被调用才为真，元数据工具不算「检索了知识库」。
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.config import settings
from app.rag import llm, retriever, tools
from app.rag.generator import FINAL_PROMPT, build_context
from app.rag.llm import Usage
from app.rag.store.base import ScoredChunk, SearchFilter

logger = logging.getLogger(__name__)

AGENT_PROMPT = (
    "你是「My Blog」的问答助手，可用工具回答访客的问题：\n"
    "- search_kb：检索博主文章与知识库的内容（回答技术观点、站内内容时用）。\n"
    "- list_posts：列出文章清单（回答「写过几篇」「最近更新」等元数据问题）。\n"
    "- get_post_outline：查看文章目录（回答「结构」「目录」等）。\n"
    "- get_post_section：查看某节完整正文（回答「某节讲了什么」等）。\n"
    "闲聊、常识性问题不需要工具，直接回答。\n"
    "注意：list_posts / get_post_outline / get_post_section 返回的是事实（标题、日期、数量、"
    "目录、正文），你只能陈述，不得据此发挥或补充通用知识。"
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
    },
    {
        "type": "function",
        "function": {
            "name": "list_posts",
            "description": (
                "列出博主已发布的文章清单（标题、日期、标签）。"
                "用于回答「写过几篇关于 X 的」「最近更新了什么」等元数据问题。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tag": {"type": "string", "description": "按标签 slug 过滤"},
                    "category": {"type": "string", "description": "按分类 slug 过滤"},
                    "date_from": {"type": "string", "description": "起始日期 YYYY-MM-DD"},
                    "date_to": {"type": "string", "description": "结束日期 YYYY-MM-DD"},
                    "limit": {"type": "integer", "description": "最多返回条数，默认 20"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_post_outline",
            "description": (
                "返回某篇已发布文章的标题目录（含锚点）。用于回答「那篇的结构」「目录」等问题。"
            ),
            "parameters": {
                "type": "object",
                "properties": {"slug": {"type": "string", "description": "文章 slug"}},
                "required": ["slug"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_post_section",
            "description": (
                "返回某篇已发布文章某一节（按锚点）的完整正文。用于回答「某节讲了什么」等问题。"
                "slug 与 anchor 从 get_post_outline 的结果获取。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string", "description": "文章 slug"},
                    "anchor": {"type": "string", "description": "章节锚点（来自 get_post_outline）"},
                },
                "required": ["slug", "anchor"],
            },
        },
    },
]


@dataclass
class AgentResult:
    used_retrieval: bool
    sources: list[ScoredChunk] = field(default_factory=list)
    final_messages: list[dict] = field(default_factory=list)
    tool_usage: Usage = field(default_factory=Usage)
    used_tools: list[str] = field(default_factory=list)


def _merge_scope(base_flt: SearchFilter | None, tool_scope: str) -> SearchFilter:
    """工具 scope 只在未限定单篇时生效，避免覆盖 FR-ASK-14 的单篇限定。"""
    flt = base_flt if base_flt is not None else SearchFilter()
    if flt.src_id is None and tool_scope in ("posts", "docs"):
        flt.src_types = [tool_scope]
    return flt


def run_agent(
    db: Session, question: str, history: list[dict], base_flt: SearchFilter | None
):
    """多工具循环（生成器）：可能先 yield 阶段标记，最后 yield AgentResult。

    阶段标记：retrieving / listing / outlining / sectioning，供 ask.py 发 status（T5-7）。
    """
    agent_messages = (
        [{"role": "system", "content": AGENT_PROMPT}]
        + history
        + [{"role": "user", "content": question}]
    )
    used_tools: list[str] = []
    sources: list[ScoredChunk] = []
    # B1：已纳入 sources 的块去重键，保证多次 search_kb 时同一块不重复编号
    seen: set[tuple[str, int, int]] = set()
    tool_usage = Usage()

    for _ in range(settings.agent_max_rounds):
        t = time.monotonic()
        resp = llm.chat_with_tools(agent_messages, TOOLS)
        logger.info("ask.timing tool_decision=%.0fms", (time.monotonic() - t) * 1000)
        tool_usage.prompt_tokens += resp.usage.prompt_tokens
        tool_usage.completion_tokens += resp.usage.completion_tokens

        if not resp.tool_calls:
            break  # 模型停止调用工具，准备最终回答

        agent_messages.append(
            {
                "role": "assistant",
                "content": resp.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": tc.arguments},
                    }
                    for tc in resp.tool_calls
                ],
            }
        )

        for tc in resp.tool_calls:
            used_tools.append(tc.name)
            args = json.loads(tc.arguments or "{}")
            if tc.name == "search_kb":
                yield "retrieving"
                flt = _merge_scope(base_flt, args.get("scope") or "all")
                new_sources = retriever.retrieve(db, args.get("query") or question, flt=flt)
                # B1：来源累加而非覆盖；去重后从全局下标继续编号，避免引用编号撞车
                start = len(sources) + 1
                fresh: list[ScoredChunk] = []
                for c in new_sources:
                    key = (c.src_type, c.src_id, c.seq)
                    if key not in seen:
                        seen.add(key)
                        sources.append(c)
                        fresh.append(c)
                content = build_context(fresh, start=start) if fresh else "未检索到相关内容。"
            elif tc.name == "list_posts":
                yield "listing"
                content = tools.list_posts(
                    db,
                    tag=args.get("tag"),
                    category=args.get("category"),
                    date_from=args.get("date_from"),
                    date_to=args.get("date_to"),
                    limit=args.get("limit") or 20,
                )
            elif tc.name == "get_post_outline":
                yield "outlining"
                content = tools.get_post_outline(db, slug=args.get("slug") or "")
            elif tc.name == "get_post_section":
                yield "sectioning"
                content = tools.get_post_section(
                    db, slug=args.get("slug") or "", anchor=args.get("anchor") or ""
                )
            else:
                content = "未知工具"
            agent_messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})

    # 最终生成：system 换成统一约束（R1 + N1 + H1），其余（历史/问题/工具结果）原样保留
    final_messages = [{"role": "system", "content": FINAL_PROMPT}] + agent_messages[1:]
    yield AgentResult(
        used_retrieval=("search_kb" in used_tools),
        sources=sources,
        final_messages=final_messages,
        tool_usage=tool_usage,
        used_tools=used_tools,
    )
