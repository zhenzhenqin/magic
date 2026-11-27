# FoodDiary 阶段 4.2 DeepSeek 适配与联调报告

## 一、当前状态

DeepSeek 适配、费用控制、隐私授权和免费回归均使用原阶段 4 分支。此前百炼免费预检查的配置绑定、SQLite 选型及 D 盘运行规则继续生效。架构顾问审核基准为 `58d694527a25347e279ddd965bef8a01a3506e87`，本轮在其后继提交 `68e9ebb525303922b8783ad6a89a2bfe81511351` 上开发。

本轮真实模型调用为 **0 次**。已在私有配置文件写入供应商及官方地址，DeepSeek 专用 Key、最大尝试次数及费用授权尚未提供。账号模型权限、赠送额度和实际账单待核验，真实 Worker 保持关闭。

## 二、接入与安全

| 项目 | 实现 |
| --- | --- |
| 模型和接口 | `DeepSeekVisionProvider` 实现现有 `FoodRecognitionProvider`，使用 `deepseek-flash` 与 `POST https://api.deepseek.com/chat/completions`。联调地区字段 `official` 指官方统一入口，物理部署地区未验证 |
| 请求 | httpx 单次请求，内联 Base64 JPEG，`thinking.type=disabled`、`stream=false`、`response_format.type=json_object`，联调初始输出上限 1024 Token |
| 校验与错误处理 | 复用中文提示词和 Pydantic 结构。空内容、截断和非法结构安全失败，有可用 Token 时保存；鉴权失败、余额不足、限流、发送前错误和发送后结果未知保留不同状态 |
| 官方地址与任务隔离 | 配置及发送时均校验官方 HTTPS 入口，禁用重定向和环境代理。任务指纹绑定供应商、模型、端点，领取和发送时再次核对。图片完整性、所有权、幂等与恢复继续由既有 API 和 Worker 检查 |
| 图片授权 | 前端显示 DeepSeek 开放平台隐私政策并要求同意 `vision-deepseek-v1`。旧百炼授权 `vision-privacy-v1` 不满足 DeepSeek 新任务的授权要求 |

[供应商实现](../backend/app/services/ai_provider.py) · [配置校验](../backend/app/core/config.py) · [任务与恢复](../backend/app/services/ai_jobs.py) · [Worker](../backend/app/services/ai_worker.py) · [DeepSeek 视觉理解](https://api-docs.deepseek.com/zh-cn/guides/vision/) · [JSON 输出](https://api-docs.deepseek.com/zh-cn/guides/json_mode/) · [平台隐私政策](https://cdn.deepseek.com/policies/zh-CN/deepseek-open-platform-privacy-policy.html)

## 三、累计额度与费用

原隔离 SQLite 已升级至 `0006_deepseek_budget`。两家真实供应商共用单用户和全局 UTC 日额度，各有独立且跨日、重启仍有效的累计次数。DeepSeek 新增计数行，Qwen 历史保留。两个累计上限均默认 0；明确未发送的尝试释放预留，结果未知的已发送尝试保守计入。

浏览器首例与命令行各批次按所选供应商使用同一 SQLite。启动和下一例前从原账本核算既有 Token、费用和剩余次数，并为下一次请求留出保守上界。有未结清任务、历史用量未知、计数对不上或无法匹配模型、端点及价目时暂停。Worker 使用基于保守费用推导的绝对次数上限，浏览器首例模式在已消费次数上最多再放行一次。联调的 Worker 并发和每任务最大尝试次数均为 1。

DeepSeek 公布的高峰价格每百万 Token 为缓存未命中输入 CNY 2、输出 CNY 8，USD 口径分别为 0.30、1.20。按输入 1,048,576 和输出 1,024 Token 计算，下一次调用的本地保守上界约 CNY 2.1054 或 USD 0.3159。历史估算也按高峰且输入未命中计算，不抵扣赠送余额。实际费用以供应商的计量、适用价格、折扣及账单为准。公开资料说明优先使用赠送余额并提供余额查询；当前账号的赠送额度、账单与是否有可用的硬性预算设置均未验证。

[迁移](../backend/migrations/versions/0006_deepseek_budget.py) · [本地预算计算](../backend/tests/benchmark_budget.py) · [CNY 价目](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/) · [USD 价目](https://api-docs.deepseek.com/quick_start/pricing/) · [余额接口](https://api-docs.deepseek.com/api/get-user-balance/)

## 四、授权与联调顺序

在 D 盘原联调目录 `D:/DevEnv/fooddiary-phase42` 的私有 `provider.env` 填写 `AI_API_KEY`，其中已配置 `AI_PROVIDER=deepseek` 和 `AI_BASE_URL=https://api.deepseek.com`。对话只需确认最大真实调用次数及费用上限和币种。建议先授权 3 次、CNY 7，用于下表首批三例。若用户决定一次批准全部用例，可在同一预算下按已结算用量重新计算每批剩余额度。

运行原 `start-phase42-lab.ps1`，API 与 Worker 共享配置、原账本及媒体目录，使用环回端口 15176 和 18022。沿用两名隔离测试账号、12 张生成样图、11 个用例和私有 CSV 报告。首例通过浏览器完成第三方授权、识别、修改、保存、查看手账和月历、刷新核验，再验证另一账号无法读取任务及照片。同一可颂任务用于页面截图和账本取证。首次出现鉴权、接口兼容、JSON 结构或用量异常时暂停。首批三例通过并核对预算后，可执行余下八例。 [启动脚本](../scripts/start-phase42-lab.ps1) · [样例与运行参数](ai-benchmark/README.md)

| 批次 | 用例 | 预期 | 实际 |
| --- | --- | --- | --- |
| 首批 | `croissant` | 可颂或牛角包 | 待授权 |
| 首批 | `home-lunch` | 白米饭、番茄炒蛋、凉拌黄瓜 | 待授权 |
| 首批 | `not-food` | `no_food`，候选为空 | 待授权 |
| 后续 | `fried-rice` | 蛋炒饭 | 待授权 |
| 后续 | `ramen` | 日式拉面 | 待授权 |
| 后续 | `strawberries` | 草莓整份计一次 | 待授权 |
| 后续 | `milk` | 牛奶，不确定成分留空 | 待授权 |
| 后续 | `latte` | 拿铁或咖啡 | 待授权 |
| 后续 | `packaged-oats` | 燕麦饼干，图片没有营养标签 | 待授权 |
| 后续 | `same-plate` | 两个角度合并为一份番茄炒蛋 | 待授权 |
| 后续 | `blurred` | 难以辨认或标注不确定，未知营养留空 | 待授权 |

### 真实联调取证

本轮没有实际识别输出、耗时或 Token，应用账本无新增真实模型费用，供应商账单未查询。真实模型结果、截图、手账保存后的来源、刷新和账号隔离均待首例验证。此前免费预检查有手动录入截图，本轮 MockTransport 与 Playwright 结果仅用于回归。生成图片可用于联调覆盖，营养准确率需有称重、配方或可靠包装营养标签。 [此前本地手动录入截图](screenshots/phase-4.2/00-local-preflight-ai-disabled.jpg)

## 五、自动化回归

| 检查 | 结果 |
| --- | --- |
| pytest | 182 项通过，包含原有 151 项；保留现有 Starlette 弃用提示 |
| Playwright | API 14 项、模拟 AI 9 项、恢复 5 项、Worker 离线 1 项、模拟 AI 截图 2 项通过 |
| Demo | 12 项交互、9 项截图通过 |
| TypeScript 与生产构建 | TypeScript、API 构建与 Demo 构建通过 |
| Alembic | 原隔离库升级到 `0006_deepseek_budget`，模型一致性检查无待应用变更。只读核对 Qwen 和 DeepSeek 累计均为 0，未发现真实尝试记录 |
| 本地预算 CLI | 用占位值检查同一账本，3 次和 CNY 7 的示例参数得到 0 次历史调用、0 元估算、CNY 2.105344 的下一次上界。该检查仅执行 SQLite 只读查询 |

`test_deepseek.py` 覆盖单图及多图参数、空响应和截断、结构校验、鉴权和余额错误、限流、官方地址校验、授权版本、跨供应商任务隔离、累计与每日额度、发送前后传输错误及迁移。`test_benchmark_budget.py` 覆盖浏览器与两个批次跨连接累计、未知用量后暂停并保留另一供应商的历史记录。Playwright 新用例「DeepSeek 独立披露并在确认后发送对应授权版本」通过。首次并行回归有一项手账编辑点击超时，单独复跑通过，测试断言未更改。 [DeepSeek 测试](../backend/tests/test_deepseek.py) · [费用回归](../backend/tests/test_benchmark_budget.py) · [浏览器测试](../frontend/tests/ai.api.spec.ts)

## 六、磁盘与交付

D 盘继续存放仓库、工具链、缓存、隔离账本和回归数据。没有安装新的大型依赖或模型。整盘空间变化包含本机其他进程。

| 磁盘 | 本轮开始可用 | 回归结束可用 | 可用空间变化 |
| --- | ---: | ---: | ---: |
| C 盘 | 28.434 GiB | 28.422 GiB | 减少 11.83 MiB |
| D 盘 | 315.945 GiB | 315.907 GiB | 减少 38.52 MiB |

交付分支为 `feature/phase-4-ai-recognition`，代码提交为 `f205af8e08a6cd070253983347dbae03da81aa83`。提交范围核查未发现真实密钥、私有数据库、样图 Base64 或联调日志。报告提交的完整 Git SHA 及远端状态随交付消息提供。 [GitHub 分支](https://github.com/zhenzhenqin/magic/tree/feature/phase-4-ai-recognition)

真实联调仍待 Key 和明确的次数、费用授权，阶段 4 尚未达到完整验收条件。本轮停留在阶段 4.2。
