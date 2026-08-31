"""统一错误处理（技术方案 §5.1）。

所有错误返回 ``{"error": {"code": ..., "message": ...}}``，``message`` 是面向用户的中文，
``code`` 是机器可读的稳定标识。业务代码抛 :class:`ApiError`；校验失败与未捕获的
HTTPException 也统一转成这个格式，避免把堆栈或英文细节暴露给前端（NFR-SEC-05）。
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(HTTPException):
    """业务错误：带机器可读 code 与面向用户的中文 message。"""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(status_code=status_code, detail={"code": code, "message": message})


def register_exception_handlers(app: FastAPI) -> None:
    """在 app 上注册统一错误处理器。main.py 启动时调用一次。"""

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})

    @app.exception_handler(HTTPException)
    async def _http_error(_: Request, exc: HTTPException) -> JSONResponse:
        # 兜底：把任意 HTTPException 的 detail 转成统一格式
        detail = exc.detail
        if isinstance(detail, dict) and "code" in detail and "message" in detail:
            body = {"error": detail}
        else:
            body = {"error": {"code": "error", "message": str(detail)}}
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # 不暴露 Pydantic 的字段级错误细节，给一个统一的中文提示
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "validation_error", "message": "请求参数不合法"}},
        )
