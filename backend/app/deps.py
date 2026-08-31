"""依赖注入：鉴权、客户端 IP（技术方案 §5.1 / §9）。

- ``get_current_admin``：校验签名 Cookie，失败抛 ApiError(401)。供管理接口 ``Depends`` 使用。
- ``get_client_ip``：优先取 X-Forwarded-For（生产经 Nginx 转发），否则取直连地址。
- 会话用 itsdangerous 的 ``URLSafeTimedSerializer`` 签名，自带过期时间（SESSION_MAX_AGE）。

为什么签名 Cookie 而不是 JWT 存 localStorage：管理端鉴权必须是 HttpOnly Cookie，
JS 读不到，能抵御 XSS 窃取；SameSite=Lax 兼顾同站跳转时携带（技术方案 §9）。
"""
from __future__ import annotations

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from fastapi import Request

from app.config import settings
from app.errors import ApiError

COOKIE_NAME = "blog_session"

_serializer = URLSafeTimedSerializer(settings.session_secret, salt="blog-session")


def get_client_ip(request: Request) -> str:
    """取真实客户端 IP。

    X-Forwarded-For 形如 ``client, proxy1, proxy2``，第一段是真实客户端。
    生产经 Nginx 才有此头；本机直连 / 经 Next.js 代理时可能没有，退回 request.client。
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def create_session_token(username: str) -> str:
    """生成带过期时间的签名会话串。"""
    return _serializer.dumps({"sub": username})


def get_current_admin(request: Request) -> str:
    """校验当前请求的登录态，返回管理员用户名；未登录/过期/伪造则抛 401。"""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise ApiError(401, "unauthorized", "请先登录")
    try:
        data = _serializer.loads(token, max_age=settings.session_max_age)
    except SignatureExpired:
        raise ApiError(401, "session_expired", "登录已过期，请重新登录")
    except BadSignature:
        raise ApiError(401, "unauthorized", "登录状态无效，请重新登录")

    username = data.get("sub")
    if not isinstance(username, str) or username != settings.admin_username:
        raise ApiError(401, "unauthorized", "登录状态无效，请重新登录")
    return username
