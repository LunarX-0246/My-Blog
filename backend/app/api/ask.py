"""AI 问答接口（技术方案 §5.5）。

SSE 流式；事件顺序：status → sources（★ 必须先于 delta，A4）→ delta → done。
访客无需登录（FR-ASK-03）；服务端无状态，历史由前端传入（R9）。
"""
from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal, get_db
from app.deps import get_client_ip
from app.errors import ApiError
from app.models import Document, Post, PostStatus
from app.rag import agent, llm, memory
from app.rag.store.base import SearchFilter
from app.schemas import AskRequest
from app.services import qa_log_service, ratelimit

router = APIRouter(prefix="/api/ask", tags=["ask"])

logger = logging.getLogger(__name__)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _build_filter(db: Session, scope: dict | None) -> SearchFilter | None:
    """FR-ASK-14：限定单篇（post_slug）。"""
    slug = (scope or {}).get("post_slug")
    if not slug:
        return None
    post = db.scalar(select(Post).where(Post.slug == slug, Post.status == PostStatus.published))
    if not post:
        return SearchFilter(src_types=["post"], src_id=-1)  # 无效，返回空
    return SearchFilter(src_types=["post"], src_id=post.id)


def _source_info(db: Session, s) -> tuple[str, str, str]:
    """返回 (title, url, excerpt)。"""
    if s.src_type == "post":
        post = db.get(Post, s.src_id)
        title = post.title if post else ""
        if post:
            url = f"/posts/{post.slug}#{s.anchor}" if s.anchor else f"/posts/{post.slug}"
        else:
            url = "#"
    else:
        doc = db.get(Document, s.src_id)
        title = doc.title if doc else ""
        if doc and doc.file_format == "pdf" and s.page_no:
            url = f"/docs/{s.src_id}?page={s.page_no}"
        else:
            url = f"/docs/{s.src_id}#chunk-{s.seq}"
    return title, url, (s.content or "")[:200]


@router.post("")
def ask(body: AskRequest, request: Request, db: Session = Depends(get_db)) -> StreamingResponse:
    ip = get_client_ip(request)
    question = body.question.strip()
    if not question:
        raise ApiError(400, "bad_request", "问题不能为空")

    err = ratelimit.check(db, ip, len(question))
    if err:
        raise ApiError(429, "rate_limited", err)

    history = memory.compress_history(body.history)
    base_flt = _build_filter(db, body.scope)
    start = time.monotonic()

    def gen():
        # 问答日志数据（只收业务字段，不落 IP/UA 等身份信息，N3）
        answer_parts: list[str] = []
        used_retrieval = False
        hit_chunks: list = []
        tokens_prompt = 0
        tokens_output = 0
        error_msg: str | None = None
        try:
            yield _sse("status", {"stage": "deciding"})
            # 用独立会话，避免请求会话在流式期间被关闭
            with SessionLocal() as s:
                # 迭代 run_agent（生成器）：可能先 yield 阶段标记，最后 yield AgentResult（M4）
                result = None
                for item in agent.run_agent(s, question, history, base_flt):
                    if isinstance(item, str):
                        yield _sse("status", {"stage": item})
                    else:
                        result = item

                used_retrieval = result.used_retrieval
                hit_chunks = [
                    {"src_type": sc.src_type, "src_id": sc.src_id, "seq": sc.seq, "score": sc.score}
                    for sc in result.sources
                ]

                source_list = []
                if result.used_retrieval:
                    for i, sc in enumerate(result.sources, 1):
                        title, url, excerpt = _source_info(s, sc)
                        source_list.append(
                            {
                                "n": i,
                                "type": sc.src_type,
                                "title": title,
                                "url": url,
                                "excerpt": excerpt,
                                "score": sc.score,
                            }
                        )

                # ★ sources 必须先于 delta 下发（A4）
                # metadata_tools：非 search_kb 的工具（N2：元数据工具不算「检索了知识库」）
                metadata_tools = [t for t in result.used_tools if t != "search_kb"]
                if result.used_retrieval:
                    yield _sse(
                        "sources",
                        {"used_retrieval": True, "sources": source_list, "metadata_tools": metadata_tools},
                    )
                else:
                    yield _sse(
                        "sources",
                        {"used_retrieval": False, "sources": [], "metadata_tools": metadata_tools},
                    )

                # 开始生成前（M4）
                yield _sse("status", {"stage": "generating"})

                # 两条路径统一流式输出（H2），不再整段 yield；记录 token 用量（M3）
                usage = [result.tool_usage]
                t_first = time.monotonic()
                first_logged = False
                for delta in llm.stream_chat(result.final_messages, usage_out=usage):
                    if not first_logged:
                        logger.info("ask.timing first_token=%.0fms", (time.monotonic() - t_first) * 1000)
                        first_logged = True
                    answer_parts.append(delta)
                    yield _sse("delta", {"text": delta})
                final_usage = usage[1] if len(usage) > 1 else llm.Usage()
                tokens_prompt = result.tool_usage.prompt_tokens + final_usage.prompt_tokens
                tokens_output = result.tool_usage.completion_tokens + final_usage.completion_tokens
                tokens = {"prompt": tokens_prompt, "output": tokens_output}
                yield _sse(
                    "done",
                    {"latency_ms": int((time.monotonic() - start) * 1000), "tokens": tokens},
                )
        except Exception as e:  # noqa: BLE001 —— 流中出错也要给用户可理解提示（M2），详情写日志不下发
            error_msg = str(e)[:500]
            logger.exception("ask stream failed")
            yield _sse("error", {"message": "抱歉，服务暂时不可用，请稍后再试"})
        finally:
            # 无论成败 / 是否被客户端中断，都异步落日志（N4、T4-3）
            qa_log_service.write_log_async(
                question=question,
                used_retrieval=used_retrieval,
                hit_chunks=hit_chunks,
                answer="".join(answer_parts),
                latency_ms=int((time.monotonic() - start) * 1000),
                tokens_prompt=tokens_prompt,
                tokens_output=tokens_output,
                error=error_msg,
            )

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/presets")
def presets(db: Session = Depends(get_db)) -> list[str]:
    from app.models import Setting

    row = db.get(Setting, "preset_questions")
    return row.value if row and isinstance(row.value, list) else []
