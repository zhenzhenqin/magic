# FoodDiary 阶段 4.2 DeepSeek 适配与联调报告

## 一、当前状态

DeepSeek 适配、费用控制、隐私授权和免费回归均使用原阶段 4 分支。此前百炼免费预检查的配置绑定、SQLite 选型及 D 盘运行规则继续生效。架构顾问审核基准为 `58d694527a25347e279ddd965bef8a01a3506e87`，本轮在其后继提交 `68e9ebb525303922b8783ad6a89a2bfe81511351` 上开发。

本轮真实模型调用为 **1 次**，在原联调账本完成了可颂识别、人工修正、保存、刷新、月历和账号隔离。用户要求费用低于人民币 1 元，按仅一次调用执行，本地启动预算设为 CNY 0.20。真实 Worker 已停止，原账本保留。

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

DeepSeek 公布的高峰价格每百万 Token 为缓存未命中输入 CNY 2、输出 CNY 8，USD 口径分别为 0.30、1.20。通用流程按模型完整上下文估算，单次约 CNY 2.1054。低预算首例由 `-CompactDeepSeekRequest` 启用，服务端在发送前核对正好一张图片、序列化请求最多 64 KiB、输出最多 1024 Token。保守估算按请求体每字节预留一个 Token，另预留 1,024 个图片 Token 及 16,384 个封装 Token，合计预留 CNY 0.174080。应用端预算保护以公开价格和该请求范围计算；实际费用以供应商的计量、适用价格和账单为准。

[迁移](../backend/migrations/versions/0006_deepseek_budget.py) · [本地预算计算](../backend/tests/benchmark_budget.py) · [CNY 价目](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/) · [USD 价目](https://api-docs.deepseek.com/quick_start/pricing/) · [余额接口](https://api-docs.deepseek.com/api/get-user-balance/)

## 四、授权与联调顺序

使用用户配置的专用 Key。调用前通过官方只读接口确认凭据有效、`deepseek-flash` 可见，账号赠送余额为零。按当前授权仅执行可颂。后续联调继续沿用原 SQLite、已消耗次数和已结算费用，待用户另行授权后再执行家常午餐和非食物样例。

运行原 `start-phase42-lab.ps1`，API 与 Worker 共享配置、原账本及媒体目录，使用环回端口 15176 和 18022。沿用两名隔离测试账号、12 张生成样图、11 个用例和私有 CSV 报告。首例通过浏览器完成第三方授权、识别、修改、保存、查看手账和月历、刷新核验，再验证另一账号无法读取任务及照片。同一可颂任务用于页面截图和账本取证。首次出现鉴权、接口兼容、JSON 结构或用量异常时暂停。首批三例通过并核对预算后，可执行余下八例。 [启动脚本](../scripts/start-phase42-lab.ps1) · [样例与运行参数](ai-benchmark/README.md)

| 批次 | 用例 | 预期 | 实际 |
| --- | --- | --- | --- |
| 首批 | `croissant` | 可颂或牛角包 | 识别为「可颂（牛角面包）」，单一结果，JSON 校验通过 |
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

| 取证项 | 实际结果 |
| --- | --- |
| 模型、入口与尝试 | `deepseek-flash`，`official` 入口，累计 1 次，任务成功，无重试 |
| 供应商请求耗时 | 2.617 秒 |
| Token 与费用 | 输入 519，输出 92。全部输入按缓存未命中、高峰价计算，估算 CNY 0.001774。供应商余额接口在调用前后显示到分的结果相同，精确账单金额未取得 |
| 营养展示 | 模型估算 60 g、245 kcal，页面显示估算及不确定性。生成样图没有可复核的称重及营养基准 |
| 保存与刷新 | 浏览器将名称改为「原味可颂」，保存返回 201，来源为 `ai_edited`，供应商为 `deepseek`，保存记录引用原任务。刷新能查看饮食详情，月历能返回该记录 |
| 账号隔离 | 另一测试账号读取任务、原照片、缩略图及手账均返回 404。恢复接口返回空结果 |
| 结束状态 | SQLite 保留，累计 DeepSeek 1、Qwen 0。原账本的只读预算检查已拒绝第二次调用。联调 API、页面及 Worker 已关闭，默认累计额度仍为 0 |

[识别结果截图](screenshots/phase-4.2/01-real-deepseek-croissant-result.jpg) · [保存后刷新截图](screenshots/phase-4.2/02-real-deepseek-croissant-saved.jpg)

## 五、自动化回归

| 检查 | 结果 |
| --- | --- |
| pytest | 184 项通过，包含原有 151 项；保留现有 Starlette 弃用提示 |
| Playwright | 本次真实浏览器闭环及模拟 AI 9 项通过。适配时已通过 API 14 项、恢复 5 项、Worker 离线 1 项、模拟 AI 截图 2 项 |
| Demo | 适配时通过 12 项交互、9 项截图 |
| TypeScript 与生产构建 | 适配时通过 TypeScript、API 构建与 Demo 构建。本次仅调整后端与联调脚本 |
| Alembic | 原隔离库在 `0006_deepseek_budget`，真实调用后检查模型一致性，无待应用变更 |
| 本地预算与真实启动 | 通用上界拒绝低预算。单图模式通过 MockTransport 验证合规可颂与发送前拒绝超限输入，新的预算回归验证单次预留和到限停止。首次启动发现 PowerShell `$provider` 与 `-Provider` 参数重名，修正后成功进入浏览器联调 |

`test_deepseek.py` 覆盖单图及多图参数、空响应和截断、结构校验、鉴权和余额错误、限流、官方地址校验、授权版本、跨供应商任务隔离、累计与每日额度、发送前后传输错误及迁移。`test_benchmark_budget.py` 覆盖浏览器与两个批次跨连接累计、未知用量后暂停并保留另一供应商的历史记录。Playwright 新用例「DeepSeek 独立披露并在确认后发送对应授权版本」通过。首次并行回归有一项手账编辑点击超时，单独复跑通过，测试断言未更改。 [DeepSeek 测试](../backend/tests/test_deepseek.py) · [费用回归](../backend/tests/test_benchmark_budget.py) · [浏览器测试](../frontend/tests/ai.api.spec.ts)

## 六、磁盘与交付

D 盘继续存放仓库、工具链、缓存、隔离账本和回归数据。没有安装新的大型依赖或模型。整盘空间变化包含本机其他进程。

| 磁盘 | 单次联调开始可用 | 回归结束可用 | 可用空间变化 |
| --- | ---: | ---: | ---: |
| C 盘 | 28.427 GiB | 28.422 GiB | 减少 4.70 MiB |
| D 盘 | 316.493 GiB | 316.460 GiB | 减少 33.60 MiB |

交付分支为 `feature/phase-4-ai-recognition`，DeepSeek 适配代码提交为 `f205af8e08a6cd070253983347dbae03da81aa83`，低预算联调代码提交为 `a6ecadac6dffa2d8a844ec0872b0493950448ec6`。提交范围核查未发现真实密钥、私有数据库、样图 Base64 或联调日志。报告提交的完整 Git SHA 及远端状态随交付消息提供。 [GitHub 分支](https://github.com/zhenzhenqin/magic/tree/feature/phase-4-ai-recognition)

真实浏览器闭环已验证。余下 10 例受本次授权次数限制未执行，阶段 4 完整验收仍待架构顾问审核。本轮停留在阶段 4.2。
