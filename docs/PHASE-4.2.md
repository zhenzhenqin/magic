# FoodDiary 阶段 4.2 联调预检查报告

## 一、阶段完成情况

已完成免费预检查、端点一致性整改、隔离环境、调用安全检查和自动化回归。当前停在真实联调授权节点。没有配置专用百炼 API Key，未收到调用次数和费用授权，真实模型验收未执行。

本次环境位于 `D:/DevEnv/fooddiary-phase42`，使用独立 SQLite、私有图片根目录、两名本地测试账号和环回端口 15176／18022。Windows 目录权限限定为运行用户和 SYSTEM。API 与 Worker 由同一启动脚本共享配置。两名账号登录通过，已用 Chrome 演练正常手动保存。验收进程已停止，真实模型能力关闭，原开发数据库和 Demo 数据未用于联调。

## 二、阶段 4.1 补充问题

- **配置绑定**。增量迁移 `0005_ai_processing_context` 为新任务记录不含密钥的 Provider、模型和地域／工作空间端点摘要。在领取及发送前分别核对摘要，同时检查原提示词及用户授权版本。更换地域或同地域工作空间后，旧任务须由用户重新确认并创建。历史结果保留，无法证明原端点的任务不能继续发送。密钥轮换不改变端点绑定。 [任务服务](../backend/app/services/ai_jobs.py) · [Worker](../backend/app/services/ai_worker.py) · [迁移](../backend/migrations/versions/0005_ai_processing_context.py)
- **数据库选型**。SQLite 是当前少量亲友使用版本的首选。MySQL 是将来高并发扩展候选。正式部署仍需验证备份、恢复、写入并发、WAL 文件和低空间保护。 [决策记录](DECISIONS.md)
- **凭据与费用**。累计上限仍默认 0。隔离账本保留，启动脚本遇到缺失的已有账本会要求恢复。检查了实际预检日志、测试输出和 Git 内容，未发现完整测试密码、Key 或图片 Base64。真实模型仍需专用凭据与明确授权。 [联调启动脚本](../scripts/start-phase42-lab.ps1)
- **分批验证**。脚本要求显式选择真实用例，每个任务只允许一次尝试。在鉴权、传输、参数、结构、状态异常或用量／费用估算未知时记录原因并暂停，避免继续发起下一例。 [联调记录脚本](../backend/tests/ai_benchmark.py)

## 三、模型、地域及参数

本轮计划模型只有 `qwen3-vl-flash`。官方文档列出 Qwen3-VL 图片 Data URI、OpenAI 兼容 Chat Completions 和非思考模式 JSON Object，应用另做 Pydantic 校验。请求预设为内联 JPEG、`stream=false`、`enable_thinking=false`、`response_format={"type":"json_object"}`、1024 输出 Token、Worker 并发 1、每任务尝试 1 次。实际账号的模型权限、所在地、端点及参数兼容性待首批核实。 [视觉与图像 Token](https://docs.modelstudio.console.alibabacloud.com/en/model-studio/vision) · [Chat 接口字段](https://www.alibabacloud.com/help/en/model-studio/qwen-api-via-openai-chat-completions) · [结构化响应](https://www.alibabacloud.com/help/en/model-studio/qwen-structured-output) · [地域及工作空间](https://www.alibabacloud.com/help/en/model-studio/regions)

## 四、授权和实际调用

用户授权次数与金额尚未提供。建议最多 12 次可能计费的尝试，费用授权不超过 USD 1 或确认的等值人民币。真实调用 **0 次**。独立数据库的 AI 任务、尝试日志和 Qwen 累计均为 0。

只需将所属地域工作空间的 `AI_BASE_URL` 和专用 `AI_API_KEY` 填入本机私有文件 `D:/DevEnv/fooddiary-phase42/provider.env`，再确认地域、最多尝试次数和费用上限。无需通过对话传输 Key。授权后按同一 SQLite 的累计账本设置绝对上限，并使用对应端口启动 API 与 Worker。

```powershell
.\scripts\start-phase42-lab.ps1 -PrepareOnly
.\scripts\start-phase42-lab.ps1
```

上述命令可用于初始化和零费用启动。经用户批准后才可用 `-AuthorizedCallLimit` 开启真实调用。同一脚本的 `-BenchmarkOptions` 将已确认的参数转给联调工具，CSV 写入私有 `reports` 目录。保持同一个账本和相同绝对上限。 [百炼创建 API Key](https://www.alibabacloud.com/help/en/model-studio/get-api-key)

## 五、逐例预期与实际

已离线校验 12 张公开生成样图和 11 个用例，私有预检结果表位于 `D:/DevEnv/fooddiary-phase42/reports/preflight-cases.csv`。首批可先在浏览器用可颂完成真实闭环，并以同一任务记录耗时与用量，再单独提交家常午餐和非食物样例。首批成功并核对账本后再执行余下八例。

| 批次 | 用例 | 预期 | 真实结果 |
| --- | --- | --- | --- |
| 首批 | `croissant` | 可颂或牛角包 | 未执行 |
| 首批 | `home-lunch` | 白米饭、番茄炒蛋、凉拌黄瓜 | 未执行 |
| 首批 | `not-food` | `no_food`，候选为空 | 未执行 |
| 后续 | `fried-rice` | 蛋炒饭 | 未执行 |
| 后续 | `ramen` | 日式拉面 | 未执行 |
| 后续 | `strawberries` | 草莓整份计一次 | 未执行 |
| 后续 | `milk` | 牛奶；不确定成分留空 | 未执行 |
| 后续 | `latte` | 拿铁或咖啡 | 未执行 |
| 后续 | `packaged-oats` | 燕麦饼干；样图无营养标签 | 未执行 |
| 后续 | `same-plate` | 两角度合并为一份番茄炒蛋 | 未执行 |
| 后续 | `blurred` | 难以辨认或标明不确定，未知营养留空 | 未执行 |

## 六、识别效果与耗时

尚无真实供应商响应，识别效果、漏识、错识、去重、实际延迟和营养估算合理性均未测。本地 Fake Provider 和 MockTransport 用于回归。

## 七、Token、费用与账单

本轮无真实 Token 用量和供应商账单数据，未产生本轮模型调用费用。以阿里云中国站所列 Flash 低档位 0.15 元输入、1.50 元输出每百万 Token 为示例，若每次输入 32,000、输出 1,024 Token，12 次约 0.076 元。这只是指定地区、档位和输入假设下的应用估算。图像按预处理后视觉 Token 折入输入，实际计量与费用查 API 用量和账单。试用额度是否存在、剩余额度和控制台停服选项待核验。百炼国际站支持适用范围内的预算告警与到限停服，停服有延迟。 [中国站模型价格](https://help.aliyun.com/zh/model-studio/qwen3-vl-flash) · [免费额度](https://www.alibabacloud.com/help/en/model-studio/new-free-quota) · [供应商预算管理](https://www.alibabacloud.com/help/en/model-studio/budget-management)

## 八、前端截图

已截取运行中的隔离环境手动录入页，照片使用原创生成样例。浏览器验证真实 API 保存成功。此图无真实或模拟的模型输出。实际模型驱动的保存、月历、刷新及另一账号访问隔离需在首批闭环时验证。 [本地截图](screenshots/phase-4.2/00-local-preflight-ai-disabled.jpg)

## 九、自动化回归

| 检查 | 结果 |
| --- | --- |
| pytest | 151 项通过，保留原 140 项并新增 11 项 |
| API、AI、恢复、Worker 离线 Playwright | 分别 14、8、5、1 项通过 |
| Demo | 12 项交互、9 项截图通过 |
| TypeScript、API/Demo 生产构建及包隔离 | 均通过 |
| Alembic | 隔离库升级到 `0005_ai_processing_context`，无待应用操作 |
| Git 与日志扫描 | 无运行数据库、私有账户文件、密钥或图片 Base64 纳入变更 |

新增用例覆盖跨地域和同地域换工作空间、领取后切换端点、旧任务缺少绑定、密钥轮换、零额度默认拒绝以及首批失败／未知用量后停止。原 Starlette TestClient 的现有弃用提示仍出现。 [新增测试](../backend/tests/test_phase42.py)

## 十、磁盘占用

| 磁盘 | 开始可用 | 预检结束可用 | 变化 |
| --- | ---: | ---: | ---: |
| C 盘 | 28.567 GiB | 28.570 GiB | 增加 2.63 MiB |
| D 盘 | 316.053 GiB | 316.017 GiB | 减少 36.19 MiB |

沿用 D 盘依赖、缓存、浏览器临时目录和测试数据。整盘读数包含本机其他进程。未安装依赖、SDK 或本地模型。

## 十一、未解决事项及局限

待核验百炼账号权限、模型兼容、Token 及实际费用，待执行真实模型前端闭环。当前样图可验证技术与识别表现。营养准确率需称重、配方或可靠包装营养标签，真实生活照片体验待用户主动授权。没有调整云服务器、Docker 或 WSL。

## 十二、Git 交付

分支 `feature/phase-4-ai-recognition`，基准 `74777dbda949eac32883410b341f5c813bfdcacb`，代码提交 `4789889eb5a607ceac837428b22d41115b305ef5`。报告用独立提交记录，分支最终完整 SHA 及工作区同步核验随交付消息提供。 [原阶段 4 分支](https://github.com/zhenzhenqin/magic/tree/feature/phase-4-ai-recognition)

## 十三、验收结论

免费预检查通过，真实联调未完成，阶段 4 尚未达到最终验收条件。暂停在阶段 4.2 等待授权和架构顾问审核。
