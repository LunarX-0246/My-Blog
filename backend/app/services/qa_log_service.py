"""问答日志（FR-LOG-01~05）。

- 异步写入：后台线程写库，不阻塞 SSE 响应（N4），写库失败不影响问答。
- 不记录 IP / User-Agent 等可定位访客身份的信息（N3 / FR-LOG-05）——本服务只收
  question / used_retrieval / hit_chunks / answer / 耗时 / token / error，一律不含身份字段。
"""
from __future__ import annotations

import threading
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import QaLog


def _write(
    *,
    question: str,
    used_retrieval: bool,
    hit_chunks: list | None,
    answer: str,
    latency_ms: int,
    tokens_prompt: int,
    tokens_output: int,
    error: str | None = None,
) -> None:
    with SessionLocal() as db:
        db.add(
            QaLog(
                question=question,
                used_retrieval=used_retrieval,
                hit_chunks=hit_chunks,
                answer=answer,
                latency_ms=latency_ms,
                tokens_prompt=tokens_prompt,
                tokens_output=tokens_output,
                error=error,
            )
        )
        db.commit()


def write_log_async(**kwargs) -> None:
    """后台线程异步写日志，不阻塞问答响应（N4）。"""
    threading.Thread(target=_write, kwargs=kwargs, daemon=True).start()


def list_logs(
    db: Session,
    *,
    used_retrieval: bool | None = None,
    has_error: bool | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[QaLog], int]:
    stmt = select(QaLog)
    count_stmt = select(func.count()).select_from(QaLog)
    if used_retrieval is not None:
        stmt = stmt.where(QaLog.used_retrieval == used_retrieval)
        count_stmt = count_stmt.where(QaLog.used_retrieval == used_retrieval)
    if has_error is not None:
        cond = QaLog.error.is_not(None) if has_error else QaLog.error.is_(None)
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)
    if date_from is not None:
        stmt = stmt.where(QaLog.created_at >= date_from)
        count_stmt = count_stmt.where(QaLog.created_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(QaLog.created_at <= date_to)
        count_stmt = count_stmt.where(QaLog.created_at <= date_to)
    total = db.scalar(count_stmt) or 0
    items = db.scalars(
        stmt.order_by(QaLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return list(items), total


def stats(db: Session) -> dict:
    """汇总统计（FR-LOG-04）：总提问数、检索命中率、平均耗时、累计 token。"""
    total = db.scalar(select(func.count()).select_from(QaLog)) or 0
    retrieval_count = (
        db.scalar(select(func.count()).select_from(QaLog).where(QaLog.used_retrieval.is_(True))) or 0
    )
    avg_latency = db.scalar(select(func.avg(QaLog.latency_ms))) or 0
    total_prompt = db.scalar(select(func.sum(QaLog.tokens_prompt))) or 0
    total_output = db.scalar(select(func.sum(QaLog.tokens_output))) or 0
    return {
        "total_questions": int(total),
        "retrieval_count": int(retrieval_count),
        "retrieval_rate": round(retrieval_count / total, 4) if total else 0.0,
        "avg_latency_ms": round(float(avg_latency), 1),
        "total_tokens": int(total_prompt or 0) + int(total_output or 0),
    }
