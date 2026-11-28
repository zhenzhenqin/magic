# FoodDiary 阶段 7.2 发布验证与 Web 内测状态

本报告保留阶段 7.2 部署整改证据，并追加应用内拍摄任务。当前审核基准为 `eac87463446db37398764844e817011cc7d7f907`。目标机真实部署和手机内测尚未完成。

## 1. 宿主机实际状态

2026 年 11 月 28 日以现有 SSH 密钥及严格主机校验访问目标机。结果如下。

| 项目 | 实际结果 |
| --- | --- |
| 系统 | `hcss-ecs-d2f4`，Debian 11，内核 `5.10.0-34-amd64`，systemd 247，Python 3.9.2 |
| CPU | 阶段 7.1 实测 2 vCPU。本轮尚无 FoodDiary 带载采样 |
| 内存 | 1.9 GiB 内存，采样时 1.5 GiB 可用。2 GiB Swap，使用量 0 |
| 磁盘 | 单块 40 GiB `/dev/vda`，根分区是 ext4，约 26 GiB 可用。业务与 Docker 数据同盘 |
| 入口 | 80、443、18080 无监听。常规 PATH 中没有 Nginx 和 Certbot |
| 安全支持 | Debian 11 官方 LTS 已结束。现有软件源未发现可核实的扩展支持渠道，云厂商扩展安全覆盖未验证 |
| 云控制台 | 实际地域、镜像清单、安全组、EIP 类型、控制台恢复入口、云整机备份均未验证 |

[Debian 维护公告](https://www.debian.org/News/2026/20260831)

## 2. 服务器变更与授权

本轮只读检查系统、磁盘、进程、程序版本、容器、镜像、卷、服务、定时器和配置目录信息。尚未进行宿主机升级、重装、整机重启、原有服务变更、项目部署及公网端口开放。

### 宿主机路径对照

| 路径 | 执行条件、影响与恢复 |
| --- | --- |
| A. 保留旧业务并逐级升级 | 推荐优先评估。核对系统盘的独立恢复副本、控制台救援入口和授权维护窗口。先 Debian 11 → 12，再按 Debian 13 指南从受支持的 Debian 12 版本升级。每段复查 SSH、磁盘、Docker、MariaDB、旧项目和第三方软件源。风险是中断及第三方软件包兼容，需每段设置可恢复点 |
| B. 备份后使用 Debian 13 镜像重装 | 由用户先确认旧业务可迁移或清除，并核实所选地域镜像。单系统盘意味着旧数据库、Docker 卷、证书、任务与配置都需先迁出并演练恢复。重装里程碑前需明确授权，换主机密钥时用云控制台查验新指纹 |

华为云支持公共镜像、云服务器备份与整机镜像机制。当前实例是否已有可复用备份及相关价格尚无经授权的控制台证据。继续沿用安全 SSH 密钥，旧管理密码应经安全渠道轮换。 [Debian 升级指南](https://www.debian.org/releases/trixie/release-notes/upgrading.en.html) · [华为云镜像说明](https://support.huaweicloud.com/usermanual-ecs/ecs_03_0201.html)

## 3. 既有业务

Exam Guardian 的 7 个容器均处于退出状态，4 个镜像与持久卷仍存在。宿主机 MariaDB 处于非活动状态，数据目录约 114 MiB。Exam Guardian 的应用目录、业务数据目录、证书文件目录和续签定时器仍存在，续签单元处于失败状态。业务状态和配置以只读检查结果为准。系统的 `/var/backups` 只有少量系统包管理备份，本轮未发现旧业务可验证的异盘恢复点。

## 4. 发布版本与整改

- 发布包绑定 Git SHA，包含 `REVISION` 与覆盖代码、模板和前端静态资源的 `SHA256SUMS`。发布与准备均校验清单。已准备的运行时虚拟环境和共享的配置链接不属于静态发布清单。
- 实际跨系统试装发现，Windows 按路径排序生成的清单顺序与 Linux 不同，即使所有文件哈希一致也会拒绝安装。已改为按统一的 POSIX 相对路径字符串排序，并重新构建发布包。
- 虚拟环境安装过程使用明确的公开读取权限，发布树最终由 root 持有。准备脚本分别核对服务账号执行权限及 Nginx 读取静态文件的能力，同时验证服务账号对发布树的写入限制和 Nginx 对私有配置的读取限制。
- 本机健康检查核对 systemd 的主 PID、回环监听、HTTP 200 及 API 返回的精确发布 SHA。停写前验证实际 HTTPS 虚拟站点的维护响应。
- 回滚前停止并检查三个 FoodDiary 写入单元。故障数据库与 WAL 等附带文件进入隔离目录。恢复原数据库、版本和服务之后校验旧 API 与必要 Worker。首次失败继续保持维护。进程硬中断可持久化追踪和恢复，已确认提交的状态不会倒退覆盖后续写入。 [发布与恢复操作](OPERATIONS.md)

真实服务器发布 SHA 尚无。D 盘实际候选包由实现提交构建，见交付一节。

## 5. 可信 HTTPS

服务器尚无 FoodDiary 的可信 HTTPS 地址。若用户已有合规域名，优先核验 DNS、证书与 ECS 安全组。若使用公网 IPv4，官方支持六天短期证书。Certbot 的 IP 参数自 5.3 提供，Webroot 方式需 5.4 或以上。当前官方公开版本核验为 5.10.0，目标机未找到 Certbot。需核实稳定公网 IP、80 的 ACME 可达性、证书续签和通过配置检测后的 Nginx 重载。现有旧项目证书需独立保留。中国大陆节点还需按接入商规则核查备案及接入，IP 方式同样适用。可用的私网、可信证书和设备接入均需确认。 [IP 证书说明](https://letsencrypt.org/2026/03/11/shorter-certs-certbot) · [Certbot 5.10.0](https://github.com/certbot/certbot/releases/tag/v5.10.0) · [华为云备案说明](https://support.huaweicloud.com/icp_faq/icp_05_0145.html)

## 6. 登录与跨设备同步

真实手机、真实服务器、内测账号创建、同步及上传待验收。生产保持关闭自助注册，首批账号由管理员使用安全交互入口创建。真实生产库从空库开始。

## 7. 好友共享与撤销

本地浏览器继续覆盖三账号隔离、单向授权、撤销、双人手账和网络恢复。目标站点上的跨日确认、旧 URL 失效和第三账号隔离待后续验证。截图仅在实际部署后提交脱敏证据。

## 8. 贴纸与 AI

生产初始关闭贴纸与外部 AI。rembg 项目明确说明权重与软件适用独立许可。现有 ONNX 发布资产的部署许可尚未确认，保留本地测试权重，发布包排除权重。若取得授权，目标机以单线程、并发 1、768 px、512 MiB 内存上限和 CPUQuota 100% 验证，必要时以 512 px 复测。两家真实供应商累计上限均为 0。 [rembg 权重许可说明](https://github.com/danielgatis/rembg#models)

## 9. 实际资源与性能

目前的真实服务器数据为只读空载状态。服务器 API P95、并发上传、SQLite 读写、CPU 贴纸冷启动和内存峰值均待实测。当前磁盘可用约 26 GiB，按 7.1 平均值估算，两人三年数据及三份完整本地恢复点约 20.77 GiB。按观测最大样本约 24.91 GiB，加入 2 GiB 备份余量和媒体保留空间后超过当前可用量。实际留存策略需要随数据增长复查，配额继续采用原配置。

## 10. 自动备份与恢复

提供每日低峰期 systemd timer，以及验证新恢复点后仅保留三个日备份的策略。发布备份另行保留。Linux 候选包和本机备份恢复证据见回归一节。服务器真实停写耗时、恢复验证、timer 实际运行以及加密离机备份目的地待授权确认。恢复副本保留费用账本与好友关系，旧会话和共享授权关闭，活跃 AI 任务取消。 [备份恢复说明](BACKUP-RESTORE.md)

## 11. 重启与持久化

真实服务器上 FoodDiary 服务启动、重启、开机启动、保留数据、Worker 恢复及证书自动续签均待验收。隔离 Linux 演练与云主机运行证据分开记录。

## 12. 回归与发布包证据

| 环境 | 实际结果 |
| --- | --- |
| Windows 后端 | `pytest -q` 218 项全部通过。包括精确发布版本响应和保留三个有效日备份的新测试。保留一条既有 Starlette `TestClient` 弃用提示 |
| Windows 浏览器 | Playwright 47 项通过。Demo 12、真实 API 14、贴纸 2、假贴纸 Provider 共享 2、本地 CPU ONNX 共享 2、AI 9、AI 恢复 5、Worker 离线 1。AI 用例使用本地模拟 |
| Windows 构建和数据库 | TypeScript、API 和 Demo 生产构建通过。对独立 SQLite 数据库执行 `alembic upgrade head` 和 `alembic check`，无模型差异 |
| WSL Bash 和 Nginx | Bash 语法检查、发布故障演练和真实 Nginx 1.24.0 检查通过。覆盖首次发布失败重试、新版迁移失败、启动后错误 SHA、Worker 启动失败时先停写再回滚、旧版恢复失败保留维护、强制中断后的恢复，以及 HTTPS、维护 503、上传体积和转发头验证 |
| WSL 原生安装和服务 | Linux x86_64 CPython 3.13.18、glibc 2.39、SQLite 3.54.1、systemd 255。候选包离线安装并通过 `pip check`。非 root 临时服务在 systemd 下启动，校验回环监听、主 PID 和准确 SHA，并拒绝错误 SHA。`systemd-analyze verify` 返回成功，提示演练使用了特殊账号 `nobody`。生产模板使用独立账号 `fooddiary`。空库完整备份、独立目录恢复及 SQLite 完整性核验通过 |
| 交付文件审查 | 逐项校验发布清单。检查阶段差异与发布文件类型、常见令牌和私钥模式，未发现受限文件或匹配内容。wheelhouse 含基础及贴纸可选依赖的 41 份 Linux 二进制包，贴纸模型未打包 |

本地 ONNX 使用已有测试权重。当前仅有本地浏览器与 WSL 证据，目标服务器及实际手机运行截图待部署生成。

## 13. C 与 D 盘

| 磁盘 | 开工可用字节 | 验证结束可用字节 | 可用空间变化 |
| --- | ---: | ---: | ---: |
| C | 30,298,091,520 | 30,142,918,656 | 减少 148.0 MiB |
| D | 337,306,669,056 | 335,185,498,112 | 减少约 1.98 GiB |

以上为整盘采样差值。发布、wheelhouse、便携 Linux Python、日志和数据库在 D 盘或 D 盘的既有 WSL 虚拟磁盘中。

## 14. 真实收费 AI

本阶段真实收费 AI 调用 **0 次**。只读核对阶段 7.2 浏览器联调库，AI 调用记录为 0。阶段 4.2 独立联调库仍保留原有 1 条历史调用记录。

## 15. 尚未解决的生产条件

需确认宿主机方案及维护窗口、旧业务独立备份及救援入口、ECS 地域、可信 HTTPS 入口和明确的服务器变更授权。贴纸正式处理另需确认权重部署许可及低配机资源。真实收费 AI 保持关闭。

## 16. Git 交付

分支 `feature/phase-7-deployment`。部署整改提交 `93c8e0469e097e047b44f6579f559f740eabeba8`。跨平台清单修复后重新打包的候选版本为 `1f12e9b64d6f7dd6535d648acd1cdcdb418ba2e8`，发布包内 `REVISION` 与此 SHA 一致，共校验 132 个文件。当前没有真实服务器运行版本。 [GitHub 分支](https://github.com/zhenzhenqin/magic/tree/feature/phase-7-deployment)

## 17. 内测验收结论

服务器现状已复查。当前交付处于部署准备及验证范围，尚未达到真实 Web 内测验收条件。

## 18. 摄像头追加任务与实际授权

用户补充确认实例为华为云 Flexus 应用服务器 L，上海一 `cn-east-3`，2 核、2 GiB、40 GiB 系统盘、2 Mbit/s 峰值和 100 GB 流量包。系统实测仍以此前 Debian 11、Python 3.9.2 和 26 GiB 可用的只读记录为准，没有重复登录盘点。本轮没有安装软件、改端口、重启主机或覆盖旧业务。Exam Guardian 应在空间允许时保留停运，本轮没有迁出旧业务，异盘恢复和 VNC 救援权限仍待确认。

已获条件授权，在宿主机满足安全要求后安装免费依赖、Nginx、Certbot、Python，部署 FoodDiary、配置证书及 systemd 备份。若满足公网接入要求，可开放 TCP 80 和 443，继续保留 SSH 22。用户明确将系统升级、重装、整机重启和旧项目删除留待单独授权。

用户当前没有域名。Let's Encrypt 免费 IP 证书只满足 TLS 信任，华为云大陆网站仍需先完成适用备案及接入核验。`https://113.44.64.113` 是拟用地址，当前未部署。初期可在安全宿主机上核验只允许内测成员访问的可信私网 HTTPS。未确认符合华为云接入要求之前，公网 80 与 443 不启用。 [华为云备案条件](https://support.huaweicloud.com/icp_faq/icp_05_0145.html) · [华为云控制台 VNC](https://support.huaweicloud.com/usermanual-flexusl/server_login_0002.html) · [IP 证书](https://letsencrypt.org/2026/03/11/shorter-certs-certbot)

## 19. 拍照闭环、测试平台和性能

Web 使用真实 MediaDevices API。快门将当前帧 Canvas 编码为单张图片，上传到现有私有媒体接口并自动提交贴纸。抠图就绪后使用真实透明产物和白边贴纸播放转场，餐次成功保存后按实际目标位置播放入账。支持补光能力检查、镜头切换、后台释放、相册降级、保留原图、手动填写和减少动态效果。AI 保持关闭，第三方识别仍须按按钮并确认。阶段 8 的 CameraProvider、系统相机与自定义取景适配范围已记录。 [实现和 Android 计划](CAMERA.md)

| 验证 | 实际结果 |
| --- | --- |
| Windows Chrome 390×844 | 7 项专项用例通过。真实 Web API、文件驱动的虚拟摄像头、真实本机 ONNX Worker。覆盖轨道释放、权限拒绝、无设备、相册、自动提交、Alpha、在途保存、相机切换、重拍、断网恢复、跳过动画、账号隔离、保存失败与重复点击 |
| 好友 | 两个独立本地浏览器会话通过。授权好友在正式保存前看不到草稿，保存后读到新贴纸，撤销后同一媒体地址返回 404。后端测试还覆盖显式原图选择与贴纸和原图权限分离 |
| 浏览器用时 | 一次 640×480 虚拟拍摄影像测得取景 0.911 秒、快门到上传响应 0.648 秒、快门到贴纸下载响应 10.264 秒，JPEG 90,041 字节。在同机并行运行其他回归时采样，包含 Worker 排队及轮询等待，未达到 5 秒端到端参考目标 |
| WSL Linux 实际 ONNX | 现有权重，Python 3.13.18、ONNX Runtime CPU 单线程。会话冷加载 0.513 秒，三张无隐私样例各跑三次。768 px 推理与两种 WebP 编码合计 1.074–2.358 秒，512 px 为 0.869–2.696 秒，全程峰值 RSS 365.1 MiB。两个 768 px 派生图共约 251–701 KiB |
| 后端 | 219 项 pytest 通过，1 条已知 Starlette 测试客户端弃用提示。Alembic 新迁移及 `alembic check` 通过，旧幂等键和原有数据回归通过 |
| 原有浏览器回归 | 47 项通过，分别为 Demo 12、API 14、贴纸 2、本地模拟 Worker 共享 2、真实本机 ONNX 共享 2、AI 9、AI 恢复 5、AI Worker 离线 1。加上拍照专项合计 54 项 |
| 构建及 WSL 发布回归 | TypeScript、API 与 Demo 生产构建通过。Bash、Nginx 可信测试证书与相机安全响应头、发布回滚、强制中断恢复通过。新的发布包在 WSL 完成真实 Linux 离线安装、非 root systemd 启动、原子版本核验和空库隔离恢复 |
| 真实设备及生产 | Android Chrome、iPhone Safari、手机实际摄像头及补光、2 Mbit/s 云机延迟、并发和备份定时触发、隔离恢复均待目标机及真机复测 |

Windows 与 WSL 指标反映本机负载。云服务器实际 CPU、内存、Swap、磁盘持续增长、API P95、SQLite 并发、重启持久化和带负载抠图尚未实测。阶段 7.2 真实收费 AI 累计 0 次，费用 0 元。

## 20. 模型证据和启用条件

本地 `u2netp.onnx` 为 4,574,861 字节，SHA-256 `309c8469258dda742793dce0ebea8e6dd393174f89934733ecc8b14c76f4ddd8`，文件名和体积与 rembg `v0.0.0` 发布记录一致。U²-Net 作者说明公开发布的代码和模型同一许可，仓库采用 Apache-2.0，同时确认 u2netp 使用 DUTS 并提示应用方核查数据集许可。DUTS 官方页未发现明确商业许可，精确 rembg ONNX 资产的独立生产说明未确认。继续保留本地评估，权重未打包，云端未开启。备用候选 withoutBG 提供公开 ONNX 条款，结合 DINOv3 条款且需进一步测量低配 CPU 和内存，本轮未切换。 [上游模型许可说明](https://github.com/xuebinqin/U-2-Net/issues/208) · [DUTS](https://saliencydetection.net/duts/) · [rembg 权重来源](https://github.com/danielgatis/rembg/releases/tag/v0.0.0) · [withoutBG 许可](https://withoutbg.com/open-model/license)

## 21. 实际截图和录屏

截图与视频均来自当前应用的本地运行，测试用合成餐桌示例和独立测试账号。真实 CPU ONNX 生成派生文件。摄像头视频输入为已有授权样例制作的 Y4M，尚无真机录屏。D 盘原始记录位于 `D:/DevEnv/fooddiary-phase72-camera/evidence/`。已核验三个 WebM，时长分别为 13.92、22.44 和 21.80 秒。

| 实际证据 | 文件 |
| --- | --- |
| 实时取景与快门 | [取景](screenshots/phase-7.2-camera/01-preview.png) · [拍摄](screenshots/phase-7.2-camera/02-captured.png) |
| 真实贴纸动画 | [等待扫描](screenshots/phase-7.2-camera/03-extracting.png) · [轮廓与背景变淡](screenshots/phase-7.2-camera/04-real-outline.png) · [白边成品](screenshots/phase-7.2-camera/05-final-sticker.png) · [A 录屏](screenshots/phase-7.2-camera/A-capture-to-real-sticker.webm) |
| 成功保存及贴纸入账 | [入账动画](screenshots/phase-7.2-camera/06-sticker-landing.png) · [B 录屏](screenshots/phase-7.2-camera/B-save-and-place.webm) |
| 权限拒绝与相册降级 | [权限拒绝](screenshots/phase-7.2-camera/07-permission-denied.png) · [C 录屏](screenshots/phase-7.2-camera/C-permission-fallback.webm) |
| 好友查看新贴纸 | [授权好友手账](screenshots/phase-7.2-camera/08-friend-real-sticker.png) |

## 22. 当前候选包与验收结论

摄像头实现提交为 `2237cf5b1440fa4a826e82223070550614e70f4a`。D 盘候选包 `D:/DevEnv/fooddiary-phase72-camera/releases/2237cf5b1440fa4a826e82223070550614e70f4a`，核验 133 个清单条目。证据及汇报另成提交，以远端分支顶端为准。报告中的候选 SHA 尚无实际目标机运行记录。 [GitHub 原分支](https://github.com/zhenzhenqin/magic/tree/feature/phase-7-deployment)

追加任务的整盘采样如下。测试浏览器缓存、截图、录屏、数据库、发布包和 WSL 虚拟磁盘均使用 D 盘，系统本身的其他活动也会影响整盘数据。

| 磁盘 | 开工可用字节 | 结束可用字节 | 可用空间变化 |
| --- | ---: | ---: | ---: |
| C | 30,074,646,528 | 29,966,262,272 | 减少 103.4 MiB |
| D | 336,172,769,280 | 330,732,961,792 | 减少约 5.07 GiB |

应用内拍照和贴纸动画具备本地证据。阶段 7.2 完整验收仍需经批准的宿主机维护与旧业务恢复验证、可信 HTTPS 部署、手机摄像头、跨真实设备同步和生产资源及恢复数据。未部署前不进入阶段 8。
