"""知识库文档接口（技术方案 §5.4）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import get_current_admin
from app.errors import ApiError
from app.schemas import DocDirNode, DocumentDetail, DocumentOut, DocumentUpdate
from app.services import doc_service

router = APIRouter(prefix="/api/docs", tags=["docs"])


@router.get("/tree", response_model=DocDirNode)
def get_tree(db: Session = Depends(get_db)) -> DocDirNode:
    return doc_service.build_tree(db)


@router.get("", response_model=list[DocumentOut])
def list_docs(
    dir: str | None = None,
    format: str | None = None,
    tag: str | None = None,
    db: Session = Depends(get_db),
) -> list[DocumentOut]:
    return doc_service.list_documents(db, dir, format, tag)


@router.get("/{doc_id}", response_model=DocumentDetail)
def get_doc(doc_id: int, db: Session = Depends(get_db)) -> DocumentDetail:
    doc = doc_service.get_document(db, doc_id)
    return DocumentDetail(
        **DocumentOut.model_validate(doc).model_dump(),
        parsed_text=doc.parsed_text,
        tag_ids=[t.id for t in doc.tags],
    )


@router.get("/{doc_id}/raw")
def get_doc_raw(doc_id: int, db: Session = Depends(get_db)) -> FileResponse:
    doc = doc_service.get_document(db, doc_id)
    path = settings.uploads_dir / doc.stored_name
    if not path.is_file():
        raise ApiError(404, "not_found", "原始文件不存在")
    # 下载时用原始文件名（FR-VIEW-21），带 filename* 以正确处理中文
    return FileResponse(
        path,
        filename=doc.original_name,
        media_type="application/octet-stream",
    )


@router.post("", response_model=DocumentDetail, dependencies=[Depends(get_current_admin)])
async def upload_doc(
    file: UploadFile = File(...),
    dir_path: str = Form(""),
    title: str = Form(""),
    description: str = Form(""),
    tag_ids: str = Form(""),
    on_conflict: str = Form("error"),
    db: Session = Depends(get_db),
) -> DocumentDetail:
    data = await file.read()
    tags = [int(x) for x in tag_ids.split(",") if x.strip()]
    doc = doc_service.upload_document(
        db,
        filename=file.filename or "",
        data=data,
        dir_path=dir_path,
        title=title,
        description=description,
        tag_ids=tags,
        on_conflict=on_conflict,
    )
    return DocumentDetail(
        **DocumentOut.model_validate(doc).model_dump(),
        parsed_text=doc.parsed_text,
        tag_ids=[t.id for t in doc.tags],
    )


@router.patch(
    "/{doc_id}", response_model=DocumentDetail, dependencies=[Depends(get_current_admin)]
)
def update_doc(
    doc_id: int, body: DocumentUpdate, db: Session = Depends(get_db)
) -> DocumentDetail:
    doc = doc_service.get_document(db, doc_id)
    doc = doc_service.update_document(
        db,
        doc,
        title=body.title,
        dir_path=body.dir_path,
        description=body.description,
        tag_ids=body.tag_ids,
    )
    return DocumentDetail(
        **DocumentOut.model_validate(doc).model_dump(),
        parsed_text=doc.parsed_text,
        tag_ids=[t.id for t in doc.tags],
    )


@router.delete("/{doc_id}", dependencies=[Depends(get_current_admin)])
def delete_doc(doc_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    doc = doc_service.get_document(db, doc_id)
    doc_service.delete_document(db, doc)
    return {"ok": True}
