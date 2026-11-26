# FoodDiary API

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

## 阶段 3 私人手账

以下路由仍使用 `/api/v1`，所有请求都需要有效的 Bearer 会话。其他账号的资源与不存在的资源返回同样的 404。

| 方法 | 路径 | 请求与结果 |
| --- | --- | --- |
| POST | `/media/upload` | multipart 单文件 `file`。201 返回图片 ID、状态、尺寸与大小 |
| GET | `/media/{id}`、`/media/{id}/thumbnail` | 私有规范化原图与缩略图，200 WebP，禁止缓存 |
| DELETE | `/media/{id}` | 未关联图返回 204，仍被关联返回 409 |
| POST | `/meals` | 要求 `Idempotency-Key`，8–128 个小写字母、数字、下划线或连字符。新建 201，同内容重试 200，不同内容或已删除请求 409 |
| GET | `/meals` | `date` 或 `start/end`，可用 `meal_type/page/limit`。默认 30 条，单页最多 100。倒序按本地日期、UTC 用餐时间、UUID |
| GET | `/meals/{id}` | 完整明细、照片和编辑版本 |
| PATCH | `/meals/{id}` | 提交全部可编辑表单及 `version`，过期版本 409 |
| DELETE | `/meals/{id}` | 可带 `version` 保护旧操作，成功返回 204 |
| GET | `/calendar?month=YYYY-MM` | 记录日期、餐次数、代表图片 ID |
| GET | `/statistics/daily?date=YYYY-MM-DD` | 餐数、食物数和按已知数值汇总的营养 |

提交包含 `meal_type`、`local_date`、`local_time`、`timezone`、备注、1–30 个 `items` 和最多 5 个已有同账号图片 ID。食物明细支持名称、分类、重量、热量、蛋白质、碳水、脂肪和备注。营养与重量允许 null，拒绝负数、非有限值和超出精度范围的值。数据库写锁超时返回统一 503 和 `Retry-After`，创建可用原幂等键重试。


## 阶段 4 食物识别

路径继续使用 `/api/v1`，所有识别接口需要有效 Bearer 会话并返回 `Cache-Control: no-store`。跨账号访问的任务和媒体验证使用与不存在相同的 404。

| 方法和路径 | 请求及响应 |
| --- | --- |
| `GET /ai/capabilities` | `available`、`simulated`、`max_images`、`consent_version`、`privacy_url` |
| `POST /ai/jobs` | 确认告知后提交 `media_ids` 与当前 `consent_version`，附 `Idempotency-Key`。成功 202，包含任务 UUID、状态及过期时间。相同键和相同照片顺序重放，内容不一致为 409 |
| `GET /ai/jobs/{id}` | 所属任务状态、可重试标记、处理结果或安全错误码。成功结果含稳定候选 UUID。任务结果保留期过后返回 404 |
| `POST /ai/jobs/{id}/cancel` | 取消等待或运行中的任务。已发送的上游调用可能仍会处理。返回当前任务状态 |
| `POST /ai/jobs/{id}/retry` | 附不同操作各自的 `Idempotency-Key`、当前 `consent_version`。上次发送状态未知时须显式传 `accept_unknown_charge=true`。成功 202 |
| `GET /ai/usage` | 当前账号计入的次数、账号上限、综合额度可用性及 UTC 重置时间。全局用量详情留在服务端 |

新餐次和编辑时，新的 AI 明细可提交 `ai_reference: {job_id, candidate_id}`。已有明细提交其 `id`，保留原来源。客户端发送 `source` 会收到 422。结果由服务器确定为 `manual`、`ai` 或 `ai_edited`，并返回 `ai_job_id`、`ai_candidate_id`、`ai_provider`。模拟候选以 `simulated` 和 Provider 标识区分。额度耗尽使用 `ai_quota` 与 429。不可用的识别配置返回 `ai_unavailable` 与 503。

### Phase 4.1

- `GET /ai/jobs/recover` 可按 `request_key` 查创建结果，或按 `retry_key` 与 `job_id` 查重试结果。默认返回本人未完成任务，或与 `form_meal_id` 匹配的近期、未采用结果。无可访问任务时返回 200 和 JSON null。此接口只读。
- 创建时可提交本人正在编辑的 `form_meal_id`。任务视图返回完整校验后的有序 `media_ids`、`form_meal_id` 和 `worker_online`。识别能力也返回 `worker_online`，独立于配置可用性。
- 真实百炼累计耗尽时返回 429 和 `ai_cumulative_limit`。用量接口以 `exhausted_reason` 区分每日与累计限制。取消和查询仍按所属账号可用。
- 新采用 AI 候选时，餐次须保有原识别图片并匹配任务编辑上下文。违反时返回 422 和 `ai_candidate_context`。日报附加 `nutrition_sources`，原 `nutrition` 的未知值、零值和完整性契约保持。
