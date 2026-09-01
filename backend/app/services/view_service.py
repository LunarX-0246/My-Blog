"""浏览次数计数（FR-STAT-01）。

文章 / 文档详情页每次被浏览时 ``view_count`` 加 1。

- 异步写：后台线程用独立 Session 执行一条原子 ``UPDATE ... SET view_count = view_count + 1``，
  立即返回，不阻塞页面响应（红线「计数不得拖慢页面响应」）。
- 与 ``qa_log_service`` 的异步写库是同一套模式（N4 精神：写库失败不应影响主流程），
  这里同样用 daemon 线程，失败静默丢弃——浏览计数是弱一致指标，不值得为它拖慢或报错。
- 计数只针对前台公开详情接口，管理端预览 / 列表不计数（走的是 ``/api/admin/...`` 与列表接口）。
"""
from __future__ import annotations

import threading

from sqlalchemy import update

from app.db import SessionLocal
from app.models import Document, Post


def _increment(src_type: str, src_id: int) -> None:
    """在独立 Session 里原子 +1。``view_count = view_count + 1`` 是 SQL 表达式，
    由数据库保证并发安全，不会出现读改写竞态丢计数。"""
    model = Post if src_type == "post" else Document
    with SessionLocal() as db:
        db.execute(
            update(model).where(model.id == src_id).values(view_count=model.view_count + 1)
        )
        db.commit()


def increment_view(src_type: str, src_id: int) -> None:
    """异步 +1 计数，立即返回。src_type 取 ``post`` / ``document``。"""
    threading.Thread(target=_increment, args=(src_type, src_id), daemon=True).start()
