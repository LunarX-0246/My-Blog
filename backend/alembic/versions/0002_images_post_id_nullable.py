"""图片 post_id 改为可空：上传发生在文章保存之前（新建时文章尚不存在）。

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-31

上传时 post_id 为 NULL，文章保存时再把正文引用的图片关联到文章（见 post_service）。
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("images", "post_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    op.alter_column("images", "post_id", existing_type=sa.Integer(), nullable=False)
