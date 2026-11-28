# FoodDiary

FoodDiary 是一款计划同时提供 Web 和 Android APK 的私人 AI 美食手账。用户可以拍照记录饮食，确认 AI 的识别结果，生成美食贴纸，并经授权与亲友互看记录。视觉采用原创组件和素材，以温馨、简洁的手账为方向。

API 模式提供真实账户、个人手账、饮食月历、每日摘要、私有照片和好友共享。启用受支持的模型后可授权识别所选照片，修改候选再保存。Demo 模式保留阶段 1 的模拟体验，继续使用独立浏览器存储。

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

默认开发库和私有照片位于 `backend/data/fooddiary.db` 与 `backend/data/media`。未提供 `.env` 或进程密钥时，脚本为本地开发生成随机密钥。自定义配置参照 `.env.example`，实际 `JWT_SECRET` 只能进入忽略文件或进程环境。已有库可以运行 Alembic 增量迁移。

### 开启本地贴纸

```powershell
.\scripts\setup-sticker-worker.ps1 -Action Install
.\scripts\setup-backend.ps1 -Action Migrate
.\scripts\start-dev.ps1 -WithStickerWorker
```

阶段 5 的真实模式使用黑白纸质手账、食物剪贴和个人图鉴。贴纸 Worker 和模型缓存位于 D 盘。普通启动支持原图记录，外部 AI Worker 可单独启用。 [贴纸使用说明](docs/STICKERS.md) · [图鉴规则](docs/CATALOG.md) · [阶段报告](docs/PHASE-5.md)

### 饭搭子与双人手账

在「饭搭子」复制自己的公开 ID，或填写好友的完整 ID 并发送申请。好友接受后，双方可以各自保存向对方授出的权限。可以单独开放原照片、贴纸或图鉴。进入「双人手账」可按日期和四种餐次查看自己与好友已共享的内容。 [权限及日期范围](docs/SHARING.md) · [阶段 6 报告](docs/PHASE-6.md)

### 个人 AI 与账号安全

账号支持用户名密码，配置邮箱服务后可使用已验证邮箱、一次性验证码及邀请码注册。登录后从「我的」进入账号安全或 AI 助手。 [账号安全与本地验证](docs/AUTH.md)

当前个人 AI 只在明确启用的开发模拟环境接收测试标记。全局管理员密钥路径及真实模型调用已关闭。设置个人连接可随时跳过，拍照、贴纸、手动记录和好友共享可独立使用。 [个人 AI](docs/BYOK.md) · [阶段 7.3](docs/PHASE-7.3.md)

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
.\scripts\setup-dev-env.ps1 -Action TestAi -Port 15173 -BackendPort 18020
.\scripts\setup-dev-env.ps1 -Action TestAiRecovery -Port 15173 -BackendPort 18020
.\scripts\setup-dev-env.ps1 -Action TestAiOffline -Port 15173 -BackendPort 18020
.\scripts\setup-dev-env.ps1 -Action TestSharing -Port 15173 -BackendPort 18020
.\scripts\setup-dev-env.ps1 -Action ScreenshotsDiary -Port 15173 -BackendPort 18020
.\scripts\setup-dev-env.ps1 -Action ScreenshotsAi -Port 15173 -BackendPort 18020
```

Playwright 使用本机 Chrome，API 测试自动启动独立的后端及临时数据库和媒体目录。识别测试使用离线模拟，截图输出到 `docs/screenshots/phase-4/`。

| 路径 | 用途 |
| --- | --- |
| `frontend/` | Web 客户端与后续 Capacitor Android 工程 |
| `backend/` | API、数据库迁移与识别 Worker |
| `deploy/` | Docker Compose 和反向代理配置 |
| `scripts/` | 开发和运维脚本 |
| `docs/` | 环境、架构和技术选型记录 |

- [开发规范](AGENTS.md)
- [分阶段计划](PLAN.md)与[当前进度](PROGRESS.md)
- [环境盘点](docs/ENVIRONMENT.md)、[初步架构](docs/ARCHITECTURE.md)与[技术决策](docs/DECISIONS.md)
- [阶段 1 汇报与截图](docs/PHASE-1.md)及[素材来源](docs/ASSETS.md)
- [阶段 2 汇报与截图](docs/PHASE-2.md)、[API](docs/API.md)、[数据库](docs/DATABASE.md)与[认证安全](docs/SECURITY.md)
- [阶段 3 汇报与截图](docs/PHASE-3.md)及[私有图片存储](docs/STORAGE.md)
- [阶段 4 汇报与截图](docs/PHASE-4.md)及[AI 食物识别](docs/AI.md)
- [阶段 7.1 汇报](docs/PHASE-7.1.md)、[部署说明](docs/DEPLOYMENT.md)及[备份恢复](docs/BACKUP-RESTORE.md)
- [阶段 7.2 部署状态与验收记录](docs/PHASE-7.2.md)
- [应用内拍照、贴纸和 Android 适配](docs/CAMERA.md)
