# FoodDiary 阶段 2 汇报

## 一、阶段完成情况

已交付真实注册、登录、会话恢复与刷新、退出、个人资料及设置，以及服务端账户隔离。保留阶段 1 前端视觉、页面、素材、原始截图和 Demo 交互。API 模式的饮食、图片、AI 和好友业务显示预留状态。工作限于 D 盘本地开发和 GitHub 交付，未变更云服务、Docker、WSL 或 Android 工具。

## 二、磁盘占用

| 检查点 | C 盘可用 | D 盘可用 |
| --- | ---: | ---: |
| 阶段开始前 | 28.680 GiB | 320.360 GiB |
| 首次依赖安装后 | 28.686 GiB | 320.317 GiB |
| 隔离安装、按锁文件复验后 | 28.674 GiB | 320.243 GiB |
| 构建、测试和截图后 | 28.675 GiB | 314.732 GiB |
| 上一行相对起点变化 | −5.57 MiB | −5,762.81 MiB |

整盘变化包含同时发生的其他活动。D 盘整盘变化的来源未确定。项目目录及缓存单独测量，C 盘未触发 500 MiB 异常占用或 10 GiB 停止安装阈值。

| 位置 | 实测逻辑大小 |
| --- | ---: |
| `D:/桌面/mjc/fooddiary`，含原有前端依赖与构建 | 约 219.02 MiB |
| `backend/.venv` | 66.82 MiB |
| `backend/.venv/Lib/site-packages`，扣除 pip | 55.14 MiB |
| `D:/DevEnv/pip-cache` | 13.16 MiB |
| `backend/data/fooddiary.db` | 61,440 B |
| `backend/logs` | 399 B |
| `D:/DevEnv/pnpm-store/v10`、`D:/DevEnv/npm-cache` | 144.13 MiB、9,344 B |
| `D:/DevEnv/playwright` | 0 B。复用现有 Chrome |
| `D:/DevEnv/tmp` | 约 45.42 MiB，含已有临时文件 |

pytest 临时目录使用 `D:/DevEnv/tmp/fooddiary-auth-pytest-*`，浏览器测试使用 `D:/DevEnv/tmp/fooddiary-auth-browser-*`，每次独立生成。最终 pytest 使用 `fooddiary-auth-pytest-6214e476c6e144e9985b38eeb8e3bcd6`。浏览器测试日志打印每次实际路径。

首次 pip 安装受本机 `global.target` 配置影响，写入了 D 盘共享 Python 目录。已核对时间、路径和项目虚拟环境中的对应项，将确认是此次新增的 41 项移到 `D:/DevEnv/tmp/fooddiary-pip-first-install-backup`（7.98 MiB）。共享 FastAPI 版本仍为 0.115.0。之后的安装通过进程级 pip 配置隔离，在项目虚拟环境按锁文件复验。

## 三、后端技术栈

Python 3.13.9，FastAPI 0.165.0，Uvicorn 0.54.0，SQLAlchemy 2.0.58，Alembic 1.20.1，Pydantic 2.14.4，pydantic-settings 2.16.3，argon2-cffi 25.1.0，PyJWT 2.15.1，pytest 9.2.0、httpx 0.28.1。`pip check` 通过，完整版本见 [requirements.txt](../backend/requirements.txt)。

## 四、数据库及迁移

`0001_identity` 迁移已应用到本地开发库和独立测试库。应用表为 `users`、`user_settings`、`auth_sessions`。Alembic 模型核对无待生成操作。SQLite 外键、WAL、5 秒忙等待和 UTC 序列化已验证。数据库使用 `DATABASE_URL` 配置，重建应用后用户仍可登录。[数据库说明](DATABASE.md)

## 五、认证机制与安全

使用 Argon2id 和 15 分钟访问令牌，刷新 Cookie 默认 30 天并在每次成功刷新时轮换。受保护接口校验 JWT 和服务端会话状态。退出、会话到期或撤销后，关联令牌无法继续访问个人数据。浏览器认证 POST 要求 Origin 和 CSRF 校验标记，生产 Cookie 强制 Secure。

本机测得 8 次 Argon2id 校验中位 43.1 ms、最高 44.4 ms，参数 m=32 MiB、t=2、p=1。2 个并发槽用满时超过上限返回 429。两个真实并发注册及刷新请求均在测试中验证，云服务器上尚未压测。[认证安全](SECURITY.md)

## 六、Demo 和 API 隔离

Vite 在启动或构建阶段选用独立入口和路由。已检查 API 产物无 Demo 存储模块，Demo 产物无真实认证请求。API 内存只持有当前真实身份，访问失败会提示或回到登录，既有 Demo 存储保留在独立空间。已验证两名真实账号依次登录时的资料和设置隔离。

## 七、实际启动命令

在项目根目录运行。

```powershell
.\scripts\setup-dev-env.ps1 -Action Install
.\scripts\setup-backend.ps1 -Action Install
.\scripts\setup-backend.ps1 -Action Migrate
.\scripts\start-dev.ps1
```

默认前端 5173、后端 8000，绑定 `127.0.0.1`。本机运行时 5173 已被其他进程占用，脚本正确报出端口冲突。联合验收使用 `.\scripts\start-dev.ps1 -FrontendPort 15175 -BackendPort 18021`，前端 200、后端 ready 及 Vite Proxy 健康检查均通过。Demo 用 `.\scripts\start-dev.ps1 -Mode Demo -FrontendPort 15174` 启动。验收用进程已结束。

## 八、API 接口

以 `/api/v1` 为前缀，提供 GET `/health`、`/ready`，POST `/auth/register`、`/auth/login`、`/auth/refresh`、`/auth/logout`，GET 与 PATCH `/users/me`、`/users/me/settings` 共 10 项。Swagger 位于后端 `/docs`，请求与错误结构见 [API 文档](API.md)。

## 九、测试报告

| 验证 | 结果 |
| --- | --- |
| 后端 pytest | 34 项通过，覆盖空库迁移、连接、并发注册、参数与口令、个人资料和设置隔离、过期、并发轮换、重放、注销与撤销、令牌完整性、限流、CSRF/CORS、重启和测试库隔离 |
| 前端 API Playwright | 7 项通过，覆盖真实注册登录、恢复、设置与用户隔离、过期、后端不可用及手机和电脑视口。使用真实 Uvicorn 与独立 SQLite |
| 阶段 1 回归 | 12 个交互与响应式场景、9 个截图场景通过。保留阶段 1 的原始截图文件 |
| 阶段 2 截图验证 | 2 个截图场景通过，包含 6 张实测截图 |
| 构建 | TypeScript、API 和 Demo 生产构建、包隔离检查通过 |

## 十、真实页面截图

[登录](screenshots/phase-2/01-login.jpg) · [注册](screenshots/phase-2/02-register.jpg) · [真实个人中心](screenshots/phase-2/03-profile.jpg) · [手账空状态](screenshots/phase-2/04-diary-empty.jpg) · [Swagger](screenshots/phase-2/05-swagger.jpg) · [自动化测试报告](screenshots/phase-2/06-test-results.jpg)

## 十一、当前风险与未验证事项

- MySQL 8.4 兼容性、云服务器真实负载、生产 HTTPS 和多进程共享限流未验证。Android 安全存储和真机未实现。
- pytest 使用所要求的 httpx。当前 Starlette TestClient 已标注此集成为弃用，测试正常通过。
- 阶段 1 审查账号的仓库 404 尚无独立验证。仓库源码交付与审查账号的访问权限各自确认。

## 十二、Git 信息

交付分支为 `feature/phase-2-backend-auth`，阶段 1 基础 SHA 为 `75023b4475a5541d655b87f901a5f3179f1f5f3e`。最终完整 SHA 与工作区状态以推送后的阶段汇报和远端分支为准。[阶段 2 分支](https://github.com/zhenzhenqin/magic/tree/feature/phase-2-backend-auth)

## 十三、阶段结论

阶段 2 满足本地开发、验证及提交审查条件。等待架构顾问审查与用户验收，阶段 3 尚未开始。
