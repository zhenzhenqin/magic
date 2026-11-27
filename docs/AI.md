# AI 食物识别

## 开启和配置

默认 `AI_ENABLED=false`。拍照、手动记录、手账与月历可直接使用。真实识别使用对应供应商的专用 Key，在 Git 忽略的 `.env` 或后端环境中配置。API 和 Worker 共享配置、SQLite 文件及媒体根目录。

| 变量 | 用途 |
| --- | --- |
| `AI_ENABLED=true` 和 `AI_PROVIDER=deepseek` 或 `qwen` | 开启指定适配器。开发和测试可显式使用 `fake` |
| `AI_BASE_URL` | DeepSeek 固定使用 `https://api.deepseek.com`。Qwen 使用工作空间的 HTTPS 兼容入口，结尾为 `/compatible-mode/v1` |
| `AI_API_KEY` | 服务端专用密钥，填在私有配置中 |
| `AI_MODEL` | DeepSeek 使用 `deepseek-flash`，Qwen 联调使用 `qwen3-vl-flash`。模型别名与账号权限需实测确认 |
| `JWT_SECRET`、`APP_ORIGINS` | 自建 `.env` 时同时配置。进行原库升级时沿用已有密钥，Origin 要与浏览器端口一致 |

HTTPS 地址、模型、系统提示词和密钥均由服务端决定。Qwen 工作空间优先使用控制台显示的地区地址，地区须匹配 API Key。 [百炼兼容入口](https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope) · [DeepSeek 视觉理解](https://api-docs.deepseek.com/zh-cn/guides/vision/)

```powershell
.\scripts\setup-backend.ps1 -Action Migrate
.\scripts\start-dev.ps1 -WithAiWorker -FrontendPort 15175 -BackendPort 18021
```

已有 API 进程时，可另开 PowerShell 执行 `.\scripts\setup-backend.ps1 -Action AiWorker`。Worker 无需监听端口。退出联合脚本时回收其启动的进程。缺少必要配置时能力接口报告不可用，可继续手动记录。

## Provider 与输出

`FoodRecognitionProvider.analyze(images: list[bytes])` 异步返回 `Analysis`，包含 `Recognition` 和可选的 Token 计数及上游请求 ID。`DeepSeekVisionProvider` 与 `QwenVisionProvider` 通过 httpx 向 Chat Completions 发送内联 JPEG，关闭流式输出，使用 JSON Object 模式。DeepSeek 以 `thinking={"type":"disabled"}` 关闭思考。空内容、截断、限流、余额不足及无法确定请求结果的超时有独立处理。`FakeVisionProvider` 离线返回确定性样例，生产配置拒绝启用。 [DeepSeek JSON 输出](https://api-docs.deepseek.com/zh-cn/guides/json_mode/) · [DeepSeek 思考模式](https://api-docs.deepseek.com/zh-cn/guides/thinking_mode/)

`food-zh-v1` 为中文提示词版本。DeepSeek 使用 `vision-deepseek-v1` 独立授权，Qwen 继续使用 `vision-privacy-v1`。切换供应商需要重新确认。提示模型联合理解多角度照片，忽略图中文字的指令，使用常见食物名，无法估算时留空。Schema `1` 区分 `recognized`、`no_food` 与 `unrecognized`，最多 15 个候选。分类取固定集合，重量及营养为数值或 null 并限制两位小数。拒绝额外字段、超长文本、无效 JSON、重复键、NaN 和 Infinity。明显矛盾的份量或能量值留空并带警告。

模型结果只在用户确认后写入手账。已填写的其他食物可由用户追加或明确替换。正式明细保存 UUID、候选追踪字段及估算摘要。仅改备注不影响来源。当前名称、分类或估算与原候选不同时显示人工修正。

## 任务状态与恢复

| 状态 | 行为 |
| --- | --- |
| `pending` | 等待可用时刻。创建和人工重试请求各有持久化幂等键，同账号默认只允许一个未完成任务 |
| `running` | 同一短写事务内领取任务、签发租约并预留尝试额度。先提交事务，再在内存处理图片。外部调用前记录发送意图 |
| `succeeded` | 写入经过校验的候选、结果状态与稳定 UUID。正式饮食记录仍需用户确认 |
| `failed` | 返回安全错误码。未发送的连接错误和明确限流可带退避自动重试。无效结果需手动重试。已发送但结果未知的尝试需明确确认费用风险 |
| `cancelled` | 原领取者无法发布候选。未发送的配额预留释放，已进入发送阶段的占位保留至结算或租约到期 |

重启后扫描过期租约。仅处于预留状态的任务在次数及有效期允许时重排。发送阶段失联记为结果未知，避免未经确认再次向上游提出请求。旧 Worker 的领取标识和租约必须仍有效才可发布。每分钟清理超过保留期的任务和用量，默认分别为 7 天与 30 天。任务超时默认 15 分钟，外部请求默认 40 秒，使用单独的并发槽。

## 额度和隐私

按 UTC 日统计。默认每用户 10 次、全局 30 次，Worker 并发 1，最多 3 次尝试。预留、发送与核算均在短数据库事务中。每次尝试均有状态记录，未发送不占日额度，可能已发送的超时、取消和明确限流保守计入。供应商没有提供 Token 时标记为未知。应用侧计数与供应商计费规则、其他客户端消耗及账户账单独立。

API 只接收本人媒体的 UUID。默认最多 3 张，最长边 1024 px，每张最多 640 KiB JPEG。一餐仍可保存最多 5 张。用户主动同意后，发送必要像素和固定识别提示词。重新编码不携带 EXIF、GPS 或文件名。账号标识和登录令牌均留在 FoodDiary。已发出的调用即使在本应用取消，供应商仍可能执行及计费。核对所在工作空间适用的隐私和数据保留条款。[百炼隐私说明](https://www.alibabacloud.com/help/en/model-studio/privacy-notice) · [国际站数据保留政策](https://www.alibabacloud.com/help/en/model-studio/data-retention-policy)

Phase 4.1 只允许官方公布的地域及工作空间 HTTPS 地址，设置与发送前都做校验。Worker 在读取源图时核对请求指纹、完整图片集合、所有者、顺序和 SHA-256，发送前复查文件仍可读取且快照一致。任一张缺失或损坏时整组停止，释放未发送额度。[地域与接口官方表](https://www.alibabacloud.com/help/en/model-studio/regions)

`AI_QWEN_CUMULATIVE_LIMIT` 和 `AI_DEEPSEEK_CUMULATIVE_LIMIT` 默认均为 0。发送累计在同一 SQLite 库中按供应商通过短事务更新，两家供应商共用用户和全局每日额度。累计跨 UTC 日、进程重启、用量明细清理与账号删除保留。已删除账号的历史调用行去除用户关联，仍参与保留期内的全局每日统计。DeepSeek 配置及真实发送均要求官方 HTTPS 域名，禁止跟随重定向。前端显示实际供应商及对应平台隐私政策。 [DeepSeek 开放平台隐私政策](https://cdn.deepseek.com/policies/zh-CN/deepseek-open-platform-privacy-policy.html)

Worker 每 3 秒更新共享数据库的配置心跳，12 秒未更新视为离线。浏览器可按登录身份查询待处理或本表单未采用的结果，页面刷新或浏览器关闭后由用户显式恢复。服务器支持按创建键与重试键读取原任务。恢复加载原照片，核对餐次和照片顺序后由用户主动采用。Worker 离线时保留已有任务，手动录入可继续。

Phase 4.2 新任务还绑定规范化端点摘要，包含 Provider、模型及带地域或工作空间的服务地址，排除 API Key。领取和发送分别检查。端点变化或历史任务缺少绑定时，保留历史并阻止发送，重新选图并确认后才建立新任务。

默认媒体账户额度 200 MiB 和 1000 张，适合开发验证。生产容量、备份、SQLite 到其他数据库的并发语义适配以及模型延迟留待对应阶段确认。

## 实际模型测试

截至本轮适配交付，真实调用为 0。模型账号权限、耗时、识别质量、用量和费用仍待实测。MockTransport 验证 Qwen 和 DeepSeek 的请求与响应处理，浏览器 Fake Provider 仅用于流程验证。

授权后使用 10～15 张原创或可合法使用的无隐私食物照片。覆盖家常菜、主食、水果、饮料、甜点、包装食品、模糊和非食物照片，以及同一道菜的两种角度。先验证首选模型，再在同一预算内决定是否对比候选模型。按任务记录实际模型与地区、耗时、漏识别和重复识别、结构校验、营养估算合理性、Token 和实际可得账单。营养值只能与称重、配方等基准对照验证准确率。

Phase 4.1 已准备 12 张图片及 11 个用例。首轮只测试 `qwen3-vl-flash`，建议最多批准 12 次可能收费的尝试、USD 1 测试预算。百炼国际站文档列出按账号、工作空间或 Key 的月预算及到限停服，亦列出停服延迟和适用范围。需以所用账号控制台可用设置及实际账单为准。 [样例、脚本和空表](ai-benchmark/README.md) · [百炼预算管理](https://www.alibabacloud.com/help/en/model-studio/budget-management)

Phase 4.2 改用 `deepseek-flash`，在 `D:/DevEnv/fooddiary-phase42` 复用原持久化账本并保留 Qwen 历史记录。浏览器首例和后续命令行批次共用 DeepSeek 次数及预算，自动重试关闭。失败、未知用量、未知估算或异常状态会暂停后续提交。 [Phase 4.2 联调说明](PHASE-4.2.md)
