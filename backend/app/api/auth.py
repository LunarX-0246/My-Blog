"""认证接口：登录 / 退出 / 当前状态（FR-AUTH-01~06，技术方案 §5.2）。

单一博主账号，凭据来自 .env（ADMIN_USERNAME / ADMIN_PASSWORD_HASH），系统内不提供注册。
登录失败按客户端 IP 计数，连续超限临时锁定，防止暴力破解（FR-AUTH-06）。
失败计数用进程内内存即可——单 worker 部署（技术方案 §9），不引入 Redis。
"""
from __future__ import annotations

import time

import bcrypt
from fastapi import APIRouter, Request, Response

from app.config import settings
from app.deps import COOKIE_NAME, create_session_token, get_client_ip, get_current_admin
from app.errors import ApiError
from app.schemas import LoginRequest, MeResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])

# 登录失败计数：{ ip: {"failures": [失败时间戳], "locked_until": 解锁时间戳} }。
# 时间戳用 time.monotonic()，仅作进程内相对比较，重启即清空（可接受）。
_login_state: dict[str, dict[str, object]] = {}


def _is_https(request: Request) -> bool:
    """判断是否 HTTPS：生产经 Nginx 会转发 X-Forwarded-Proto=https，本机 HTTP 无此头。"""
    return request.headers.get("x-forwarded-proto", "").split(",")[0].strip() == "https"


@router.post("/login")
def login(body: LoginRequest, request: Request, response: Response) -> dict[str, bool]:
    ip = get_client_ip(request)
    now = time.monotonic()
    state = _login_state.setdefault(ip, {"failures": [], "locked_until": 0.0})

    failures: list[float] = state["failures"]  # type: ignore[assignment]
    locked_until: float = state["locked_until"]  # type: ignore[assignment]
    # 只统计锁定时长窗口内的失败，超出窗口的自动失效
    failures = [t for t in failures if now - t < settings.login_lockout_seconds]
    state["failures"] = failures

    if locked_until > now:
        wait = int(locked_until - now) + 1
        raise ApiError(429, "locked_out", f"登录失败次数过多，请 {wait} 秒后再试")

    if not settings.admin_username or not settings.admin_password_hash:
        raise ApiError(503, "not_configured", "管理员账号尚未配置，请检查 .env")

    password_ok = bcrypt.checkpw(
        body.password.encode("utf-8"), settings.admin_password_hash.encode("utf-8")
    )
    if body.username != settings.admin_username or not password_ok:
        failures.append(now)
        state["failures"] = failures
        remaining = settings.login_max_attempts - len(failures)
        if remaining <= 0:
            state["locked_until"] = now + settings.login_lockout_seconds
            raise ApiError(
                429, "locked_out",
                f"连续失败 {settings.login_max_attempts} 次，账号已临时锁定，请稍后再试",
            )
        raise ApiError(401, "bad_credentials", f"用户名或密码错误，还可尝试 {remaining} 次")

    # 成功：清空失败记录，下发签名 HttpOnly Cookie
    _login_state.pop(ip, None)
    token = create_session_token(body.username)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=settings.session_max_age,
        httponly=True,
        samesite="lax",
        secure=_is_https(request),
        path="/",
    )
    return {"ok": True}


@router.post("/logout")
def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
def me(request: Request) -> MeResponse:
    try:
        username = get_current_admin(request)
        return MeResponse(authenticated=True, username=username)
    except ApiError:
        return MeResponse(authenticated=False)
