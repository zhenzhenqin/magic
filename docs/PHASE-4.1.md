# FoodDiary Phase 4.1 整改报告

审核基准为 `feature/phase-4-ai-recognition` 上的 `e6ae1693b4efadb377f07748faa59536ab070b58`。本轮完成代码整改、迁移、本地联调和样例准备。真实百炼调用为 0。本阶段仍待架构顾问第二轮审核和用户验收。

## 一、基准复现与逐项处理

先在基准代码上运行四个预期保护用例。基准均未通过，分别确认了非百炼地址可通过配置、删去一张输入关联后剩余照片仍进入 Provider、账号删除释放当天全局用量，以及缺少按原请求键只读恢复入口。这四个用例在整改后通过。

| 审核意见 | 实际处理与代码定位 |
| --- | --- |
| 1. 费用控制与账号删除 | [ai_control.py](../backend/app/services/ai_control.py) 的 `reserve_qwen_call()`、`refund_qwen_call()` 和 [ai_worker.py](../backend/app/services/ai_worker.py) 的 `dispatch()`、`finish()` 将累计发送量与尝试状态同事务写入。真实累计额度默认 0。跨日、Worker 重启、历史明细清理和账号删除均不重置。明确未发送可退回，自动重试及可能已发送的结果未知尝试按次保守计入。每日用户与全局限制保留。账号删除将用量行的归属置空，保留期内继续计入全局每日统计。 |
| 2. Provider 地址安全 | [config.py](../backend/app/core/config.py) 的 `validate_qwen_base_url()` 按官方地域和工作空间域名精确匹配 HTTPS 本路径。Provider 在 [ai_provider.py](../backend/app/services/ai_provider.py) 的 `analyze()` 发送前再次校验。保留禁自动重定向与禁环境代理。既有输入拒绝额外字段、配置只由服务端决定，复用这些保护与 MockTransport。 |
| 3. 前端任务恢复 | [ai.py](../backend/app/api/ai.py) 的 `/ai/jobs/recover` 与 [ai_jobs.py](../backend/app/services/ai_jobs.py) 的 `recover_job()` 按认证账号查询。创建或重试回包丢失时用原键只读查找。刷新、关闭再开、短时断网都可恢复已存在的任务，仍可取消。 [useMealRecognition.ts](../frontend/src/composables/useMealRecognition.ts) 的 `restore()`、`postWithRecovery()` 和 `matchesSelection()` 校验餐次与完整照片顺序，恢复后由用户主动采用候选。切换身份时撤销旧前端请求和结果引用。 |
| 4. Worker 输入完整性 | [ai_worker.py](../backend/app/services/ai_worker.py) 的 `photo_records()`、`photos()`、`dispatch()` 核对账号、原集合、顺序、请求指纹、规范化文件字节与 SHA-256。调度时重复检查关联和文件状态。删图、缺关联、重排、损坏或读后文件消失都会阻断本次发送。 |
| 5. AI 来源与前端 | [meal_sources.py](../backend/app/services/meal_sources.py) 的 `verify_candidate()` 要求新采用的候选匹配编辑餐次及原始图片。原照片从草稿移除时，保留已填文本，解除该草稿来源。历史已保存的来源保留。连续识别可明确追加或替换。过期候选可保留字段并转手动。现有同餐候选唯一、任务只用于一餐、已有明细 ID 和备注编辑保护通过回归。 [diary.py](../backend/app/services/diary.py) 的 `daily()` 与手账页保留未知、已知零值，并分别提示涉及估算、人工修正、模拟的统计值。 |
| 6. Worker 健康检查 | [ai_control.py](../backend/app/services/ai_control.py) 的 `mark_heartbeat()` 和 `worker_online()` 与 Worker 共享 SQLite。每 3 秒更新，12 秒未更新视为离线。API 仍可保存手动记录，任务继续保留。额外用隔离库实际终止一个本次启动的 Fake Worker 进程，确认心跳过期、API ready 保持，新进程领取原任务且只尝试一次。 |

新增迁移 [0004_ai_recovery.py](../backend/migrations/versions/0004_ai_recovery.py) 已升级本地开发库。测试用旧阶段 3 及阶段 4 的非空库均通过，阶段 4 的任务、媒体关联、旧请求指纹、历史状态及累计计数回填已核对。

## 二、自动化与实测

| 检查 | 实际结果 |
| --- | --- |
| 后端 pytest | 140 项通过，含基准 111 项和新增 29 项 |
| 原 API Playwright | 14 项通过 |
| 原 AI Playwright | 8 项通过 |
| Phase 4.1 恢复 Playwright | 5 项通过 |
| Worker 离线 Playwright | 1 项通过 |
| Demo Playwright | 12 项交互与响应式、9 项截图通过 |
| 原截图场景 | 认证 2 项、手账 1 项、识别 2 项通过，历史截图保留 |
| TypeScript、API/Demo 生产构建及包隔离 | 通过 |
| Alembic 一致性检查 | `0004_ai_recovery` 为 head，未检出待应用操作 |
| 联调脚本 | 无网络校验 12 张图片和 11 个用例，在本地 Fake Worker 联调 2 个用例并生成记录 |

构建与双模式联调曾触发 Windows 下 Vite 优化缓存的并发重命名冲突。将优化缓存按模式和端口划分后，使用原有断言重跑。

### 新增后端测试

以下名称及参数化组均通过，详见 [test_phase41.py](../backend/tests/test_phase41.py) 和 [Provider 测试](../backend/tests/test_ai_provider.py)。

- `test_untrusted_qwen_host_is_rejected`、`test_qwen_endpoint_rejects_variants_outside_the_allowlist`（8 例）、`test_qwen_endpoint_allows_documented_regional_variants`（3 例）、`test_mutated_settings_are_rechecked_before_constructing_a_request`。
- `test_global_attempt_history_survives_owner_deletion`、`test_qwen_cumulative_counts_automatic_retry_and_survives_midnight_restart_and_purge`、`test_before_send_refund_and_dispatch_lease_unknown_keep_budget_conservative`、`test_two_prepared_workers_can_consume_only_one_final_cumulative_slot`、`test_cancel_after_dispatch_then_settle_does_not_return_a_paid_slot`。另保留单任务多 Worker 领取和旧租约写回回归。
- `test_partial_photo_set_never_reaches_provider`、`test_incomplete_or_changed_bytes_fail_before_dispatch`（4 例）、`test_recover_lost_create_response_is_owner_scoped`、`test_recovery_edit_context_and_expired_candidates_keep_manual_save_available`。
- `test_heartbeat_stales_and_comes_back_without_affecting_manual_meals`、`test_ai_source_requires_original_media_and_summary_distinguishes_unknown_zero_and_edited`、`test_phase_4_upgrade_backfills_count_without_losing_jobs_links_or_history`、`test_benchmark_fixture_validation_and_csv_comparison`。

### 新增浏览器测试

- 刷新和关闭标签页后恢复原照片，候选须显式采用。
- 网络中断后只恢复轮询，保留一次创建。
- 重试回包丢失后按原重试标识恢复。
- 更换识别输入后保留文本，删除输入解除草稿来源。
- 连续识别需明确替换，零值和人工修正在手账中可见。
- Worker 未启动时显示状态，仍可手动保存。

另加强原创建回包丢失用例，断言恢复前后任务 ID 相同且只出现一次创建 POST。[Playwright 测试](../frontend/tests/ai.api.spec.ts)

### 前端实际运行截图

本机 Chrome 访问本地真实 API 和 Fake Worker，使用无隐私测试素材。 [刷新后的恢复入口](screenshots/phase-4.1/01-restore-after-reload.jpg) · [候选等待人工采用](screenshots/phase-4.1/02-recovered-before-apply.jpg) · [已人工修正和零值](screenshots/phase-4.1/03-manually-edited-nutrition.jpg) · [Worker 离线的手动录入](screenshots/phase-4.1/04-worker-offline-manual.jpg)

## 三、真实模型联调准备和预算建议

准备了 12 张原创生成样例、11 个用例，包含单食物、多菜家常餐、主食、水果、饮品、包装食品、多角度、模糊和非食物。联调脚本支持有序上传、原键恢复、结构与同义词初筛、逐尝试耗时、Token、失败原因及计费对照。营养合理性需人工复核，准确率验证需额外准备可靠称重、配方或真实营养标签。 [样例、提示词、脚本和结果表](ai-benchmark/README.md)

建议只测试 `qwen3-vl-flash`。在独立本地联调库建议最多 **12 次可能收费的尝试、USD 1 测试预算**，11 个基本用例再预留 1 次失败空间。批准后可设置累计与每日限制各 12，Worker 并发 1，输出上限 1024 Token。以官方北京低档费率输入 0.022 USD、输出 0.215 USD 每百万 Token 为例，假设每次输入 32,000、输出 1,024 Token，12 次估算约 USD 0.0111。实际地区、Token 档位、计费、优惠和汇率以选择的账号及供应商账单为准。 [百炼模型定价](https://www.alibabacloud.com/help/en/model-studio/model-pricing)

百炼国际站文档支持在账号、工作空间或 API Key 范围设置月预算、告警和到限停服。月预算有适用范围，且停服存在延迟，延迟期间仍可能计费。独立测试工作空间及专用 Key 可把测试和其他消费分开。若对应模型与账户控制台提供免费额度用完即停，可考虑启用。当前没有账号验证，需由用户确认相关控制实际可用性。 [百炼预算管理](https://www.alibabacloud.com/help/en/model-studio/budget-management) · [账单与成本管理](https://www.alibabacloud.com/help/en/model-studio/bill-query-and-cost-management)

## 四、磁盘、Git 与工作区

| 磁盘 | 开始可用 | 测试与截图验收后可用 | 变化 |
| --- | ---: | ---: | ---: |
| C 盘 | 28.684 GiB | 28.602 GiB | 减少 83.98 MiB |
| D 盘 | 314.862 GiB | 314.744 GiB | 减少 120.82 MiB |

整盘读数包含其他进程活动。继续使用 D 盘依赖、测试库、构建和素材目录。内置 ImageGen 按工具默认路径在 C 盘保存约 11 MiB 源图，供项目使用的 JPEG 已导出到 D 盘。未新增依赖或下载本地模型，未触发磁盘限制。验收端口与测试 Worker 均确认停止。

最新代码整改提交为 `4c5496e5dd8f00350c698b6bb9663efa4568443c`，直接基于审核基准。报告用独立文档提交随同分支交付。最终远端提交 SHA 及工作区同步状态在交付消息中提供。 [GitHub 分支](https://github.com/zhenzhenqin/magic/tree/feature/phase-4-ai-recognition)

## 五、未完成事项及已知边界

- 真实百炼的账号权限、地区、模型响应、Token 和供应商账单待专用 Key 及有限费用授权。本次外部付费调用 0 次。
- 本地累计计数以该 SQLite 账本为边界。删除库或换新独立库会改变基线，迁移只能回填旧库中仍存在的用量。停用后留存原账本供核对。
- 浏览器恢复范围是服务端已持久化的任务及其参与识别的图片。本地尚未上传的照片、未保存的手动文字需重新添加。
- Worker 心跳最长约 12 秒才从在线变为离线。网络发送结果未知仍保守处理。既有 Starlette TestClient 发出一条弃用提示，测试通过。

整改停止在 Phase 4.1，等待架构顾问第二轮审核和用户授权。阶段 4 完整验收仍待真实模型联调。
