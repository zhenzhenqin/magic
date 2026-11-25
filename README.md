# FoodDiary

FoodDiary 是一款计划同时提供 Web 和 Android APK 的私人 AI 美食手账。用户可以拍照记录饮食，确认 AI 的识别结果，生成美食贴纸，并经授权与亲友互看记录。视觉采用原创组件和素材，以温馨、简洁的手账为方向。

阶段 1 提供可运行的 Web 原型。原型包含手账、月历、图鉴、本地图片预览和模拟识别、亲友共享、双人手账及个人中心。记录和照片保存在当前浏览器。

## 本地启动

在 Windows PowerShell 中，从 D 盘项目根目录执行。脚本将 pnpm、npm、Playwright 和临时文件路径配置到 D 盘，仅在当前开发进程中生效。

```powershell
.\scripts\setup-dev-env.ps1 -Action Check
.\scripts\setup-dev-env.ps1 -Action Install
.\scripts\setup-dev-env.ps1 -Action Dev
```

启动后打开 [本机原型](http://127.0.0.1:5173/)。需要更换端口时传入 `-Port 5174`。

```powershell
.\scripts\setup-dev-env.ps1 -Action Typecheck
.\scripts\setup-dev-env.ps1 -Action Build
.\scripts\setup-dev-env.ps1 -Action Test
.\scripts\setup-dev-env.ps1 -Action Screenshots
```

Playwright 默认使用本机已安装的 Chrome。截图生成到 `docs/screenshots/phase-1/`。

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
