# FoodDiary 阶段 7.4 · 生产服务收尾与真实 Web 内测

**状态**　生产候选已构建。本地回归、真实 ONNX 浏览器链路与旧业务备份复核已完成。云服务器升级、实际部署和真实手机验收等待恢复维护授权。2026 年 11 月 28 日，北京时间。

## 1. 邀请码和邮箱安全

| 改动 | 实际处理与证据 |
| --- | --- |
| 发信前验证 | `backend/app/services/identity.py` 的 `issue` 在 SQLite 写事务核对邀请码，拒绝缺失、无效、过期、撤销和耗尽的码。发信只预留邮件额度。注册事务以同一条件原子消费验证码和邀请码。两个合法验证码竞争最后一次邀请时只有一个注册成功。 |
| 邮箱状态和发信额度 | 未验证邮箱控制权前的邮件请求处理不依赖邮箱注册状态。保留每邮箱每小时 5 次、每 IP 每小时 12 次、60 秒重发间隔。初始生产环境设全局每日 30 次，失败的上游发送也消耗一个预留，失败验证码不可消费。 |
| 旧验证码和会话 | `backend/app/api/identity.py` 及 `identity.invalidate_challenges` 使改密、重设、绑换邮箱及账号删除前的相关挑战失效。绑定和换绑验证码的 HMAC 绑定发起会话。敏感写操作在事务内复查活动会话与凭据快照，密码登录的会话写入也检查密码哈希与登录身份是否仍匹配。 |
| 账号删除与并发 | 删除取消未发送的 AI 预留并保留去关联的用量历史。照片与贴纸按所有权级联清理，迟到的 Worker 写入无法发布。原图上传最终写入前重新确认账号仍存在。`api/ai.py` 在断开连接、修改额度时进事务复查会话。 |
| 前端和代理 | `AuthPage.vue` 与 `authRepository.ts` 发送邀请码，邮件禁用时隐藏不可用入口。Nginx 覆盖外部 `X-Forwarded-For`，Uvicorn 只信任回环。本地代理演练验证伪造来源被替换，云端上线后需复验实际客户端 IP。 |
| SMTP 配置缺陷 | 首次 Linux 安装复现 `SMTP_PORT=465` 从环境文件按字符串解析失败。修复为接收整数配置并验证仅 465/587，覆盖两种端口和拒绝 25。最终发布 SHA 包含该修复。 |

## 2. BYOK 与真实 DeepSeek

现有临时密钥在 API 进程内存，默认 1 小时，受发起会话期限约束。请求只引用账号、会话及凭据版本。主动清除、退出、会话撤销、账号切换、到期和进程重启使旧任务无法取得凭据。密钥不进入浏览器持久化、数据库、备份或任务。进程内删除不承诺物理擦除。用户及凭据版本绑定识别，历史管理员费用账本和临时个人模拟记录独立。可能已发出的请求保守结算，服务器暂存期限到期无法撤回上游已收到的请求。

正式启用等待供应商澄清和用户具体授权。供应商咨询草稿已写好，本轮未发送。官方公开条款给出集成和密钥保护要求，个人 Key 的服务端临时持有仍待供应商明确。真实模式需要独立启用条件、官方 HTTPS、个人账本与模拟及历史账本区分、保留幂等和未知结果、先余额查询后做一次另行获准的有预算识别。现有模拟开关继续只供开发。后续可提供 1、12、24 小时授权并取当前有效会话期限为上界；当前沿用 1 小时。 [真实联调顺序和可转发邮件](BYOK.md#可转发的供应商邮件) · [官方 API 联系渠道](https://api-docs.deepseek.com/api/get-user-balance/)

## 3. SMTP

从上海现有云服务器实际连接 `smtp.qq.com:465`，验证主机名、TLS 1.3 与证书链，OpenSSL 返回校验成功。未认证 SMTP 账户，587 未从服务器实际验证，真实邮件 0 封。实际发件人及账户发送限制待 QQ 控制台核对。生产模板采用独立 `EMAIL_CODE_SECRET`、`EMAIL_DAILY_LIMIT=30` 和 `EMAIL_MODE=disabled`。本地捕获验证码完成模拟账号注册和登录，找回密码由后端回归覆盖。基础 MVP 可使用管理员创建的账号。 [专用 QQ 邮箱配置与三封测试方案](AUTH.md#邮件)

## 4. 实际运行界面和好友共享

延续阶段 7.3 标本册。1 张贴纸占整行，2 张并排，5 张采用 2+3，保留原始比例、轻微稳定旋转和可换行名称。手机拍照按钮维持主要触控位置，一次点击进入取景。确认页保留贴纸优先，信息表单先输入食物名称，再集中填写日期、时间和餐次，营养信息折叠。

- 手账手机视口截图　[一张](screenshots/phase-7.4/phase74-diary-1.png) · [两张](screenshots/phase-7.4/phase74-diary-2.png) · [五张和长名称](screenshots/phase-7.4/phase74-diary-5.png) · [空页](screenshots/phase-7.4/phase74-diary-empty.png)
- 本地浏览器链路截图　[取景](screenshots/phase-7.4/01-preview.png) · [真实主体轮廓](screenshots/phase-7.4/04-real-outline.png) · [白边贴纸](screenshots/phase-7.4/05-final-sticker.png) · [确认页](screenshots/phase-7.4/08-sticker-confirmation.png) · [贴纸入账](screenshots/phase-7.4/06-sticker-landing.png)
- 同一台电脑的独立浏览器会话实际运行三账号测试。好友可见授权的新贴纸及双人手账，撤销后旧媒体地址失效，第三账号访问被拒绝。断网返回后重新校验共享。阶段 7.2 的旧真实 ONNX 共享套件单独执行通过。 [好友手账](screenshots/phase-7.4/06-friend-diary.png)

截图使用测试样例和虚拟摄像头。抠图为真实本地 CPU ONNX，两个浏览器场景从快门到贴纸就绪分别为 3.243 秒和 2.937 秒。云端性能、真实手机摄像头、设备间同步时延和手机录屏待上线后采集。

## 5. 生产发布和验证

| 项目 | 实测或配置 |
| --- | --- |
| 实现及发布完整 SHA | `0b53fa2b232a022b81f6bf64bd685a67981b00b2` |
| 本地发布路径 | `D:/DevEnv/fooddiary-phase74/releases/0b53fa2b232a022b81f6bf64bd685a67981b00b2` |
| 发布清单 | `REVISION` 和 `SHA256SUMS` 校验 150 个文件，含校验清单共 2,452,927 字节。候选包不含实际环境文件、私钥、邮件副本、测试数据库及 ONNX 权重。 |
| 安全初始配置 | 关闭公开注册、邮箱和真实 AI，禁止 Fake Provider。真实累计额度维持 0，复用历史账本。贴纸依审核的私人内测权重授权按需启用。 |
| 后端 | 最终代码全量 243 项通过，77.67 秒。原有 235 项仍保留。保留既有 Starlette TestClient 的 httpx 弃用提示。 |
| 浏览器 | 14 项认证、AI 禁用和手账 API 回归，8 项相机及 1/2/5 张贴纸布局，2 项真实 ONNX 好友共享旧用例，1 项个人 AI 模拟、邮箱及 ONNX 组合回归，均通过。Vue TypeScript 与 API 生产构建通过。 |
| Linux | 在 D 盘 WSL 使用 Python 3.13.18、SQLite 3.54.1、Nginx 1.24.0、41 个已有 wheel。实际离线安装 API 及贴纸两套环境，依赖检查和 ONNX Runtime 1.26.0 CPU Provider 通过。模板加载、最小读写权限、systemd 非 root API 启动、健康检查识别 SHA、Alembic `0011_personal_identity` 迁移及模型一致性通过。私网与公网 Nginx 模板在回环 TLS 下通过，发布流程通过回滚及中断恢复演练。 |
| 本地备份恢复 | 对候选包初始化的 SQLite 做实际备份、独立目录恢复和外键校验，原生演练数据库含 0 个媒体文件。测试夹具另验证旧会话、好友授权、邀请码和验证码失效，临时 AI 凭据不进入恢复，历史用量保留。 |

针对性回归包含 `test_invite_is_checked_before_sending_without_spending_and_registration_is_atomic`、`test_security_mutations_invalidate_prior_email_and_account_challenges`（3 种操作）、`test_email_binding_challenge_is_bound_to_its_session_and_revocation_during_password_check_wins`、`test_account_delete_cancels_queued_work_and_prevents_late_publishing`、`test_restore_expires_saved_email_challenges_and_invitation`、`test_smtp_port_is_read_from_environment_and_requires_secure_transport`。原有邮件失败用例补充注册码无法消费及邀请码未核销的断言。

## 6. 旧业务备份与实际服务器

五个密文分卷均仍在已批准的 D 盘私有目录，合计 **1,714,943,556 字节**，`sha256sum -c SHA256SUMS` 全部通过。既有隔离恢复验证记录仍在，阶段 7.4 用原 Windows 账户经 DPAPI 实际解密并检查宿主机恢复分卷，未创建新的完整副本。DPAPI 依赖当前 Windows 用户和设备；跨设备恢复需要由用户安全保管的独立恢复材料。

通过严格 SSH 主机校验只读核查。华为云 Flexus L 上海一，规格为 2 核、2 GiB 内存、40 GiB 系统盘和 2 Mbit/s 带宽。实查 Debian 11.1、内核 `5.10.0-34-amd64`，`base-files` 仍被 hold。七个旧业务容器均退出，宿主 MariaDB 为 inactive 且开机启用。检查应用目录、业务目录、宿主数据库及配置、TLS 目录和 Docker 数据库卷的文件及符号链接修改和元数据时间，未发现晚于原备份起点的变更。该检查覆盖指定范围和文件时间，未对在线源重新计算逐文件哈希。公网 80/443 无应用监听，`/opt/fooddiary` 尚无实际部署。

本轮云服务器仅只读和 SMTP TLS 连通验证。此前的系统维护授权已暂停。等待重新批准 Debian 11 → 12 → 13 及必要重启、给定北京时间维护窗口，并确认此前实测的 VNC 救援入口仍可用。维护时逐级验证 SSH、VNC、运行内核、旧 MariaDB 与 Docker 数据及停运状态，先处理 `base-files` hold 和旧服务开机启用风险。默认选择可信私网 HTTPS，真实入口与内测账号待授权后部署。 [备份与恢复](BACKUP-RESTORE.md) · [内测入口与部署](DEPLOYMENT.md)

## 7. 资源、费用及交付范围

| 尚待线上验收 | 当前状态 |
| --- | --- |
| HTTPS、手机拍照与录屏 | 未部署，暂无实际地址。待 Android Chrome 和 iPhone Safari 用后置摄像头验收。 |
| 云上好友共享 | 待跨真实设备验证保存与撤销。本地独立浏览器已完成逻辑和真实媒体验证。 |
| 云上性能 | 待采样 CPU、各进程 RSS 与峰值、Swap、API P95、拍照至贴纸分段耗时和磁盘增长。 |
| 生产自动备份 | 待实际启用定时器并验证一次可恢复的云端数据。本地验证记录见发布测试。 |
| 费用 | 真实收费 AI 调用 0 次，真实邮件 0 封，新增付费 0 元。 |

| 本机磁盘 | 开始可用（字节） | 结束可用（字节） | 可用空间变化 |
| --- | ---: | ---: | ---: |
| C 盘 | 31,814,676,480 | 31,875,866,624 | +58.4 MiB |
| D 盘 | 304,217,956,352 | 303,995,441,152 | −212.2 MiB |

上表为整卷快照，包含系统和其他进程的同时变动。本轮复用 D 盘依赖、模型和浏览器缓存。Ubuntu 的 `D:/WSL/Ubuntu/ext4.vhdx` 文件仍为 43,994,054,656 字节（40.97 GiB），未执行压缩。已结束本阶段临时 API、Worker 和 Vite 监听。

工作分支为 `feature/phase-7.4-production-finalization`，起点 `270a552144732d41cfef142500097d0d13dc5e22`。以上完整 SHA 对应可运行发布包，本报告与截图通过后续文档提交交付，分支顶端 SHA 由 GitHub 和最终交付记录给出。阶段 7.4 的线上验收仍待完成，阶段 8 等待审核。
