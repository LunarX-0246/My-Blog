"""SQLAlchemy ORM 表模型（技术方案 §4.2）。

设计要点（评审会重点核对，勿改）：
- ``chunks`` 用 ``src_type + src_id`` 做多态关联，**不建外键**，也不拆成两张块表
  —— 检索时必须一次查询全部块（RAG-RETR-01）。
- ``chunks.fingerprint`` 是增量索引的依据，取 sha256(context_prefix + content)。
- ``chunks.embed_text`` 是实际送去向量化的文本 = 前缀 + 换行 + 正文，单独存一列
  方便排查「为什么这个块召回不对」。
- ``documents.dir_path`` 是逻辑路径字符串，不是物理目录。
- ``documents.stored_name`` 是系统生成的唯一名，原始文件名仅作记录与下载用。
"""
from __future__ import annotations

import enum
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """所有 ORM 模型的基类，其 metadata 供 Alembic 迁移使用。"""


# ── PostgreSQL 枚举类型（与迁移里 CREATE TYPE 的名字一一对应）──────────────

class IndexStatus(str, enum.Enum):
    pending = "pending"    # 未索引
    queued = "queued"      # 排队中
    running = "running"    # 索引中
    indexed = "indexed"    # 已索引
    failed = "failed"      # 失败


class SourceType(str, enum.Enum):
    post = "post"
    document = "document"


class PostStatus(str, enum.Enum):
    draft = "draft"
    published = "published"


# 复用同一批类型对象，保证多个表里同名枚举引用一致。
index_status_enum = Enum(IndexStatus, name="index_status", native_enum=True)
source_type_enum = Enum(SourceType, name="source_type", native_enum=True)
post_status_enum = Enum(PostStatus, name="post_status", native_enum=True)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    posts: Mapped[list["Post"]] = relationship(back_populates="category")


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    posts: Mapped[list["Post"]] = relationship(
        secondary="post_tags", back_populates="tags"
    )
    documents: Mapped[list["Document"]] = relationship(
        secondary="document_tags", back_populates="tags"
    )


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    content_md: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[PostStatus] = mapped_column(
        post_status_enum, nullable=False, server_default=text("'draft'")
    )
    is_featured: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    read_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    view_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    idx_status: Mapped[IndexStatus] = mapped_column(
        index_status_enum, nullable=False, server_default=text("'pending'")
    )
    idx_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    category: Mapped["Category | None"] = relationship(back_populates="posts")
    tags: Mapped[list["Tag"]] = relationship(
        secondary="post_tags", back_populates="posts"
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    dir_path: Mapped[str] = mapped_column(String(512), nullable=False, server_default=text("''"))
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    file_format: Mapped[str] = mapped_column(String(16), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parsed_text: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    view_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    idx_status: Mapped[IndexStatus] = mapped_column(
        index_status_enum, nullable=False, server_default=text("'pending'")
    )
    idx_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tags: Mapped[list["Tag"]] = relationship(
        secondary="document_tags", back_populates="documents"
    )


class Chunk(Base):
    """检索的最小单元，全系统核心表。

    ``embedding`` 维度固定 1024（技术方案 §4.2 ``vector(1024)``）。
    """

    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("src_type", "src_id", "seq", name="uq_chunks_src_seq"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    src_type: Mapped[SourceType] = mapped_column(source_type_enum, nullable=False)
    src_id: Mapped[int] = mapped_column(Integer, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    context_prefix: Mapped[str] = mapped_column(Text, nullable=False)
    embed_text: Mapped[str] = mapped_column(Text, nullable=False)
    fingerprint: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    anchor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    embedding: Mapped[object | None] = mapped_column(Vector(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Image(Base):
    __tablename__ = "images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stored_name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    post_id: Mapped[int] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), nullable=False
    )
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IndexTask(Base):
    __tablename__ = "index_tasks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    src_type: Mapped[SourceType] = mapped_column(source_type_enum, nullable=False)
    src_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[IndexStatus] = mapped_column(
        index_status_enum, nullable=False, server_default=text("'queued'")
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_new: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)


class QaLog(Base):
    """问答日志（二期交付，一期先建表）。"""

    __tablename__ = "qa_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    used_retrieval: Mapped[bool] = mapped_column(Boolean, nullable=False)
    hit_chunks: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_prompt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_output: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
