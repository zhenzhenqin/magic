# 技术选型与关键决策

记录日期为 2026-11-25。阶段 0 采用可审查的兼容版本线。具体补丁版本和依赖锁文件由对应实施阶段通过构建或安装验证后确定。

| 决策 | 初步选择 | 依据及验证时点 |
| --- | --- | --- |
| Web 与包管理 | Vue 3、TypeScript、Vite 8、Tailwind CSS、原创组件。优先使用 pnpm，统计阶段使用 ECharts | 现有 Node.js 22.19.0 达到 Vite 8 的 Node 22 门槛。本机 pnpm 可运行。阶段 1 验证安装、开发启动和生产构建 |
| Android | Capacitor 8 候选，保留现有 JDK 21.0.9 | 当前 Node.js 满足 Capacitor 8 要求。阶段 9 核验实际 Android Studio、SDK 36、Build Tools、Gradle 与 Android Gradle Plugin 组合 |
| 后端 | Python 3.13、FastAPI、SQLAlchemy 2.x、Alembic | 本机 Python 3.13.9 用于实际 API。阶段 5 核验 Linux x86_64 的图像依赖与 ONNX Runtime wheel |
| 数据库 | SQLite 为少量亲友使用版本的首选 | 采用文件库、WAL、外键及短写事务。MySQL 8.4 LTS 为未来高并发扩展候选 |
| AI 食物识别 | 服务端通过百炼的 OpenAI 兼容接口接入 Qwen3-VL | 首测候选 `qwen3-vl-flash`，对照候选 `qwen3-vl-plus`。实际地区权限、质量、延迟与费用待联调 |
| CPU 抠图 | rembg、ONNX Runtime CPU、Pillow，独立 Worker | 阶段 5 优先测 `u2netp` 与单任务并发，结合质量、峰值 RSS、CPU 和吞吐量决定模型、上线并发及 Worker 部署位置 |
| 图片存储 | 私有本地文件系统，预留对象存储接口 | 起步组件较少。项目需验证访问授权、备份恢复和真实图片存储增长 |
| 部署 | Docker Compose + Nginx，结合试运行确定部署位置 | 现有主机 Compose 可用，旧业务停服后 80/443 空闲、可用内存约 1.5 GiB。阶段 8 依据压测、安全支持、入口和运维授权确定部署方案 |

阶段 5 采用 rembg 发布的 u2netp 权重，使用独立的 ONNX Runtime CPU 与 Pillow 处理环境。关闭 ONNX 内存池以降低驻留和推理峰值，维持单任务并发。原创建牌与黑白控件搭配暖白纸页和开源手写字体子集。 [实际测量](PHASE-5.md)

版本依据。[Vite 8 发布说明](https://vite.dev/blog/announcing-vite8) · [Capacitor 8 环境要求](https://capacitorjs.com/docs/getting-started/environment-setup) · [Capacitor 8 Android 迁移指南](https://capacitorjs.com/docs/updating/8-0) · [MySQL LTS 说明](https://dev.mysql.com/doc/refman/8.4/en/mysql-releases.html) · [rembg 依赖与平台配置](https://github.com/danielgatis/rembg/blob/main/pyproject.toml)

## 阶段 1

| 决策 | 实施 |
| --- | --- |
| Vue 原型 | Vue 3.5.46、TypeScript 5.9.3、Vite 8.3.8、Vue Router 4.6.5、Pinia 3.0.4 和 Tailwind CSS 4.3.5。通过项目的 pnpm 锁文件复现 |
| 浏览器持久化 | 类型化 Mock Repository 统一提供记录和共享投影。localStorage 保存小体积演示数据，IndexedDB 保存重新编码的照片 Blob。账号切换复用同一套授权模型 |
| 响应式和图片 | 手机底部导航预留系统安全区，桌面使用侧边栏和受约束的内容列。12 张透明 WebP 本地打包，标题用本地 Noto Serif SC 子集 |
| 当前阶段的缓存 | 通过 `scripts/setup-dev-env.ps1` 使 pnpm store、npm cache、`PLAYWRIGHT_BROWSERS_PATH` 与 `TEMP / TMP / TMPDIR` 生效到 `D:/DevEnv`。Vite 缓存、依赖、构建、测试结果及截图留在 D 盘项目。Playwright 复用现有 Chrome |
| 后续 Python 和 Android 磁盘 | Python 虚拟环境设在 D 盘项目，`PIP_CACHE_DIR=D:/DevEnv/pip-cache`。SDK 使用 `D:/DevEnv/Android/Sdk`，模拟器数据放 `D:/DevEnv/Android/avd`，`GRADLE_USER_HOME=D:/DevEnv/gradle`。APK 和测试产物放在 D 盘 |
| 后续模型、Docker 与 WSL | Hugging Face、rembg 和 ONNX 缓存按工具支持的变量配置到 `D:/DevEnv/models`。使用 Docker Desktop 官方支持的方法把数据文件设到 `D:/DevEnv/docker`，新增 WSL 发行版优先在 D 盘存放虚拟磁盘。已有工具继续复用 |

后续目录按需创建。大型资源下载、解压、构建和测试使用 D 盘路径。

## 阶段 2

| 决策 | 实施 |
| --- | --- |
| 数据库 | SQLite 用于阶段 2 本地开发，通过 `DATABASE_URL` 配置。外键开启，WAL 和 5 秒忙等待。MySQL 8.4 仍为生产候选，尚未验证 |
| 依赖 | Python 3.13.9 保持不变，锁文件固定运行和测试依赖。pip 配置隔离在项目进程，虚拟环境在 `backend/.venv` |
| 认证 | Argon2id + HS256 短期 JWT + 可撤销和轮换的不透明刷新凭据。每次受保护请求查询关联会话 |
| Web 交付 | Vite 静态选择 API 或 Demo 根模块与路由。API 生产构建排除 Demo 数据模块，开发用 Vite Proxy 转发同源请求 |
| 测试 | pytest 和 Playwright 使用各自 D 盘隔离 SQLite 库及临时密钥，避免修改开发数据 |

## 阶段 3

| 决策 | 实施 |
| --- | --- |
| 饮食写入 | SQLite 保持 WAL。按账号串行化短写事务，数据库约束防止跨账号图片关联。创建以幂等键判重，编辑使用版本号 |
| 时间与数值 | 保存 UTC、用餐时区、确认的本地日期。营养未知保留 null，摘要提供已知数和完整性 |
| 私有媒体 | Pillow 13.0.0、python-multipart 0.0.34。流式限额、WebP 规范化、私有存储、单解码槽与超期孤立回收 |
| 多标签页会话 | 旧 Bearer 只能绑定其签名会话，不能续期或清除不同会话 Cookie。标签页身份变更时清除先前数据和在途请求 |
| 前端 | API 模式调用真实用户接口，月历只请求当月摘要和缩略图。Demo 路由与数据源维持独立 |


## 阶段 4

- 复用 httpx、Pydantic 与 Pillow。使用有明确版本的中文提示词和 JSON Object 输出，再做应用侧严格校验与估算合理性检查。
- 任务、配额和请求重放使用同一文件 SQLite。短写事务领取和结算，网络请求在事务外。发送情况未知时保留额度记录，并由用户明确确认后再试。
- 暂定每日每用户 10 次、全局 30 次，按 UTC 结算。项目记录尝试和供应商返回的 Token，不猜测账单价格。
- 候选归属于账号和识别任务，采用稳定 UUID。确认保存后复制精简来源到明细，让正式历史独立于任务保留期。
- 停在本地开发与模拟验收。中国内地或国际站账号应用各自工作空间的地址及策略，实际地区由联调账号决定。[百炼兼容接口](https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope)

## 阶段 4.2

- 保留 SQLite 文件库。AI Worker 的 `BEGIN IMMEDIATE` 和健康心跳 upsert 采用 SQLite 语义，满足当前轻量部署方向。正式部署验收需实际演练数据库与媒体一致性备份和恢复，测量写入并发、忙等待和磁盘配额，并设定低空间保护。未来切换 MySQL 需重新验证领取、结算和跨请求幂等。
- 识别任务保存不含密钥的服务端点摘要。Worker 在领取和发送前绑定原 Provider、模型、工作空间或地域端点、授权和提示词版本。迁移后的未绑定任务不能再发送，原有完成结果可继续读取。
- 真实模型联调只计划 `qwen3-vl-flash`。使用一个持久化隔离账本、先做三例技术验证、禁用自动重试。凭据和明确预算授权齐备后再执行。

## 阶段 6

- 好友关系使用规范化用户对。方向授权绑定关系 ID，权限使用九位标记，固定本地日期为共同历史边界。关系重新建立时分配新的 ID。
- 共享响应由专用字段投影生成。好友图鉴从存量用餐明细重算，用标准名称规则分组。本人图鉴的别名、收藏、选封面及合并偏好留在本人范围。
- SQLite 联合归属与日期索引支撑共享过滤，使用批量查询取当前页的说明和缩略图。仅在前台以 25 秒间隔刷新，同时支持焦点、网络恢复及手动触发。
- 在 SQLite 使用短期全局预留共享媒体空间，原图与现有贴纸 Worker 沿用同一可配置磁盘下限。 [共享设计](SHARING.md)

## 阶段 7.2

- 以应用内相机为 API 模式新增入口。Web 用 MediaDevices，预留 Android 适配契约。客户端压缩以及真实抠图产物驱动动画，服务器保持单 API 进程、SQLite 和独立贴纸 Worker。
- 原图展示偏好保存在单条餐次的图片关联，兼容旧客户端和幂等记录。原图及贴纸的授权仍独立核验。 [拍照架构](CAMERA.md)

## 阶段 7.3

- 个人 AI 使用有期限的进程内凭据。生产识别关闭，DeepSeek 是否允许受托使用终端用户凭据等待供应商明确。
- 邮箱沿用原用户表，挑战采用独立 HMAC 签名和 SQLite 原子消费。生产默认关闭注册，邀请码与 SMTP 均需显式配置。
- 选择日常食物标本册，使用连续纸页、横向导航与现有食物照片，保留黑白方向轻量对照。 [阶段报告](PHASE-7.3.md)
