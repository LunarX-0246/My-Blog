"""管理端接口：文章列表/详情、索引管理；站点设置随后续阶段加入。

整组路由统一鉴权（``dependencies``），管理端任何接口都要求登录（NFR-SEC-05）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import get_current_admin
from app.errors import ApiError
from app.models import Document, IndexStatus, IndexTask, Post, PostStatus
from app.rag.store import get_store
from app.schemas import PostDetail, PostListItem
from app.services import index_service, post_service

router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
    dependencies=[Depends(get_current_admin)],
)


@router.get("/posts", response_model=list[PostListItem])
def admin_list_posts(
    status: PostStatus | None = Query(None), db: Session = Depends(get_db)
) -> list[PostListItem]:
    return post_service.list_admin(db, status)


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
        "model": settings.embedding_model,
        "dim": settings.embedding_dim,
        "last_indexed_at": last,
    }


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
