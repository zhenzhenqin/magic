# FoodDiary

FoodDiary 是一款计划同时提供 Web 和 Android APK 的私人 AI 美食手账。用户可以拍照记录饮食，确认 AI 的识别结果，生成美食贴纸，并经授权与亲友互看记录。视觉采用原创组件和素材，以温馨、简洁的手账为方向。

API 模式提供真实账户、个人手账、饮食月历、每日摘要及私有照片。启用百炼后可授权识别所选照片，修改候选再保存。Demo 模式保留阶段 1 的图鉴、模拟识别和共享体验，继续使用独立浏览器存储。

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

### 开启食物识别

在对应地域的阿里云百炼工作空间创建 API Key。在仓库根目录的忽略文件 `.env` 或后端进程环境设置 `AI_ENABLED=true`、`AI_PROVIDER=qwen`、`AI_BASE_URL`、`AI_API_KEY` 和 `AI_MODEL=qwen3-vl-flash`。Base URL 使用工作空间的 OpenAI 兼容地址，结尾为 `/compatible-mode/v1`。若新建 `.env`，同时使用现有开发 `JWT_SECRET`，或为独立开发库生成新的高熵密钥。启动前确认 `APP_ORIGINS` 对应实际端口。[百炼 API Key 指引](https://www.alibabacloud.com/help/en/model-studio/get-api-key)

Qwen 与 DeepSeek 的累计调用上限默认均为 0。获得用户批准后，基于独立联调库的现有账本设置对应供应商的绝对累计上限。浏览器能在同账号下恢复上次任务，Worker 离线时可继续手动记录。 [联调素材和脚本](docs/ai-benchmark/README.md)

阶段 4.2 使用独立联调目录 `D:/DevEnv/fooddiary-phase42`。在仓库根运行 `.\scripts\start-phase42-lab.ps1 -PrepareOnly` 可准备环境，直接运行会关闭真实调用。DeepSeek 联调在私有 `provider.env` 中配置 `AI_PROVIDER=deepseek`、`AI_BASE_URL=https://api.deepseek.com` 和专用 `AI_API_KEY`，获得明确的次数和费用授权后可启动真实 Worker。 [联调及授权说明](docs/PHASE-4.2.md)

```powershell
.\scripts\setup-backend.ps1 -Action Migrate
.\scripts\start-dev.ps1 -WithAiWorker -FrontendPort 15175 -BackendPort 18021
```

也可在当前 API 已运行时，在另一窗口执行 `.\scripts\setup-backend.ps1 -Action AiWorker`。配置为空时，手动饮食系统可单独运行。真实模型效果仍待授权联调。[AI 配置和测试说明](docs/AI.md)

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
