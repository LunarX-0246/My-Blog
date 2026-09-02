"""管理端接口：文章列表/详情、索引管理；站点设置随后续阶段加入。

整组路由统一鉴权（``dependencies``），管理端任何接口都要求登录（NFR-SEC-05）。
"""
from __future__ import annotations

from datetime import date, datetime, time

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import get_current_admin
from app.errors import ApiError
from app.models import Document, IndexStatus, IndexTask, Post, PostStatus, Setting
from app.rag.store import get_store
from app.schemas import (
    PostDetail,
    PostListItem,
    QaLogListResponse,
    QaLogStats,
    SettingsUpdate,
)
from app.services import index_service, post_service, qa_log_service

router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
    dependencies=[Depends(get_current_admin)],
)


@router.get("/posts", response_model=list[PostListItem])
def admin_list_posts(
    status: PostStatus | None = Query(None),
    sort: str = Query("updated"),
    db: Session = Depends(get_db),
) -> list[PostListItem]:
    return post_service.list_admin(db, status, sort)


@router.get("/posts/{post_id}", response_model=PostDetail)
def admin_get_post(post_id: int, db: Session = Depends(get_db)) -> PostDetail:
    return post_service.to_detail(post_service.get_by_id(db, post_id))


@router.get("/index/status")
def index_status(db: Session = Depends(get_db)) -> dict:
    """全部内容的索引状态 + 统计（FR-IDX-04、FR-IDX-07）。"""
    posts = db.scalars(select(Post).order_by(Post.updated_at.desc())).all()
    docs = db.scalars(select(Document).order_by(Document.uploaded_at.desc())).all()
    stats = get_store().stats(db)
    last = db.scalar(
        select(func.max(IndexTask.finished_at)).where(IndexTask.status == IndexStatus.indexed)
    )
    token_row = db.get(Setting, "embedding_tokens")
    embedding_tokens = int(token_row.value.get("total", 0)) if token_row and isinstance(token_row.value, dict) else 0
    return {
        "posts": [
            {"id": p.id, "title": p.title, "idx_status": p.idx_status.value, "idx_error": p.idx_error}
            for p in posts
        ],
        "documents": [
            {"id": d.id, "title": d.title, "idx_status": d.idx_status.value, "idx_error": d.idx_error}
            for d in docs
        ],
        "total_chunks": stats.total_chunks,
        # 孤儿块：源内容已删除但块仍留在索引里。正常应为 0；不为 0 时
        # 检索会命中已不存在的内容且不报任何错，只能靠这里主动暴露
        "orphan_chunks": index_service.count_orphan_chunks(db),
        "model": settings.embedding_model,
        "dim": settings.embedding_dim,
        "embedding_tokens": embedding_tokens,
        "last_indexed_at": last,
    }


@router.post("/index/purge-orphans")
def purge_orphans() -> dict[str, int]:
    """清除孤儿块（源内容已删除、却残留在索引中的块）。"""
    return {"purged": index_service.purge_orphan_chunks()}


@router.post("/index/retry/{src_type}/{src_id}")
def retry_index(src_type: str, src_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    if src_type not in ("post", "document"):
        raise ApiError(400, "bad_request", "未知的内容类型")
    index_service.enqueue(src_type, src_id)
    return {"ok": True}


@router.post("/index/rebuild")
def rebuild_index(db: Session = Depends(get_db)) -> dict[str, int]:
    queued = index_service.rebuild_all()
    return {"queued": queued}


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)) -> dict:
    presets = db.get(Setting, "preset_questions")
    limits = db.get(Setting, "ask_limits")
    return {
        "presets": presets.value if presets and isinstance(presets.value, list) else [],
        "limits": limits.value if limits and isinstance(limits.value, dict) else None,
    }


@router.put("/settings")
def update_settings(body: SettingsUpdate, db: Session = Depends(get_db)) -> dict[str, bool]:
    def upsert(key: str, value: object) -> None:
        row = db.get(Setting, key)
        if row:
            row.value = value
        else:
            db.add(Setting(key=key, value=value))

    if body.presets is not None:
        upsert("preset_questions", body.presets)
    if body.limits is not None:
        upsert("ask_limits", body.limits)
    db.commit()
    return {"ok": True}


@router.get("/qa-logs", response_model=QaLogListResponse)
def list_qa_logs(
    used_retrieval: bool | None = Query(None),
    has_error: bool | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> QaLogListResponse:
    # ★ 按**本机时区**切日界，不能按 UTC。
    #   created_at 存的是 UTC，而博主在管理页选的是自己日历上的日期。
    #   若把这个日期当成 UTC 日（replace(tzinfo=utc)），东八区下选「今天」会漏掉
    #   本地当天 00:00–08:00 的全部记录 —— 早上刚问过的几条筛不出来，
    #   而界面上不会有任何提示，只会显示「暂无数据」。
    #   astimezone() 作用在 naive datetime 上时，正是按本机时区解释再补上偏移。
    df = datetime.combine(date_from, time.min).astimezone() if date_from else None
    dt = datetime.combine(date_to, time.max).astimezone() if date_to else None
    items, total = qa_log_service.list_logs(
        db,
        used_retrieval=used_retrieval,
        has_error=has_error,
        date_from=df,
        date_to=dt,
        page=page,
        page_size=page_size,
    )
    return QaLogListResponse(items=items, total=total)


@router.get("/qa-logs/stats", response_model=QaLogStats)
def qa_log_stats(db: Session = Depends(get_db)) -> QaLogStats:
    return QaLogStats(**qa_log_service.stats(db))
