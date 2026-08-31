"""管理端接口：文章列表/详情；索引管理、站点设置随后续阶段加入。

整组路由统一鉴权（``dependencies``），管理端任何接口都要求登录（NFR-SEC-05）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_admin
from app.models import PostStatus
from app.schemas import PostDetail, PostListItem
from app.services import post_service

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
