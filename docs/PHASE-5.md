# FoodDiary 阶段 5 贴纸与视觉专项报告

## 一、阶段完成情况

在已审查基础提交 `26ad3aca2cb7fff9b4dc6fe721b2862ce38bbc8e` 上完成本地 CPU 抠图、真实图鉴和黑白纸质手账。照片可自动制作贴纸，确认保存后在手账、详情、月历和图鉴显示。关闭付费识别时仍可完整使用本地贴纸。等待架构顾问审查及用户视觉验收。

## 二、模型、依赖与许可证

| 项目 | 值 |
| --- | --- |
| 模型及缓存 | rembg 发布的 `u2netp.onnx`，`D:/DevEnv/models/rembg/u2netp.onnx`，4,574,861 B |
| SHA-256 | `309c8469258dda742793dce0ebea8e6dd393174f89934733ecc8b14c76f4ddd8` |
| 上游校验 | rembg 会话文件的 MD5 为 `8e83ca70e441ab06c318d82300c84806`，实物匹配 |
| 实际运行 | Python 3.13.9、ONNX Runtime CPU 1.26.0、NumPy 2.4.1、Pillow 13.0.0。单线程且仅 CPU Provider |
| 独立环境 | `D:/DevEnv/fooddiary-phase5/worker`，`pip check` 无依赖冲突。CPU 额外包为 ORT、NumPy、FlatBuffers、Protobuf |
| 程序许可 | rembg 2.0.88 上游程序为 MIT。实际部署仅需 Python ONNX Runtime CPU 会话及 Pillow。ONNX Runtime 程序为 MIT |
| 权重许可 | U²-Net 上游仓库为 Apache-2.0，作者提供 U²-NetP 预训练权重。rembg 发布的 ONNX 转换文件附有校验，未发现该单独附件的许可声明，公开部署或重新分发前仍需确认权重许可范围 |

可独立安装 CPython 3.13 Windows x86-64 CPU wheel。Linux x86-64 wheel 的 glibc 标签与 Debian 11 的 glibc 版本兼容，服务器实际依赖、线程调度及峰值仍待验证。完整 rembg 安装遇到大体积传递依赖的下载停滞，改用已验证同权重和等效归一化流程的 CPU 会话。

[rembg 程序](https://pypi.org/project/rembg/2.0.88/) · [权重来源](https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx) · [U²-Net 上游](https://github.com/xuebinqin/U-2-Net) · [上游许可](https://github.com/xuebinqin/U-2-Net/blob/master/LICENSE) · [ONNX Runtime wheel](https://pypi.org/project/onnxruntime/1.26.0/) · [ONNX Runtime 许可](https://github.com/microsoft/onnxruntime/blob/main/LICENSE)

## 三、性能与选型

浏览器实际采用 768 px 预处理和 320×320 内部模型输入。16 张样例连续推理，统一单线程，包含编码两个派生图。冷启动 1.107 秒。模型加载后未推理的工作集约 68.5 MiB。首次默认内存池测试峰值约 584 MiB，关闭内存池和内存模式后最高约 332 MiB。独立推理进程结束时约 78.6 MiB，较首次加载后增加约 10 MiB。常规样本大多在 2～4 秒，模糊汤面在 768 px 耗时约 5.9 秒。

| 输入最长边 | 16 张总时间 | 本批后累计峰值工作集 | CPU 时间占一个核心 |
| --- | ---: | ---: | ---: |
| 512 px | 30.041 秒 | 322.1 MiB | 95.2% |
| 768 px | 47.068 秒 | 326.1 MiB | 94.7% |
| 1024 px | 49.112 秒 | 332.3 MiB | 96.9% |

`u2net` 对照权重未下载。`u2netp` 在常见单份食物上可用，按 768 px 提供清晰贴纸并控制局部图的体积。复杂餐盘、模糊照片和透明玻璃仍有裁剪与残留，保留原图及手动裁剪路径。本地工作集为推理进程测量，部署需计入 API、Worker 父进程、SQLite 与反向代理。

## 四、16 个质量样例

下表为 768 px 的实测。照片组含 Pexels 许可实拍 9 张、阶段 4 原创生成样图 6 张、空白曝光控制 1 张。每行均保留原图和真实运行结果。贴纸大小为完整白边 WebP 的字节数。

| 用例 | 来源 | 原图 → 贴纸尺寸 | 时间 ms | 贴纸 B | 人工观察 |
| --- | --- | --- | ---: | ---: | --- |
| 空白控制 | 合成曝光控制 | 700×630 → 无 | 24 | — | 前景不明确，返回失败并保留原图 |
| 模糊汤面 | 阶段 4 | 960×720 → 697×563 | 5895 | 249568 | 右侧明显残留，碗边软糊 |
| 复杂餐盘 | Pexels | 1200×1480 → 651×787 | 4398 | 698232 | 主盘在，右下盘沿及少量米饭误删，上方有背景残片 |
| 可颂 | Pexels | 1200×1504 → 248×382 | 2726 | 93840 | 可颂完整，盘子及阴影去掉，边缘自然 |
| 非食物 | 阶段 4 | 960×720 → 608×551 | 2355 | 110014 | 抠出订书机与本子，显著性模型无食物分类能力 |
| 炒饭 | Pexels | 1200×800 → 530×363 | 2067 | 165110 | 正面碗完整，背景食物移除，碗底有轻微阴影 |
| 家常三菜 | 阶段 4 | 877×960 → 718×748 | 4268 | 359466 | 三个盘碗同属整餐贴纸，米饭边缘较软 |
| 透明冰饮 | Pexels | 1200×1800 → 230×482 | 3233 | 90186 | 杯身保留，透明杯脚有少量背景 |
| 冰拿铁 | Pexels | 1200×1600 → 404×572 | 2148 | 73080 | 贴近背景的杯子主体保留，几处浅边 |
| 包装燕麦饼干 | 阶段 4 | 960×640 → 308×446 | 2063 | 128166 | 包装完整，图案文字保留 |
| 拉面 | Pexels | 1200×800 → 336×434 | 3018 | 110714 | 主碗完整，筷尖较淡 |
| 草莓 | Pexels | 1200×1800 → 471×478 | 3494 | 193562 | 草莓和白盘保留，红色及淡阴影自然 |
| 番茄炒蛋俯拍 | 阶段 4 | 883×887 → 540×528 | 3712 | 291580 | 食物保留，盘沿被去掉 |
| 番茄炒蛋侧拍 | 阶段 4 | 883×887 → 772×457 | 3331 | 336458 | 食物和盘子均保留，结果依角度不同 |
| 白盘可颂 | Pexels | 1200×1800 → 456×463 | 2220 | 96136 | 保留部分叉勺，盘缘略软 |
| 白碗米饭 | Pexels | 1200×800 → 421×415 | 2117 | 171992 | 整碗米饭保留，米白区域细节略软 |

[图板一](screenshots/phase-5/quality-comparison-1.jpg) · [图板二](screenshots/phase-5/quality-comparison-2.jpg) · [Pexels 许可](https://www.pexels.com/license/) · [前期样例记录](ai-benchmark/README.md)

实拍图片来源。[可颂](https://www.pexels.com/photo/photo-of-a-croissant-on-a-plate-16543194/) · [复杂餐盘](https://www.pexels.com/photo/cooked-food-on-stainless-steel-tray-10078270/) · [炒饭](https://www.pexels.com/photo/fried-rice-in-a-bowl-13065212/) · [透明杯](https://www.pexels.com/photo/glass-of-iced-latte-with-ice-cubes-20220698/) · [拿铁](https://www.pexels.com/photo/chilled-iced-latte-beverage-on-rustic-surface-31939227/) · [拉面](https://www.pexels.com/photo/bowl-of-ramen-4224210/) · [草莓](https://www.pexels.com/photo/strawberries-in-bowl-4397050/) · [白盘可颂](https://www.pexels.com/photo/croissant-on-plate-10526473/) · [米饭](https://www.pexels.com/photo/a-bowl-of-cooked-rice-8923092/)

## 五、资源、迁移与数据完整性

任务行按所有者、媒体摘要和处理参数复用。短写事务领取单全局租约与新令牌，独立子进程推理后回写，超时或中断时有限恢复。三个派生文件均属于同一原图。浏览器只接受授权 Blob，切换账号或卸载组件释放 Object URL。单用户配额与全局磁盘剩余在发布前复核。活跃任务和餐次引用保护原图，已脱离引用的文件走保留期及 dry-run。

`0007_stickers_catalog` 完成 0006 库升级及旧食物回填。在阶段 4.2 的只读快照上比较升级前后数据，2 个账号、2 餐、2 条食物明细、2 张图片、1 个 AI 任务、1 条用量与两项累计预算的内容逐表保持一致，新增 2 条图鉴关联，外键检查通过。原阶段 4.2 库保留 DeepSeek 累计 1 次。

图鉴按食物名称及有限别名归类，使用有效餐次统计，提供自定义显示名、分类、封面、收藏和事务合并。

[贴纸任务和存储](STICKERS.md) · [图鉴数据规则](CATALOG.md) · [回归用例](../backend/tests/test_stickers_catalog.py)

## 六、视觉专项及截图

应用背景灰白，纸页暖白，灰阶组件使用原创建牌及拍照图标。周报注明待开放。日期环表示当天有用餐记录，未知热量保持未知。首页连续纸页、左侧装订孔、稳定旋转的真实双列贴纸，图鉴沿用纸页及手写标题。安卓及浏览器表单仍用系统字体。手机底部三个入口，顶部提供饭搭子和我的，桌面保留五项侧栏。

`FoodDiary Hand` WOFF2 由霞鹜文楷 v1.530 重新命名并按常用简体及数字子集化，880,256 B，保留 SIL OFL 1.1 和原作者版权。缺字回退系统字。真实拍照和手账截图均来自 Chrome，标注为测试账号。用户提供的参考截图只用于设计。

[新版 390×844](screenshots/phase-5/05-notebook-390x844.jpg) · [新版 430×932](screenshots/phase-5/05-notebook-430x932.jpg) · [新版桌面](screenshots/phase-5/05-notebook-desktop.jpg) · [旧版对照](screenshots/phase-4/06-saved-private-diary.jpg) · [全部浏览器截图](screenshots/phase-5/README.md) · [字体原版](https://github.com/lxgw/LxgwWenKai/releases/tag/v1.530) · [字体许可证](../frontend/src/assets/fonts/OFL-LXGW-WenKai.txt)

## 七、自动化和隔离测试

| 检查 | 结果 |
| --- | --- |
| 后端 pytest | 193 项通过，包含基准 184 项与新增 9 项。保留原有 Starlette 测试客户端弃用提示 |
| API 模式 | 14 项通过，覆盖账号会话、图片续期及饮食记录 |
| 识别、恢复与离线 | 模拟识别 9 项、恢复 5 项、Worker 离线 1 项通过 |
| 本地贴纸与图鉴 | 2 项浏览器测试通过，覆盖原图、抠图、贴纸切换，生成中保存，失败降级、裁剪、图鉴和跨浏览器回读 |
| Demo | 12 项交互及响应式测试通过 |
| 历史截图回归 | 认证 2 项、手账 1 项、模拟识别 2 项、Demo 9 项通过 |
| 类型与构建 | TypeScript 检查、API 与 Demo 构建通过 |
| Alembic | 0007 为当前版本，模型一致性检查无待应用变更，旧库快照核对通过 |
| 真实联调 | 浏览器使用真实 CPU Worker，开启六张有背景的样例，贴纸和图鉴跨刷新可读 |

新增后端测试覆盖源图摘要、幂等、不同账号的任务及媒体读取、竞争领取、取消重试、租约恢复、不阻塞正常保存、失败保留原图、磁盘与用户额度以及图鉴编辑删除和合并。并行迭代中曾出现前端编辑及恢复用例超时，复跑通过。新首页在纸页总计、单条记录和展开的营养小结中显示相同热量时，旧截图测试会匹配多个元素。现已在展开的小结内核验原热量值，重跑通过。

## 八、磁盘与交付

启动从项目根使用 `.\scripts\setup-sticker-worker.ps1 -Action Install`、`.\scripts\setup-backend.ps1 -Action Migrate` 和 `.\scripts\start-dev.ps1 -WithStickerWorker`。本轮实际在 D 盘独立库通过 15177／18023 启动，关闭外部识别。费用账本验证阶段 5 付费调用 **0 次**。

独立 Worker 环境实测约 175.5 MiB，CPU 四个 wheel 合计约 24.6 MiB。模型缓存为 D 盘，4.36 MiB。阶段 5 联调目录约 280 MiB，含环境、样例、输出和隔离数据库。磁盘读数包含本机其他进程。

| 驱动器 | 开始可用 | 结束可用 | 变化 |
| --- | ---: | ---: | ---: |
| C 盘 | 28.398 GiB | 28.407 GiB | +10.13 MiB |
| D 盘 | 316.459 GiB | 317.015 GiB | +569.29 MiB |

分支为 `feature/phase-5-stickers-catalog`，代码提交为 `299486154a9f0ab2996ded39deda665f6b75a114`。交付提交的完整 SHA 与工作区状态随交付消息提供。 [GitHub 分支](https://github.com/zhenzhenqin/magic/tree/feature/phase-5-stickers-catalog)

阶段 5 代码、迁移和真实浏览器视觉证据已交付，等待审核与用户实机视觉验收。正式部署前需核对权重再分发许可，测试低内存 Linux 上的 SQLite、备份及 CPU 并发。
