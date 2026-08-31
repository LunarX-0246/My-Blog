"""数据库引擎与会话（技术方案 §2.2）。

职责：创建 SQLAlchemy 引擎与会话工厂，供 api / services 层注入使用。
不在这里定义表模型（见 models.py），避免循环依赖。
"""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

# pool_pre_ping：连接被数据库空闲回收后，下次使用前自动探测并重连，
# 避免长空闲后的 "connection closed" 报错。
engine = create_engine(settings.database_url, pool_pre_ping=True)

# expire_on_commit=False：提交后仍可访问已加载的属性，服务层返回 ORM 对象给
# 序列化层时不会触发额外查询，也能避免常见 "Instance expired" 报错。
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI 依赖：每个请求一个独立会话，请求结束自动关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
