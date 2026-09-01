"""知识库文档业务逻辑（FR-DOC-01~18）。

- 上传：校验格式/大小、系统生成唯一存储名（D2）、同名处理（覆盖/另存）
- 解析：PDF 按页（R2）、Markdown 原样、txt 纯文本
- 目录树：由 dir_path 现推（D3，逻辑目录，非物理目录）
- 删除：级联清理块与原始文件（FR-DOC-16）
"""
from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.errors import ApiError
from app.models import Chunk, Document, IndexStatus, SourceType, Tag
from app.rag import parser
from app.rag.retriever import invalidate_bm25
from app.schemas import DocDirNode, DocumentOut
from app.services import ask_cache, index_service

# 扩展名 -> file_format
_ALLOWED = {".pdf": "pdf", ".md": "markdown", ".markdown": "markdown", ".txt": "txt"}


def _save_file(stored_name: str, data: bytes) -> None:
    uploads_dir = settings.uploads_dir
    uploads_dir.mkdir(parents=True, exist_ok=True)
    (uploads_dir / stored_name).write_bytes(data)


def _load_full(db: Session, doc_id: int) -> Document:
    return db.execute(
        select(Document).options(selectinload(Document.tags)).where(Document.id == doc_id)
    ).scalar_one()


def _assign_tags(db: Session, doc: Document, tag_ids: list[int]) -> None:
    if tag_ids:
        doc.tags = list(db.scalars(select(Tag).where(Tag.id.in_(tag_ids))).all())
    else:
        doc.tags = []


def _unique_title(db: Session, dir_path: str, title: str) -> str:
    n = 2
    candidate = title
    while db.scalar(
        select(Document.id).where(Document.dir_path == dir_path, Document.title == candidate)
    ):
        candidate = f"{title} ({n})"
        n += 1
    return candidate


def _parse(file_format: str, data: bytes) -> tuple[str, int | None]:
    if file_format == "pdf":
        pages = parser.parse_pdf(data)
        return "\n\n".join(t for _, t in pages), len(pages)
    return data.decode("utf-8", errors="replace"), None


def upload_document(
    db: Session,
    *,
    filename: str,
    data: bytes,
    dir_path: str,
    title: str,
    description: str,
    tag_ids: list[int],
    on_conflict: str = "error",
) -> Document:
    ext = Path(filename).suffix.lower()
    fmt = _ALLOWED.get(ext)
    if fmt is None:
        raise ApiError(400, "bad_format", "仅支持 PDF / Markdown / txt 三种格式")
    if not data:
        raise ApiError(400, "empty_file", "文件内容为空")
    if len(data) > settings.upload_max_mb * 1024 * 1024:
        raise ApiError(413, "too_large", f"文件大小不能超过 {settings.upload_max_mb} MB")

    title = (title or Path(filename).stem).strip() or "未命名"
    dir_path = (dir_path or "").strip()
    parsed_text, page_count = _parse(fmt, data)

    existing = db.scalar(
        select(Document).where(Document.dir_path == dir_path, Document.title == title)
    )
    if existing and on_conflict == "error":
        raise ApiError(409, "name_conflict", "同目录下已存在同名文档")
    if existing and on_conflict == "rename":
        title = _unique_title(db, dir_path, title)

    if existing and on_conflict == "overwrite":
        doc = existing
        doc.original_name = filename
        doc.file_format = fmt
        doc.file_size = len(data)
        doc.page_count = page_count
        doc.parsed_text = parsed_text
        doc.description = description
        doc.idx_status = IndexStatus.pending
        doc.idx_error = None
        _save_file(doc.stored_name, data)  # 覆盖内容，存储名不变（不可更改）
        _assign_tags(db, doc, tag_ids)
        db.commit()
        index_service.enqueue("document", doc.id)
        return _load_full(db, doc.id)

    stored_name = uuid.uuid4().hex + ext
    _save_file(stored_name, data)
    doc = Document(
        original_name=filename,
        stored_name=stored_name,
        title=title,
        dir_path=dir_path,
        description=description,
        file_format=fmt,
        file_size=len(data),
        page_count=page_count,
        parsed_text=parsed_text,
        idx_status=IndexStatus.pending,
    )
    _assign_tags(db, doc, tag_ids)
    db.add(doc)
    db.commit()
    index_service.enqueue("document", doc.id)
    return _load_full(db, doc.id)


def get_document(db: Session, doc_id: int) -> Document:
    doc = db.execute(
        select(Document).options(selectinload(Document.tags)).where(Document.id == doc_id)
    ).scalar_one_or_none()
    if not doc:
        raise ApiError(404, "not_found", "文档不存在")
    return doc


def list_documents(
    db: Session,
    dir_path: str | None = None,
    file_format: str | None = None,
    tag_slug: str | None = None,
) -> list[Document]:
    stmt = select(Document).options(selectinload(Document.tags))
    if dir_path is not None:
        stmt = stmt.where(Document.dir_path == dir_path)
    if file_format:
        stmt = stmt.where(Document.file_format == file_format)
    if tag_slug:
        stmt = stmt.join(Document.tags).where(Tag.slug == tag_slug)
    return list(db.scalars(stmt.order_by(Document.title)).all())


def update_document(
    db: Session,
    doc: Document,
    *,
    title: str | None = None,
    dir_path: str | None = None,
    description: str | None = None,
    tag_ids: list[int] | None = None,
) -> Document:
    if title is not None and title.strip() != doc.title:
        new_title = title.strip() or "未命名"
        if db.scalar(
            select(Document.id).where(
                Document.dir_path == doc.dir_path,
                Document.title == new_title,
                Document.id != doc.id,
            )
        ):
            raise ApiError(409, "name_conflict", "同目录下已存在同名文档")
        doc.title = new_title
    if dir_path is not None:
        doc.dir_path = dir_path.strip()
        if db.scalar(
            select(Document.id).where(
                Document.dir_path == doc.dir_path,
                Document.title == doc.title,
                Document.id != doc.id,
            )
        ):
            raise ApiError(409, "name_conflict", "目标目录下已存在同名文档")
    if description is not None:
        doc.description = description
    if tag_ids is not None:
        _assign_tags(db, doc, tag_ids)
    # 目录路径会作为检索上下文的一部分，移动后需重新索引（FR-DOC-15）
    doc.idx_status = IndexStatus.pending
    db.commit()
    index_service.enqueue("document", doc.id)
    return _load_full(db, doc.id)


def delete_document(db: Session, doc: Document) -> None:
    stored_name = doc.stored_name
    # 块是多态关联（无外键），需手动删除
    db.execute(
        delete(Chunk).where(Chunk.src_type == SourceType.document, Chunk.src_id == doc.id)
    )
    # 删除文档：FK 级联删除 document_tags
    db.delete(doc)
    db.commit()
    invalidate_bm25()
    ask_cache.clear()
    # 删除原始文件
    (settings.uploads_dir / stored_name).unlink(missing_ok=True)


def build_tree(db: Session) -> DocDirNode:
    """由所有 dir_path 现推目录树（FR-DOC-11：不存在空目录）。"""
    docs = list(
        db.scalars(
            select(Document).options(selectinload(Document.tags)).order_by(Document.title)
        ).all()
    )
    root = DocDirNode(name="", path="", dirs=[], documents=[])
    path_to_node: dict[str, DocDirNode] = {"": root}
    for doc in docs:
        if not doc.dir_path:
            root.documents.append(DocumentOut.model_validate(doc))
            continue
        parts = [p for p in doc.dir_path.split("/") if p]
        cur_path = ""
        parent = root
        for part in parts:
            prev = cur_path
            cur_path = f"{prev}/{part}" if prev else part
            node = path_to_node.get(cur_path)
            if node is None:
                node = DocDirNode(name=part, path=cur_path, dirs=[], documents=[])
                parent.dirs.append(node)
                path_to_node[cur_path] = node
            parent = node
        parent.documents.append(DocumentOut.model_validate(doc))
    return root
