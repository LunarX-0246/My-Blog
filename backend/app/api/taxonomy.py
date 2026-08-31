"""分类与标签接口。列表公开（供归档筛选），新建需登录（FR-POST-16）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_admin
from app.schemas import CategoryCreate, CategoryOut, TagCreate, TagOut
from app.services import taxonomy_service

router = APIRouter(prefix="/api", tags=["taxonomy"])


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)) -> list[CategoryOut]:
    return taxonomy_service.list_categories(db)


@router.get("/tags", response_model=list[TagOut])
def list_tags(db: Session = Depends(get_db)) -> list[TagOut]:
    return taxonomy_service.list_tags(db)


@router.post(
    "/categories", response_model=CategoryOut, status_code=201,
    dependencies=[Depends(get_current_admin)],
)
def create_category(body: CategoryCreate, db: Session = Depends(get_db)) -> CategoryOut:
    return taxonomy_service.create_category(db, body.name)


@router.post(
    "/tags", response_model=TagOut, status_code=201,
    dependencies=[Depends(get_current_admin)],
)
def create_tag(body: TagCreate, db: Session = Depends(get_db)) -> TagOut:
    return taxonomy_service.create_tag(db, body.name)
