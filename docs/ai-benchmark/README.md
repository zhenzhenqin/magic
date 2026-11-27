# 食物识别模型联调素材

共 12 张无隐私测试图片，组成 11 个请求用例。[样例清单](cases.json) · [结果记录表](results-template.csv)

| 组成 | 来源和使用方式 |
| --- | --- |
| 可颂、蛋炒饭、拉面、草莓、牛奶、拿铁 | FoodDiary 阶段 1 原创生成素材，以原 WebP 作为单图对照 |
| 家常三菜、燕麦饼干包装、模糊汤面、订书机与笔记本 | 本次内置 ImageGen 生成的四张独立原图，导出为 JPEG |
| 番茄炒蛋俯视与低角度 | 本次内置 ImageGen 生成一组双画面。同一蓝边盘和食物分别裁成两个 JPEG，联合发送为一个去重用例 |

全部是生成样例，适合验证识别、去重及估算合理性。包装样例无营养标签，素材无可复核称重值。若需验证营养准确率，另准备按实际份量称重、带可核配方或包装营养标签的食物，并在评审表记录基准来源。 [阶段 1 素材来源](../ASSETS.md)

## 脚本

在项目的 `backend` 目录，从 D 盘临时环境运行。无参数仅校验样例，使用 `--output` 可生成一张新结果空表。脚本保留已有 CSV。

```powershell
.\.venv\Scripts\python.exe -m tests.ai_benchmark
.\.venv\Scripts\python.exe -m tests.ai_benchmark --output D:\DevEnv\tmp\fooddiary-benchmark.csv
```

本地流程由 `--run-local fake`、`--run-local deepseek` 或 `--run-local qwen` 显式启用。脚本使用同源环回代理、专用已注册测试账号和给定的只读 SQLite 文件，经过现有上传、授权任务和轮询接口。若创建回包丢失，它按原键查询既有任务。上游请求由 Worker 发出。脚本不会自动发起人工重试，结果写入新 CSV。真实适配器还要求匹配的 SQLite 及 Flash 配置、已批准的调用次数和金额、接口地区、币种及核实的价格档位。

真实联调时，给 `start-phase42-lab.ps1` 传入 `-Provider deepseek` 或 `-Provider qwen`、用户批准的总次数 `-AuthorizedCallLimit` 和同一组 `-BudgetOptions`。预算选项包含 `--region`、`--approved-budget`、`--currency`、`--price-reference` 及 `--price-tier 上限:输入单价:输出单价`，单价按每百万 Token 填写。DeepSeek 指定 `--region official`，公开高峰价对应的参数为 CNY `--price-tier 1048576:2:8` 或 USD `--price-tier 1048576:0.30:1.20`。Qwen 按账号地域核实 32768、131072、262144 三档。首个浏览器用例同时使用 `-FirstBrowserCall`，后续批次继续使用原账本及授权，并通过 `-BenchmarkOptions` 选择用例。 [DeepSeek CNY 价目](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/) · [DeepSeek USD 价目](https://api-docs.deepseek.com/quick_start/pricing/) · [百炼模型价目](https://help.aliyun.com/zh/model-studio/model-pricing)

启动及每批提交前从原账本按供应商重新汇总浏览器和命令行的历史调用，校验累计次数、Token、地域端点和适用档位。下一次调用使用模型完整上下文与配置输出上限计算保守上界。用量未知、状态未结清、明细缺失或价格无法对应时暂停。本地估算用于控制联调，供应商账单仍以其计量、适用费用和结算规则为准。

预算较低时，DeepSeek 的首次单图浏览器测试可同时使用 `-FirstBrowserCall -CompactDeepSeekRequest -AuthorizedCallLimit 1`。该模式限制序列化请求为 64 KiB、最多 1024 个输出 Token，并在发送前拒绝超限输入。使用公开 CNY 高峰价时，单次本地保守预留为 CNY 0.174080。该模式使用原账本的绝对累计上限，已有一次已发送调用的账本会停止启动。 [实际联调](../PHASE-4.2.md)

```powershell
# 本地 Fake Worker 测试命令示例
.\.venv\Scripts\python.exe -m tests.ai_benchmark --run-local fake --username benchmark_reader --database D:\DevEnv\tmp\benchmark-test.db --cases same-plate not-food --output D:\DevEnv\tmp\bench-fake.csv
```

输出记录包括模型与地区、期望和实际菜品、同义词初筛、漏识错识及重复、结构校验、应用端与 Provider 耗时、逐尝试 Token、失败与重试原因及上游请求 ID。营养合理性和近义词差异由评审者复核。已知 Token 且有明确单价时生成估算，实际费用、币种和账单引用根据供应商记录补填。公开模板只有预期值。含私有样例、上游请求标识或账号信息的联调输出保留在联调目录。

## 生成提示词

- 双角度：Generate ONE original photorealistic two-panel contact sheet, landscape, with absolutely equal left and right halves separated by a straight narrow neutral divider at the exact center, so each half can be saved as an independent test photo. Both halves depict the EXACT same home-cooked Chinese tomato-and-egg plate: a white round ceramic plate with a cobalt-blue double rim and one tiny chip, eight red tomato wedges, loose yellow scrambled egg curds and three tiny green scallion pieces, on the same plain light oak tabletop. LEFT is a straight 90-degree top-down smartphone photo; RIGHT is a noticeably low, 28-degree side perspective of the same exact plate, showing rim and food volume. Same plate, ingredients and portion, realistic soft indirect daylight and ordinary phone photo texture. Leave a little background around the plate in both halves so it does not cross the divider. No text, logos, people, watermark, decoration, other food or utensils. FoodDiary private food recognition benchmark synthetic reference.
- 包装燕麦饼干：An original realistic smartphone photo for a food recognition benchmark. A single upright generic oat biscuit retail packet with a clear lower window showing several round tan oatmeal cookies, on a plain gray tabletop. The front reads only OAT BISCUITS in legible simple type and has no company brand; no nutrition panel or made-up nutritional claim. Simple daylight, entire package centered with breathing room, no other food, person, barcode, watermarks or real logo. Landscape photograph.
- 家常三菜：An original realistic overhead smartphone photo of one home-cooked Chinese lunch on a neutral beige wooden table, three discrete elements clearly visible: an ivory bowl of plain steamed white rice, a white plate of red tomato wedges scrambled with yellow egg, and a small round shallow bowl of sliced green cucumber salad. The three dishes should not touch and all containers are fully inside the frame. Ordinary natural daylight, visible individual textures, no text or people, no cutlery, real photo appearance. Food recognition benchmark synthetic sample.
- 非食物：An original realistic smartphone photograph of a dark olive stapler and a plain spiral-bound cream notebook on a light desk. Daylight, desk background, simple everyday snapshot. No food, drink, cup, logos, handwriting, people or decorative text. Food recognition negative test synthetic sample.
- 模糊样例：An original realistic smartphone photograph of a bowl of noodle soup on a tabletop accidentally shot severely out of focus and with visible handheld motion blur; only vague dark bowl silhouette and light and warm colors are visible. Deliberately difficult to identify the contents, no text, people or logos. Food recognition uncertain-image test synthetic sample.
