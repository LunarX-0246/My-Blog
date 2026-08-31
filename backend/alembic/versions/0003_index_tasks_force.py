"""index_tasks 增加 force 列（R1：全量重建标记持久化，崩溃恢复后不退化）。

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-01

背景：全量重建（换 embedding 模型）时，若处理到一半进程崩溃，重启后
_recover_pending 之前把 force 写死 False，剩余源会退化为增量（文本未变→指纹未变→
复用旧模型向量），导致索引里新旧模型向量混杂且无报错。持久化 force 后恢复即正确。
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "index_tasks",
        sa.Column("force", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("index_tasks", "force")
