# FoodDiary

FoodDiary 是一款计划同时提供 Web 和 Android APK 的私人 AI 美食手账。用户可以拍照记录饮食，确认 AI 的识别结果，生成美食贴纸，并经授权与亲友互看记录。视觉采用原创组件和素材，以温馨、简洁的手账为方向。

阶段 2 提供真实注册、登录、会话和个人资料。API 模式的饮食及亲友功能显示预留状态。Demo 模式继续提供阶段 1 的手账、图鉴、模拟识别与共享交互，演示记录和照片存于浏览器。

## 本地启动

在 Windows PowerShell 中，从 D 盘项目根目录执行。启动脚本只给本次进程及子进程配置缓存和临时路径。

### API 模式

```powershell
.\scripts\setup-dev-env.ps1 -Action Install
.\scripts\setup-backend.ps1 -Action Install
.\scripts\setup-backend.ps1 -Action Migrate
.\scripts\start-dev.ps1
```

默认地址为 [前端](http://127.0.0.1:5173/) 与 [Swagger](http://127.0.0.1:8000/docs)。端口占用时可改用 `.\scripts\start-dev.ps1 -FrontendPort 15175 -BackendPort 18021`。如果已有自定义 `.env`，将 `APP_ORIGINS` 包含实际的前端 Origin。

默认开发库在 `backend/data/fooddiary.db`。未提供 `.env` 或进程密钥时，脚本为本地开发生成随机密钥。自定义配置参照 `.env.example`，实际 `JWT_SECRET` 只能进入忽略文件或进程环境。

### Demo 模式

```powershell
.\scripts\start-dev.ps1 -Mode Demo
```

Demo 只启动前端。正式构建默认 API 模式，通过 `-Mode Demo` 可单独生成演示包。

### 测试

```powershell
.\scripts\setup-dev-env.ps1 -Action Typecheck
.\scripts\setup-dev-env.ps1 -Action Build
.\scripts\setup-backend.ps1 -Action Test
.\scripts\setup-dev-env.ps1 -Action Test -Mode Demo -Port 15174
.\scripts\setup-dev-env.ps1 -Action TestApi -Port 15173 -BackendPort 18020
.\scripts\setup-dev-env.ps1 -Action ScreenshotsApi -Port 15173 -BackendPort 18020
```

Playwright 使用本机 Chrome，API 测试自动启动独立的后端及临时数据库。阶段 2 截图输出到 `docs/screenshots/phase-2/`。

| 路径 | 用途 |
| --- | --- |
| `frontend/` | Web 客户端与后续 Capacitor Android 工程 |
| `backend/` | API、数据库迁移与后续图片任务 |
| `deploy/` | Docker Compose 和反向代理配置 |
| `scripts/` | 开发和运维脚本 |
| `docs/` | 环境、架构和技术选型记录 |

- [开发规范](AGENTS.md)
- [分阶段计划](PLAN.md)与[当前进度](PROGRESS.md)
- [环境盘点](docs/ENVIRONMENT.md)、[初步架构](docs/ARCHITECTURE.md)与[技术决策](docs/DECISIONS.md)
- [阶段 1 汇报与截图](docs/PHASE-1.md)及[素材来源](docs/ASSETS.md)
- [阶段 2 汇报与截图](docs/PHASE-2.md)、[API](docs/API.md)、[数据库](docs/DATABASE.md)与[认证安全](docs/SECURITY.md)
