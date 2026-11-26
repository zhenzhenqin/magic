# FoodDiary 阶段 2 认证安全

## 密码与限流

密码由 argon2-cffi 作 Argon2id 哈希，使用随机盐。默认内存 32 MiB、时间成本 2、并行度 1，每个后端进程最多同时执行 2 次哈希或校验。达到上限返回 429。未知或停用账号走占位哈希校验，错误响应与错误密码一致。注册、登录、刷新采用进程内来源 IP 滑动窗口限流。SQLite 的用户名唯一约束覆盖并发注册。

默认每 60 秒每 IP 允许注册 8 次、登录 10 次、刷新 60 次。本地代理下来源会合并为回环地址。生产多进程共享限流、可信代理配置和低配主机压测属于部署阶段。

## 会话与重放

- Access Token 为 HS256 JWT，默认 15 分钟，验证算法、签发者、受众、主体、会话 ID、签发时间和有效期。每个受保护请求同时查询所属账户和会话的有效状态。
- Refresh Token 由 32 字节密码学随机数生成，数据库仅保存 SHA-256 摘要。会话自登录起默认最多 30 天，刷新轮换凭据并遵守原会话截止时间。
- 刷新以当前摘要和会话状态作原子条件更新。并发竞争只有一个请求成功。最近一次旧摘要在默认 10 秒窗口内返回 409，响应不改 Cookie，客户端可等待获胜请求的 Cookie 生效后再试。窗口外再次提交最近一次旧摘要会撤销相关会话，更早的摘要被拒绝。浏览器优先用 Web Locks 在标签页间串行化 Cookie 请求。
- 退出成功后服务端撤销会话并清理 Cookie。已签发的关联 Access Token 随即无法访问受保护接口。当前网络请求失败时会显示错误，退出需待服务器确认成功。
- 访问令牌仅放在前端运行内存。刷新令牌由浏览器作为 HttpOnly、SameSite=Strict 的 Cookie 管理，路径为 `/api/v1/auth`。本地 HTTP 使用开发 Cookie，生产必须设置 Secure 并配置 HTTPS 白名单。

## 边界与配置

- Cookie 认证 POST 校验精确 Origin 与固定自定义请求头。CORS 启用显式来源白名单。服务器只根据认证主体访问个人资料与设置。Pydantic 拒绝额外字段，公开响应排除内部 ID、密码哈希和账号状态等内部字段。
- 配置经进程变量或根目录忽略的 `.env` 提供。JWT 密钥要求至少 32 字节且拒绝弱示例，生产必须显式配置密钥，固定关闭异常调试。便于本地启动的随机密钥放在 D 盘开发数据目录，经脚本注入进程环境。
- API 错误统一封装且屏蔽提交值、异常堆栈和数据库细节。API 响应使用 `Cache-Control: no-store`。开发日志记录 HTTP 方法、路径和状态码。
- Demo 和 API 使用构建或启动时确定的路由入口，真实身份和设置不写入 Demo 存储。原生 Android 安全存储、生产 HTTPS 和云端实际负载未在阶段 2 验证。

实现参考。[FastAPI 安全指南](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/) · [PyJWT API](https://pyjwt.readthedocs.io/en/stable/api.html) · [argon2-cffi](https://argon2-cffi.readthedocs.io/en/stable/api.html)
