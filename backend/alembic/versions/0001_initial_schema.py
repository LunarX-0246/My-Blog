"""初始建表：技术方案 §4.2 全部表结构。

Revision ID: 0001
Revises:
Create Date: 2026-08-31

说明：本迁移手写（而非 autogenerate），原因是 §4.2 里的三个 PostgreSQL 枚举类型、
``CREATE EXTENSION vector`` 与 HNSW 索引都不是 autogenerate 能可靠生成的，
手写能确保 DDL 与文档逐字一致。
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# 复用同名枚举对象，create_type=False：类型已在下方显式 CREATE TYPE 创建。
index_status = postgresql.ENUM(
    "pending", "queued", "running", "indexed", "failed",
    name="index_status", create_type=False,
)
source_type = postgresql.ENUM(
    "post", "document", name="source_type", create_type=False,
)
post_status = postgresql.ENUM(
    "draft", "published", name="post_status", create_type=False,
)


def upgrade() -> None:
    # 向量扩展：整个检索能力的地基（RAG-RETR-01）
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 三个枚举类型（与 §4.2 的 CREATE TYPE 一致）
    op.execute("CREATE TYPE index_status AS ENUM ('pending','queued','running','indexed','failed')")
    op.execute("CREATE TYPE source_type AS ENUM ('post','document')")
    op.execute("CREATE TYPE post_status AS ENUM ('draft','published')")

    # ── 分类与标签 ──────────────────────────────────────
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── 文章 ────────────────────────────────────────────
    op.create_table(
        "posts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False, unique=True),
        sa.Column("summary", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("content_md", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", post_status, nullable=False, server_default=sa.text("'draft'")),
        sa.Column("is_featured", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("read_minutes", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("idx_status", index_status, nullable=False, server_default=sa.text("'pending'")),
        sa.Column("idx_error", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("posts_status_pub_idx", "posts", ["status", sa.text("published_at DESC")])

    op.create_table(
        "post_tags",
        sa.Column("post_id", sa.Integer(), sa.ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", sa.Integer(), sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    )

    # ── 知识库文档 ──────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("stored_name", sa.String(64), nullable=False, unique=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("dir_path", sa.String(512), nullable=False, server_default=sa.text("''")),
        sa.Column("description", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("file_format", sa.String(16), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("parsed_text", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("idx_status", index_status, nullable=False, server_default=sa.text("'pending'")),
        sa.Column("idx_error", sa.Text(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("documents_dir_idx", "documents", ["dir_path"])

    op.create_table(
        "document_tags",
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", sa.Integer(), sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    )

    # ── 块（检索单元）★ 全系统核心表 ────────────────────
    op.create_table(
        "chunks",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("src_type", source_type, nullable=False),
        sa.Column("src_id", sa.Integer(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("context_prefix", sa.Text(), nullable=False),
        sa.Column("embed_text", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.CHAR(64), nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=True),
        sa.Column("anchor", sa.String(255), nullable=True),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("src_type", "src_id", "seq", name="uq_chunks_src_seq"),
    )
    op.create_index("chunks_src_idx", "chunks", ["src_type", "src_id"])
    op.create_index("chunks_fp_idx", "chunks", ["fingerprint"])
    # HNSW 向量索引（小数据量下 PG 可能仍走顺序扫描，属正常，见技术方案 §12）
    op.execute(
        "CREATE INDEX chunks_embedding_idx ON chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    # ── 文章配图 ────────────────────────────────────────
    op.create_table(
        "images",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stored_name", sa.String(64), nullable=False, unique=True),
        sa.Column("post_id", sa.Integer(), sa.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── 索引任务 ────────────────────────────────────────
    op.create_table(
        "index_tasks",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("src_type", source_type, nullable=False),
        sa.Column("src_id", sa.Integer(), nullable=False),
        sa.Column("status", index_status, nullable=False, server_default=sa.text("'queued'")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("chunk_total", sa.Integer(), nullable=True),
        sa.Column("chunk_new", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("index_tasks_status_idx", "index_tasks", ["status", "created_at"])

    # ── 站点设置（预设问题、限流阈值等）──────────────────
    op.create_table(
        "settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", postgresql.JSONB(), nullable=False),
    )

    # ── 问答日志（二期，一期先建表）─────────────────────
    op.create_table(
        "qa_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("used_retrieval", sa.Boolean(), nullable=False),
        sa.Column("hit_chunks", postgresql.JSONB(), nullable=True),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("tokens_prompt", sa.Integer(), nullable=True),
        sa.Column("tokens_output", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("qa_logs")
    op.drop_table("settings")
    op.drop_table("index_tasks")
    op.drop_table("images")
    op.drop_table("chunks")
    op.drop_table("document_tags")
    op.drop_table("documents")
    op.drop_table("post_tags")
    op.drop_table("posts")
    op.drop_table("tags")
    op.drop_table("categories")

    op.execute("DROP TYPE post_status")
    op.execute("DROP TYPE source_type")
    op.execute("DROP TYPE index_status")
    op.execute("DROP EXTENSION vector")
