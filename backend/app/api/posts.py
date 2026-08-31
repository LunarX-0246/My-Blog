"""文章接口（技术方案 §5.3）：公开读 + 博主写。

读接口公开（仅返回已发布）；写接口用 dependencies 统一鉴权。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_admin
from app.schemas import PostDetail, PostListResponse, PostWrite, SummaryResponse
from app.services import post_service

router = APIRouter(prefix="/api/posts", tags=["posts"])


@router.get("", response_model=PostListResponse)
def list_posts(
    category: str | None = None,
    tag: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PostListResponse:
    items, total = post_service.list_published(db, category, tag, page, page_size)
    return PostListResponse(items=items, total=total)


@router.get("/{slug}", response_model=PostDetail)
def get_post(slug: str, db: Session = Depends(get_db)) -> PostDetail:
    return post_service.to_detail(post_service.get_published_by_slug(db, slug))


@router.post(
    "", response_model=PostDetail, status_code=201,
    dependencies=[Depends(get_current_admin)],
)
def create_post(body: PostWrite, db: Session = Depends(get_db)) -> PostDetail:
    return post_service.to_detail(post_service.create_post(db, body))


@router.put(
    "/{post_id}", response_model=PostDetail,
    dependencies=[Depends(get_current_admin)],
)
def update_post(post_id: int, body: PostWrite, db: Session = Depends(get_db)) -> PostDetail:
    post = post_service.get_by_id(db, post_id)
    return post_service.to_detail(post_service.update_post(db, post, body))


@router.post(
    "/{post_id}/publish", response_model=PostDetail,
    dependencies=[Depends(get_current_admin)],
)
def publish_post(post_id: int, db: Session = Depends(get_db)) -> PostDetail:
    post = post_service.get_by_id(db, post_id)
    return post_service.to_detail(post_service.publish(db, post))


@router.post(
    "/{post_id}/unpublish", response_model=PostDetail,
    dependencies=[Depends(get_current_admin)],
)
def unpublish_post(post_id: int, db: Session = Depends(get_db)) -> PostDetail:
    post = post_service.get_by_id(db, post_id)
    return post_service.to_detail(post_service.unpublish(db, post))


@router.post(
    "/{post_id}/summary", response_model=SummaryResponse,
    dependencies=[Depends(get_current_admin)],
)
def generate_summary(post_id: int, db: Session = Depends(get_db)) -> SummaryResponse:
    post = post_service.get_by_id(db, post_id)
    return SummaryResponse(summary=post_service.generate_summary(db, post))


@router.delete(
    "/{post_id}", dependencies=[Depends(get_current_admin)],
)
def delete_post(post_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    post = post_service.get_by_id(db, post_id)
    post_service.delete_post(db, post)
    return {"ok": True}
