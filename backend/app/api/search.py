"""全站搜索接口（FR-SEARCH-01~05）。公开，无需登录。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import SearchResult
from app.services import search_service

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("", response_model=list[SearchResult])
def search(
    q: str = Query(..., min_length=1, description="关键词"),
    type: str | None = Query(None, description="来源类型 post/document"),
    tag: str | None = Query(None, description="标签 slug"),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
) -> list[SearchResult]:
    return search_service.search(db, q, src_type=type, tag=tag, limit=limit)
