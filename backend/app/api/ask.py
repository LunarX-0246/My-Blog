"""AI 问答接口（技术方案 §5.5）。

SSE 流式；事件顺序：status → sources（★ 必须先于 delta，A4）→ delta → done。
访客无需登录（FR-ASK-03）；服务端无状态，历史由前端传入（R9）。
"""
from __future__ import annotations

import json
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
from app.services import ratelimit

router = APIRouter(prefix="/api/ask", tags=["ask"])


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
        yield _sse("status", {"stage": "deciding"})
        # 用独立会话，避免请求会话在流式期间被关闭
        with SessionLocal() as s:
            result = agent.run_agent(s, question, history, base_flt)

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

            if result.used_retrieval:
                yield _sse("status", {"stage": "retrieving"})
                # ★ sources 必须先于 delta 下发（A4）
                yield _sse("sources", {"used_retrieval": True, "sources": source_list})
            else:
                yield _sse("sources", {"used_retrieval": False, "sources": []})

            # 两条路径统一流式输出（H2），不再整段 yield
            for delta in llm.stream_chat(result.final_messages):
                yield _sse("delta", {"text": delta})
            yield _sse("done", {"latency_ms": int((time.monotonic() - start) * 1000)})

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/presets")
def presets(db: Session = Depends(get_db)) -> list[str]:
    from app.models import Setting

    row = db.get(Setting, "preset_questions")
    return row.value if row and isinstance(row.value, list) else []
