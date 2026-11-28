# 阶段 7.3 个人 AI、账号安全与原创界面

## 范围与基准

保留审查基准 `9ee0722902fd608573953a3bd963d0ee800847e1`，并在其后续已推送的 Exam Guardian 备份提交 `286114eca1ca86fa049bfc276d5df3270b091283` 上建立 `feature/phase-7.3-byok-identity-design`。服务器只读复查仍为 Debian 11.1，系统升级与生产部署暂停，未修改旧项目。未安装 Android 工具或构建 APK。

功能代码提交为 `2a6765ec4d0ff0b0b3f1caf0e81ac8214a77b2a1`。阶段证据与汇报作为后续文档提交，完整报告版本以远端阶段分支为准。 [GitHub 阶段分支](https://github.com/zhenzhenqin/magic/tree/feature/phase-7.3-byok-identity-design)

## 服务和安全

| 项目 | 实际处理 |
| --- | --- |
| 模拟 BYOK | `ai_credentials.py` 的进程内存以账号、会话、随机版本和期限约束连接。FastAPI 管理同进程模拟 Worker。领取、预留、发起和自动或手动重试复核凭据。 |
| 个人费用 | `ai_jobs.py` 与 `ai_worker.py` 按账号和版本执行。旧任务无法换用新 Key。SQLite 保留历史账本，个人页面仅聚合该用户自己的 BYOK 记录。未知尝试保守计入，显示可用 Token 及个人限额。 |
| 真实出站 | 生产 Fake、旧全局 Key 及真实模型请求关闭。余额通过固定官方路径的 MockTransport 验证。清除提示说明已发送调用可能结算。 |
| 供应商政策 | DeepSeek 开放平台协议第 2.4 条要求保护且不共享 API Key。公开条款未明确答复第三方代管终端用户的 Key。临时真实调用和加密长期保存待供应商确认。 |
| 邮箱与会话 | 用户名和已验证邮箱密码、邮箱验证码注册和登录、绑定、更换、找回、设备撤销、密码修改及账号删除均进入原用户体系。生产默认关闭注册。邀请码在验码事务中原子消费，可通过本机管理命令创建或撤销。 |
| 邮件安全 | 独立 HMAC、验证码用途隔离、五次错误限制、单次消费及邮箱、IP、全局限流。SMTP 支持 TLS 465 与 STARTTLS 587。测试使用本地模拟邮箱。 |
| 第三方入口 | QQ、小米 OAuth 的实际个人开发者资质和零费用条件未验证，保持未接入。Apple、微信和短信也未接入。 |
| 备份 | 旧会话和共享授权在隔离恢复副本撤销，过期及未执行任务不会自动发起调用。临时密钥不随数据库恢复。旧邮箱挑战与邀请码在恢复副本失效。 |

两个账号的自动化测试观察到 Worker 分别收到发起人的测试标记，且两个账本记录具有不同的凭据引用。其他账号无法读取任务或连接。数据库及 WAL 检查未出现测试明文，HTTP 响应与捕获日志同样通过检查。真实收费 AI 和真实 SMTP 发信均为 **0 次**。 [个人 AI 详情与 DeepSeek 协议](BYOK.md) · [认证与第三方核验](AUTH.md) · [API](API.md)

## 迁移与历史数据

新增 `0011_personal_identity`，向现有用户、会话和 AI 表增加可空字段与默认值，并新增挑战、邀请码表。旧数据库的原文件保持只读，比较在 D 盘候选副本完成。

| 迁移样本 | 前后验证 |
| --- | --- |
| 本地开发库 `0004_ai_recovery` | 原有业务计数相同，旧 Qwen 额度行保留。经过较早的 DeepSeek 迁移时，供应商账本行数从 1 增至 2。 |
| 阶段 7.2 浏览器库 `0009_meal_photo_display` | 34 用户、35 会话、15 餐次与明细、26 份媒体、20 份派生、15 条图鉴、2 段好友关系及 2 条共享授权前后相同。旧账户登录后，旧私有 WebP 可读取。 |
| 自动化历史夹具 | 从阶段 2、3 和 4 的表结构写入旧记录。升级后验证旧会话轮换、幂等、媒体内容、识别结果及非空费用账本。 |

两份本机候选库到达 `0011_personal_identity`，SQLite 完整性、外键和 Alembic 模型一致性检查通过。旧开发库首次按账本总行数比较时发现预期的 DeepSeek 初始行增加，改按供应商逐条核对了旧值。

## 设计

方向 A 为暖白编辑式食物标本册。方向 B 为黑白摄影手账。登录页提供同一 Vue 页面两个运行态方向的轻量比较，默认采用 A。桌面页眉、移动端主导航、餐次纸页、图鉴分隔、好友阅读页、拍照确认和账号列表使用同一品牌。相机仍读取实际 400 px 透明缩略图播放动效。真实主体与原图同坐标配准的评估见设计规范。 [设计规范](DESIGN-SYSTEM.md)

## 浏览器实测证据

18 张 PNG 和两段 WebM 来自 Windows Chrome 实际运行。测试账号使用真实认证 API，邮件投递到本地模拟邮箱，AI 使用测试响应。相机由授权样例视频驱动，抠图使用 WSL 的真实 CPU ONNX。原始文件在 D 盘阶段目录。用例实测 390×844、430×932 和 1280×900。手机软键盘、安全区和实际设备兼容仍需真机验证。

| 场景 | 实际截图或录屏 |
| --- | --- |
| 登录设计 | [A 暖纸密码登录](screenshots/phase-7.3/01-password-login.png) · [B 黑白探索](screenshots/phase-7.3/00-exploration-monochrome.png) · [邮箱验证码登录](screenshots/phase-7.3/02-email-code-login.png) |
| 连接与设置 | [首次 AI 引导](screenshots/phase-7.3/03-first-ai-connection.png) · [AI 设置](screenshots/phase-7.3/04-ai-settings.png) · [个人设置](screenshots/phase-7.3/15-profile.png) · [账号安全](screenshots/phase-7.3/16-account-security.png) |
| 相机 | [取景](screenshots/phase-7.3/05-camera.png) · [原图冻结](screenshots/phase-7.3/06-captured.png) · [轮廓与渐隐](screenshots/phase-7.3/07-cutout-reveal.png) · [确认贴纸](screenshots/phase-7.3/08-sticker-confirmation.png) |
| 入账与浏览 | [入账动画](screenshots/phase-7.3/09-placement.png) · [今日手账](screenshots/phase-7.3/10-diary.png) · [桌面手账](screenshots/phase-7.3/17-diary-desktop.png) · [月历](screenshots/phase-7.3/11-calendar.png) · [图鉴](screenshots/phase-7.3/12-catalog.png) |
| 好友 | [好友手账](screenshots/phase-7.3/13-friend-diary.png) · [好友列表](screenshots/phase-7.3/14-friends.png) |
| 连续操作 | [注册、登录、拍照、抠图和保存录屏](screenshots/phase-7.3/author-camera-flow.webm) · [邮箱登录及好友同步录屏](screenshots/phase-7.3/friend-sync.webm) |

集成用例从快门到贴纸就绪约 **6.57 秒**。用户保存后，另一浏览器的手账自动刷新出已授权贴纸。撤销后，旧贴纸地址返回 404。相机专项也验证了保留草稿、相册替代、断网续传、摄像头轨道释放、减少动态效果和手动记录。在该专项的本地样本中，快门到贴纸响应为 7.85 秒，缩略图 124,630 字节，解码约 15 毫秒。上述结果来自开发机。

已用 Chrome 核对两段 WebM 均可读取，时长分别为 40.28 秒与 33.80 秒。测试采集物仅包含样例照片和隔离测试账号。

## 回归与构建

- 后端 pytest **235 项通过**，其中 16 项为本阶段的 `test_personal_identity.py`。涉及 A/B 密钥隔离、清除/替换/到期/重启/注销/切换、未知用量幂等、余额请求、备份恢复、发信失败、邮箱枚举、并发消费、邀请码和账号删除。保留 Starlette 原测试客户端弃用提示。
- 浏览器 53 项通过。真实 API 14 项，模拟 AI 9 项，恢复 5 项，Worker 离线 1 项，贴纸 2 项，三账号共享 2 项，Demo 12 项，真实 ONNX 相机专项 7 项，阶段 7.3 集成 1 项。实际 Android、iPhone 和线上表现仍待验收。
- TypeScript 和 Vite 生产构建通过。测试环境复用现有工具、模型和 Linux wheelhouse。首次 Windows ONNX 启动发现开发虚拟环境缺少推理包，后续使用 D 盘 WSL 的离线包完成实际 ONNX 运行。

| Web 发布体积 | 阶段 7.2 字节 | 当前字节 | 增量 |
| --- | ---: | ---: | ---: |
| 完整发布目录 | 2,061,125 | 2,085,187 | 24,062 |
| JavaScript 合计 | 253,239 | 273,602 | 20,363 |
| 入口 JavaScript | 121,927 | 124,734 | 2,807 |
| CSS 合计 | 58,230 | 61,929 | 3,699 |

| 开发机空间 | 开始可用字节 | 结束采样可用字节 | 可用空间变化 |
| --- | ---: | ---: | ---: |
| C 盘 | 31,764,930,560 | 31,764,885,504 | 减少 44 KiB |
| D 盘 | 303,914,532,864 | 303,593,652,224 | 减少约 306 MiB |

测试库和构建、录制、浏览器缓存及离线 Linux 推理包均在 D 盘。整盘采样也受其他系统活动影响。本轮启动的本地联调服务已停止。

## 待审核

真实 DeepSeek 用户密钥托管及长期保存等待供应商明确。正式 SMTP、QQ 或小米资格与费用、手机真机，以及云端资源与未上线环境的生产表现仍需单独验收。阶段 7.2 服务器维护、生产发布与阶段 8 Android APK 继续暂停。
