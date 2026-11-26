from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException


class FieldProblem(BaseModel):
    field: str
    message: str


class Problem(BaseModel):
    code: str
    message: str
    fields: list[FieldProblem] = []


class ProblemResponse(BaseModel):
    error: Problem


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, headers: dict[str, str] | None = None):
        self.status, self.code, self.message, self.headers = status, code, message, headers or {}
        super().__init__(message)


def invalid_session() -> ApiError:
    return ApiError(401, "invalid_session", "登录已失效，请重新登录。", {"WWW-Authenticate": "Bearer"})


def problem(status: int, code: str, message: str, headers=None, fields=None):
    body = ProblemResponse(error=Problem(code=code, message=message, fields=fields or []))
    return JSONResponse(body.model_dump(), status_code=status, headers={"Cache-Control": "no-store", **(headers or {})})


async def api_error(_: Request, exc: ApiError):
    return problem(exc.status, exc.code, exc.message, exc.headers)


async def validation_error(_: Request, exc: RequestValidationError):
    messages = {
        "missing": "必填字段。",
        "extra_forbidden": "不支持此字段。",
        "string_too_short": "内容太短。",
        "string_too_long": "内容太长。",
        "string_pattern_mismatch": "格式不正确。",
    }
    fields = [
        FieldProblem(
            field=".".join("字段" if not isinstance(part, (str, int)) else str(part) for part in error["loc"][:4]),
            message=messages.get(error["type"], "请检查字段值。"),
        )
        for error in exc.errors()
    ]
    # Unknown field names come from the client and may themselves contain secrets.
    for item, error in zip(fields, exc.errors()):
        if error["type"] == "extra_forbidden":
            item.field = "body"
    return problem(422, "validation_error", "请检查输入内容。", fields=fields)


async def http_error(_: Request, exc: HTTPException):
    messages = {404: "未找到该接口。", 405: "此接口不支持该请求方法。"}
    return problem(exc.status_code, "http_error", messages.get(exc.status_code, "请求未完成。"), exc.headers)


async def unexpected_error(_: Request, exc: Exception):
    return problem(500, "internal_error", "服务器暂时无法处理请求。")
