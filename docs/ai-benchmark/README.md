# Phase 4.1 百炼联调素材

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

本地流程由 `--run-local fake` 或 `--run-local qwen` 显式启用。脚本使用同源环回代理、专用已注册测试账号和给定的只读 SQLite 文件，经过现有上传、授权任务和轮询接口。若创建回包丢失，它按原键查询既有任务。脚本不直接调用百炼接口，也不会自动发起人工重试。运行结果写入新 CSV。带 `--run-local qwen` 的执行还要求匹配的 SQLite 及 Flash 配置、已批准调用次数和金额、地区、币种及核实的价格档位。

```powershell
# 本地 Fake Worker 测试命令示例
.\.venv\Scripts\python.exe -m tests.ai_benchmark --run-local fake --username benchmark_reader --database D:\DevEnv\tmp\benchmark-test.db --cases same-plate not-food --output D:\DevEnv\tmp\bench-fake.csv
```

输出记录包括模型与地区、期望和实际菜品、同义词初筛、漏识错识及重复、结构校验、应用端与 Provider 耗时、逐尝试 Token、失败与重试原因及上游请求 ID。营养合理性和近义词差异由评审者复核。估算仅在已知 Token 与有明确单价时产生，实际费用、币种和账单引用根据百炼账单补填。公开模板只有预期值。不要公开含私有样例、上游请求标识或账号信息的联调输出。

## 生成提示词

- 双角度：Generate ONE original photorealistic two-panel contact sheet, landscape, with absolutely equal left and right halves separated by a straight narrow neutral divider at the exact center, so each half can be saved as an independent test photo. Both halves depict the EXACT same home-cooked Chinese tomato-and-egg plate: a white round ceramic plate with a cobalt-blue double rim and one tiny chip, eight red tomato wedges, loose yellow scrambled egg curds and three tiny green scallion pieces, on the same plain light oak tabletop. LEFT is a straight 90-degree top-down smartphone photo; RIGHT is a noticeably low, 28-degree side perspective of the same exact plate, showing rim and food volume. Same plate, ingredients and portion, realistic soft indirect daylight and ordinary phone photo texture. Leave a little background around the plate in both halves so it does not cross the divider. No text, logos, people, watermark, decoration, other food or utensils. FoodDiary private food recognition benchmark synthetic reference.
- 包装燕麦饼干：An original realistic smartphone photo for a food recognition benchmark. A single upright generic oat biscuit retail packet with a clear lower window showing several round tan oatmeal cookies, on a plain gray tabletop. The front reads only OAT BISCUITS in legible simple type and has no company brand; no nutrition panel or made-up nutritional claim. Simple daylight, entire package centered with breathing room, no other food, person, barcode, watermarks or real logo. Landscape photograph.
- 家常三菜：An original realistic overhead smartphone photo of one home-cooked Chinese lunch on a neutral beige wooden table, three discrete elements clearly visible: an ivory bowl of plain steamed white rice, a white plate of red tomato wedges scrambled with yellow egg, and a small round shallow bowl of sliced green cucumber salad. The three dishes should not touch and all containers are fully inside the frame. Ordinary natural daylight, visible individual textures, no text or people, no cutlery, real photo appearance. Food recognition benchmark synthetic sample.
- 非食物：An original realistic smartphone photograph of a dark olive stapler and a plain spiral-bound cream notebook on a light desk. Daylight, desk background, simple everyday snapshot. No food, drink, cup, logos, handwriting, people or decorative text. Food recognition negative test synthetic sample.
- 模糊样例：An original realistic smartphone photograph of a bowl of noodle soup on a tabletop accidentally shot severely out of focus and with visible handheld motion blur; only vague dark bowl silhouette and light and warm colors are visible. Deliberately difficult to identify the contents, no text, people or logos. Food recognition uncertain-image test synthetic sample.
