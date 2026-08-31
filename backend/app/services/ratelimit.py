"""问答限流（FR-ASK-19~22）。

- 单 IP 每小时次数（内存计数，单进程即可）
- 全站每日总量熔断
- 单次提问长度上限
阈值存 settings 表，可在管理端修改，无需改代码（FR-ASK-22）。
"""
from __future__ import annotations

import time
from collections import defaultdict

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Setting

_ip_counter: dict[str, list[float]] = defaultdict(list)
_daily: dict[str, object] = {"date": "", "count": 0}


def get_limits(db: Session) -> dict:
    """读取限流阈值；首次访问时用 .env 默认值初始化到 settings 表。"""
    row = db.get(Setting, "ask_limits")
    if row and isinstance(row.value, dict):
        return row.value
    limits = {
        "per_hour": settings.ask_rate_limit_per_hour,
        "daily_total": settings.ask_daily_total_limit,
        "max_chars": settings.ask_max_question_chars,
    }
    db.add(Setting(key="ask_limits", value=limits))
    db.commit()
    return limits


def check(db: Session, ip: str, question_len: int) -> str | None:
    """返回超限时的友好提示，否则 None。"""
    limits = get_limits(db)

    if question_len > limits["max_chars"]:
        return f"单次提问不能超过 {limits['max_chars']} 字"

    now = time.time()
    _ip_counter[ip] = [t for t in _ip_counter[ip] if now - t < 3600]
    if len(_ip_counter[ip]) >= limits["per_hour"]:
        return f"提问过于频繁，请稍后再试（每小时限 {limits['per_hour']} 次）"
    _ip_counter[ip].append(now)

    today = time.strftime("%Y-%m-%d")
    if _daily["date"] != today:
        _daily["date"] = today
        _daily["count"] = 0
    if int(_daily["count"]) >= limits["daily_total"]:
        return "今日问答已达上限，请明天再来"
    _daily["count"] = int(_daily["count"]) + 1

    return None
