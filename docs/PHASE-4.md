# FoodDiary 阶段 4 汇报

## 一、阶段完成情况

已完成阶段 4 的代码、数据库迁移、API、后台 Worker、浏览器交互及本地模拟验收。用户选择照片并同意第三方处理后，可等候识别、修正候选，再确认保存到手账和月历。真实百炼联调等待专用 API Key 和有限费用授权。此次仅运行本地程序。

## 二、阶段 3 遗留问题处理

编辑已有明细时沿用其 ID，允许删除和排序。服务端验证明细所属餐次及账号，并保留创建幂等和编辑版本锁。媒体清理执行时重新检查活跃识别任务，覆盖扫描与任务创建的并发情况。每用户 200 MiB 和 1000 张的默认媒体额度保留，生产按实际数据量与备份情况评审。[存储](STORAGE.md) · [数据库](DATABASE.md)

## 三、C 盘和 D 盘磁盘占用

| 读数 | C 盘可用 | D 盘可用 |
| --- | ---: | ---: |
| 开始前 | 28.476 GiB | 314.947 GiB |
| 构建、测试、截图和本地联调后 | 28.692 GiB | 314.863 GiB |
| 可用空间变动 | 增加 220.58 MiB | 减少 86.06 MiB |

整盘变化包括同机其他进程。复用 D 盘虚拟环境、缓存和临时目录，也复用了已安装的 Chrome。11 张截图合计 884,665 字节。未新增依赖或下载模型，未触发 C 盘阈值。

## 四、AI 技术选型及依赖版本

初测候选为 `qwen3-vl-flash`，对照候选为 `qwen3-vl-plus`。适配百炼的 OpenAI Chat Completions，以 JSON Object 形式输出。复用 Python 3.13.9、FastAPI 0.165.0、SQLAlchemy 2.0.58、Alembic 1.20.1、httpx 0.28.1、Pydantic 2.14.4 与 Pillow 13.0.0。[Qwen 视觉兼容接口](https://www.alibabacloud.com/help/en/model-studio/qwen-vl-compatible-with-openai) · [JSON 输出](https://www.alibabacloud.com/help/en/model-studio/qwen-structured-output)

## 五、迁移及新增表

`0003_ai_recognition` 新增 `ai_jobs`、`ai_job_media`、`ai_usage_logs`、`ai_retry_requests` 及食物明细来源字段。开发 SQLite 已升级，Alembic 模型核对无待应用操作。测试验证原有账号、设置、会话、餐次、照片、明细 ID 及旧幂等请求升级后仍可使用。[数据库](DATABASE.md)

## 六、AI Provider

`QwenVisionProvider` 发送去元数据的 JPEG 与固定版本中文提示词。服务端校验候选结构、分类、未知值、数值范围和小数精度，明显矛盾的估算留空并附警告。`FakeVisionProvider` 供标记清楚的本地模拟及自动化，生产配置拒绝使用。[AI 接入说明](AI.md)

## 七、状态机、Worker 和恢复

SQLite 短写事务原子领取任务及预留额度。外部网络请求在事务外运行。后台默认只有一个并发槽。未发送的租约可恢复入队，发送后状态未知的任务需要用户确认重试。取消或失去租约的 Worker 无法写入结果。终态任务和用量按保留期回收。[任务恢复](AI.md)

## 八、隐私、额度和费用保护

每次使用时由用户确认所选照片的第三方处理说明。API 只接受本人照片 UUID，第三方接收压缩像素和固定提示词。默认每用户 10 次和全局 30 次，按 UTC 日重置。额度按尝试预留、结算并记录，结果未知的调用也计入。实际账单由供应商提供。[安全说明](SECURITY.md) · [百炼隐私](https://www.alibabacloud.com/help/en/model-studio/privacy-notice)

## 九、食物明细 ID 和来源

候选使用稳定 UUID。正式明细可为 `manual`、`ai` 或 `ai_edited`，由后端按所有者、已完成任务和候选字段确定。每个识别任务只可被一条正式餐次采用。修改备注保留原 ID 与来源。模型与提示词追踪保存在正式明细中，任务候选结果到期后仍可编辑这条明细。

## 十、前端与运行截图

沿用阶段 3 的录入页、月历和奶油纸手账。选中的照片最多三张进入识别，餐次仍可保存五张。空表在收到候选后自动填入，有人工内容时提供追加及替换。换图、离开页面或换账号时停止使用旧任务结果。

以下为本机 Chrome 的运行截图，使用原创样例图、合成故障图片及本地模拟识别。百炼授权界面截图由受控能力响应触发，未提交照片到第三方。

- [选图](screenshots/phase-4/01-simulated-photo-selection.jpg) · [模拟授权](screenshots/phase-4/02-simulated-consent.jpg) · [百炼授权界面](screenshots/phase-4/10-qwen-consent-ui-check.jpg)
- [等待](screenshots/phase-4/03-simulated-waiting.jpg) · [多食物候选](screenshots/phase-4/04-simulated-candidates.jpg) · [人工修正](screenshots/phase-4/05-simulated-edited.jpg) · [真实后端保存的手账](screenshots/phase-4/06-saved-private-diary.jpg)
- [失败降级](screenshots/phase-4/07-simulated-manual-fallback.jpg) · [额度提示](screenshots/phase-4/08-simulated-quota.jpg) · [手机端选图和结果状态](screenshots/phase-4/09-simulated-mobile.jpg) · [手机端食物明细](screenshots/phase-4/11-simulated-mobile-foods.jpg)

## 十一、自动化测试

| 检查 | 结果 |
| --- | --- |
| 后端 pytest | 111 项通过，包含原有 66 项和本阶段新增 45 项 |
| 真实 API Playwright | 14 项通过，含原有 13 项及未配置 AI 的手动降级 |
| AI Playwright | 8 项通过，真实 API、私有图片和独立 SQLite 配本地 Fake Provider |
| Demo Playwright | 12 项交互和响应式、9 项截图回归通过 |
| 阶段 4 截图场景 | 2 项通过，生成 11 张截图 |
| 构建及迁移 | TypeScript、API/Demo 生产构建、包内容隔离和 Alembic 模型核对均通过 |

## 十二、真实模型测试

真实模型调用 0 次，测试未产生外部模型调用费用。真实模型权限、精确地区、供应商响应延迟、识别及营养表现、Token 与账单留待联调。模拟浏览器的等待时间是测试场景设定值。[授权后测试矩阵](AI.md)

## 十三、启动与 API Key

```powershell
.\scripts\setup-backend.ps1 -Action Migrate
.\scripts\start-dev.ps1 -WithAiWorker -FrontendPort 15175 -BackendPort 18021
```

在本机忽略的根目录 `.env` 或后端进程环境启用 `AI_ENABLED=true` 并配置 `AI_PROVIDER=qwen`、地域匹配的 `AI_BASE_URL`、`AI_API_KEY` 和模型。使用自定义端口时同样调整 `APP_ORIGINS`。真实模型测试需预先明确调用次数及费用上限。[配置步骤](AI.md) · [百炼 API Key 指引](https://www.alibabacloud.com/help/en/model-studio/get-api-key)

备用端口联合启动已用隔离 SQLite 和 Fake Provider 实测。Vite 代理健康检查通过。独立 Worker 领取私有图片任务并返回两条候选。验收进程已停止。

## 十四、问题与后续风险

真实模型识别质量、去重效果、结构稳定性及成本尚待测量。公开截图只包含样例。真实供应商的数据处理以账号适用政策为准。当前队列的原子领取依赖 SQLite，未来迁移生产数据库时需验证等价的并发语义。既有 Starlette 对 TestClient 使用 httpx 报一条弃用提示。

## 十五、Git 信息

工作目录 `D:/桌面/mjc/fooddiary`。分支 `feature/phase-4-ai-recognition`，基于 `4042ce7782aedb0e3ebeb0c2d9e6c85e5b39473c`。最终完整 SHA 与工作区状态随推送验收结果提供。[GitHub 阶段 4 分支](https://github.com/zhenzhenqin/magic/tree/feature/phase-4-ai-recognition)

## 十六、阶段验收结论

阶段 4 代码和本地模拟达到提交审查条件。完整验收仍需真实模型联调、架构顾问审核和用户体验确认。暂停在阶段 4。
