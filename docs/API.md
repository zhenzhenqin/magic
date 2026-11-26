# FoodDiary 阶段 2 API

本地 API 默认绑定 `http://127.0.0.1:8000`。Swagger 位于 `/docs`，OpenAPI 位于 `/openapi.json`。业务接口统一使用 `/api/v1`。联合启动时，前端通过同源 Vite Proxy 转发 `/api`。

| 方法 | 路径 | 输入 | 成功响应 |
| --- | --- | --- | --- |
| GET | `/health` | 无 | 200，`{"status":"ok"}` |
| GET | `/ready` | 无 | 200，`{"status":"ready"}`，连接或业务表不可用返回 503 |
| POST | `/auth/register` | `username`、`password`、`nickname` | 201，公开账户资料 |
| POST | `/auth/login` | `username`、`password` | 200，短期访问令牌、`expires_in`、`token_type` 和 `user`，同时设置刷新 Cookie |
| POST | `/auth/refresh` | HttpOnly 刷新 Cookie | 200，返回新访问令牌并轮换 Cookie |
| POST | `/auth/logout` | 可接收浏览器 Cookie 与访问令牌 | 204，撤销会话并清 Cookie |
| GET | `/users/me` | Bearer | 200，公开账户资料 |
| PATCH | `/users/me` | Bearer，`nickname` | 200，更新后资料 |
| GET | `/users/me/settings` | Bearer | 200，本人设置 |
| PATCH | `/users/me/settings` | Bearer，可提交 `timezone`、`show_calories`、`show_nutrition` 中任意字段 | 200，更新后设置 |

公开账户资料含 `public_id`、`username`、`nickname`、`avatar_key`、`created_at` 和 `updated_at`。个人设置含时区、两个布尔项及创建和更新时间。时区使用 IANA 名称，PATCH 字段可省略。昵称去首尾空格后为 1–40 字符。登录名去首尾空格后为 3–32 个 ASCII 字母、数字或下划线，统一转小写。注册密码为 12–128 字符，按原值校验。用户资料请求经服务端会话确定所属账号。

所有认证 POST 要求浏览器 `Origin` 在配置白名单内，且请求包含 `X-FoodDiary-Intent: browser`。登录失败统一使用 `401 invalid_credentials`。参数无效为 422，用户名冲突与并发刷新分别为 `409 username_taken` 和 `409 refresh_in_progress`。会话无效或已撤销为 `401 invalid_session`，来源与 CSRF 校验失败为 403，限流为 429 并提供 `Retry-After`。业务响应禁用缓存。

错误响应格式如下。

```json
{
  "error": {
    "code": "validation_error",
    "message": "请检查输入内容。",
    "fields": [{"field": "body.username", "message": "格式不正确。"}]
  }
}
```

联调时使用当前前端地址作为可信 Origin。Swagger 可查看模型。直接从后端端口点击授权相关请求时，浏览器 Origin 仍须满足白名单；通过联合前端正常操作可验证完整 Cookie 流程。
