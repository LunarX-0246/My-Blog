"""知识库文档接口（技术方案 §5.4）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import get_current_admin
from app.errors import ApiError
from app.models import Chunk, SourceType
from app.schemas import DocChunk, DocDirNode, DocumentDetail, DocumentOut, DocumentUpdate
from app.services import doc_service, view_service

router = APIRouter(prefix="/api/docs", tags=["docs"])


@router.get("/tree", response_model=DocDirNode)
def get_tree(db: Session = Depends(get_db)) -> DocDirNode:
    return doc_service.build_tree(db)


@router.get("", response_model=list[DocumentOut])
def list_docs(
    dir: str | None = None,
    format: str | None = None,
    tag: str | None = None,
    sort: str = Query("title"),
    db: Session = Depends(get_db),
) -> list[DocumentOut]:
    return doc_service.list_documents(db, dir, format, tag, sort)


@router.get("/{doc_id}", response_model=DocumentDetail)
def get_doc(doc_id: int, db: Session = Depends(get_db)) -> DocumentDetail:
    doc = doc_service.get_document(db, doc_id)
    # 浏览计数：后台线程异步 +1，不阻塞响应（FR-STAT-01）
    view_service.increment_view("document", doc.id)
    chunks = db.scalars(
        select(Chunk)
        .where(Chunk.src_type == SourceType.document, Chunk.src_id == doc_id)
        .order_by(Chunk.seq)
    ).all()
    return DocumentDetail(
        **DocumentOut.model_validate(doc).model_dump(),
        parsed_text=doc.parsed_text,
        tag_ids=[t.id for t in doc.tags],
        chunks=[DocChunk(seq=c.seq, content=c.content, page_no=c.page_no, anchor=c.anchor) for c in chunks],
    )


# 原始文件的 MIME 类型。PDF 必须是 application/pdf，浏览器才会内联渲染；
# 用 application/octet-stream 会被当成二进制流直接触发下载。
_RAW_MEDIA_TYPE = {
    "pdf": "application/pdf",
    "markdown": "text/markdown; charset=utf-8",
    "txt": "text/plain; charset=utf-8",
}


@router.get("/{doc_id}/raw")
def get_doc_raw(
    doc_id: int,
    download: int = Query(0, description="1=作为附件下载；0=内联展示（默认）"),
    db: Session = Depends(get_db),
) -> FileResponse:
    """原始文件。

    两种用途共用一个端点，靠 ``download`` 区分：

    - **内联展示**（默认）：PDF 原文视图用 iframe 嵌入浏览器内置阅读器，
      必须返回 ``application/pdf`` 且**不带 filename**，否则会被
      ``Content-Disposition: attachment`` 强制成下载，页面上什么都看不到。
    - **下载**（``?download=1``）：带原始文件名（FR-VIEW-23），
      FileResponse 会自动补 ``filename*`` 以正确处理中文名。
    """
    doc = doc_service.get_document(db, doc_id)
    path = settings.uploads_dir / doc.stored_name
    if not path.is_file():
        raise ApiError(404, "not_found", "原始文件不存在")
    media_type = _RAW_MEDIA_TYPE.get(doc.file_format, "application/octet-stream")
    if download:
        return FileResponse(path, filename=doc.original_name, media_type=media_type)
    return FileResponse(path, media_type=media_type)


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
