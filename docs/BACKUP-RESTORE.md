# FoodDiary SQLite 与私有图片备份

## 一致恢复点

生产任务通过 `bash deploy/production/manage.sh backup` 执行。它先设置 Nginx 维护标记并停下三个 FoodDiary 写入进程。SQLite 的立即事务防止意外并发写入，另一个连接使用 SQLite Online Backup API 读取包括已提交 WAL 在内的当前状态。工具按该数据库的引用复制规范化原图、原图缩略图、透明抠图、白边贴纸及贴纸缩略图。未持久化的临时文件和孤立文件由既有清理流程处理。

工具核对 SQLite 完整性与外键，保存数据库和每项媒体的字节数及 SHA-256。检测到缺失、路径异常或摘要不匹配时不发布该恢复点。恢复点以同分区临时目录完成后原子改名，目标必须是新目录。默认检查剩余空间足以存放完整副本并保留 2 GiB。完成或可安全回退后恢复原有 FoodDiary 服务，保留已有备份。

每天安排短维护窗口。授权并完成首次真实备份验证后，可启用项目专用 `fooddiary-backup.timer`，默认宿主机时间 04:30，随机延迟至多五分钟。对应 service 运行 `manage.sh backup --keep-three`。校验本轮最新恢复点后仅轮换具有 FoodDiary 清单的旧日备份，保留最近三个日恢复点。版本发布备份单独管理。通过 timer 状态与 `journalctl -u fooddiary-backup.service` 核对最近成功时间、耗时、空间不足和失败原因。

数据库备份包含用户、认证会话、好友、授权、用餐、识别历史、费用账本与媒体引用。私有配置和当前凭据经独立加密备份，管理权限与业务副本分开。离机备份可把已校验恢复点打包后，以接收方专用 GPG 公钥加密，经受控 SFTP 迁至已授权存储。启用前核对公钥指纹和容量。接收方应在隔离目录解密并复验清单。该流程不依赖新购云存储。

## 隔离恢复

在活动版本的后端目录执行，指定新的恢复目录。保持隔离网络，先核对快照再创建副本。

```bash
.venv/bin/python -m app.maintenance verify /var/backups/fooddiary/<point>
.venv/bin/python -m app.maintenance restore /var/backups/fooddiary/<point> /var/backups/fooddiary/drill-<name>
.venv/bin/python -m app.maintenance check-db /var/backups/fooddiary/drill-<name>/data/fooddiary.db
```

原备份的授权及会话仍保留供盘点。隔离恢复副本注销旧会话、关闭授出的权限并提升修改版本，保留好友关系和账户密码。活跃外部 AI 任务在副本取消，保留历史、未知调用和费用累计。恢复生成的 `ISOLATED.env` 关闭真实 AI、额度、公开注册与贴纸 Worker。需配置独立 JWT 密钥和隔离的浏览器来源，分别核验账号登录、旧餐次、所有媒体、好友关系及重新授权。恢复流程会核对复制过程中是否发生变化。

如需将该副本用于正式恢复，先核对事故发生前后其他来源的最新费用账本、供应商账单以及待决调用，保守补齐后才允许单独申请开启外部识别。管理员还需与数据所有者确认已撤销的权限，按实际需要重新授权，并在上线前检查生产媒体和预期 schema。运行中的数据库与媒体切换必须处于受控停写窗口。

阶段 7.3 的临时凭据只在进程内使用，数据库备份只包含不透明引用。隔离恢复撤销旧会话及共享权限、取消未完成识别、使旧验证码和邀请码失效，并保留用量账本。隔离环境默认关闭 AI 和邮箱。删除账号后，活动副本与授权立即撤销。仍处于保留期的历史数据库和媒体备份由原轮换机制到期处理。

## 旧业务及宿主机维护

Exam Guardian 的离机归档独立于 FoodDiary。用受信任 SSH 把停运应用、配置、Compose、必要镜像和卷、MariaDB 数据、证书、定时器及 systemd 配置流式移至经批准的 D 盘私有加密目录，逐项核对清单和 SHA-256。隔离核验数据库与 Docker 恢复能力后再安排维护。对单系统盘还需准备云控制台 VNC 或救援入口，并保留足以恢复整机的途径。当前实际归档、迁出与恢复均等待维护范围和目的地确认。

### Exam Guardian 迁出清单和恢复点

1. 核对云控制台打开目标实例的 VNC 并能登录系统。授权范围确认后，将 `D:/DevEnv/fooddiary-private-backups/exam-guardian` 作为建议归档目录，设置仅用户与必要恢复人员可读的 ACL。可用接收方已确认的 GPG 公钥，或由用户独立保管对称口令。先用小样验证加密、解密和校验，避免在普通 D 盘目录落明文归档。
2. 保持原有 7 个容器和宿主 MariaDB 停运。源目录包括 `/opt/exam-guardian-lab`、`/var/lib/exam-guardian-lab` 的业务子目录、`/var/lib/mysql`、`/etc/mysql`、`/etc/letsencrypt`、Docker 的 `exam-guardian-lab_db` 卷，以及相关 systemd、定时任务和反代配置。交换文件可在恢复时重新创建。记录安装包及系统版本、APT 源、原服务启用状态、容器配置、镜像标签与镜像 ID。容器检查输出可能包含凭据，直接加入加密归档。
3. 使用经严格主机校验的 SSH 流式归档。文件、MariaDB 物理副本和 Docker 卷保留数字所有者、模式、链接与适用的扩展属性。镜像用 `docker image save` 归档。对每个容器核对 `docker diff`，如有无法从镜像、卷和配置重建的内容，另保留该容器的根文件系统导出。以目录清单与文件摘要核对归档，密文在目标位置计算 SHA-256。传输失败的分卷不登记为恢复点。
4. 还原至隔离、受访问控制的 D 盘工作区，禁止与当前 Docker 卷同名或者启用原业务定时器。用与源相容的 MariaDB 版本，仅本地 Unix socket 启动数据库副本，核对数据库列表、关键表与抽样行数。恢复镜像和卷，在隔离网络中检查 Compose 可解析、应用可读取配置和代表性业务文件，检查证书、私钥与文件权限。记录恢复测试结果、原始发布版本和必要的云控制台恢复路径。维护开始前保留全部原数据和已验证归档。

定向只读统计显示应用目录 610.1 MiB，排除交换文件后业务目录 59.5 MiB，宿主 MariaDB 113.2 MiB，Docker 卷 251.6 MiB，4 个镜像的 API 报告大小合计 746.2 MiB。现存 7 个容器的可写层各约 12–102 kB。基础合计约 1.74 GiB，实际归档大小仍受镜像导出、容器额外文件和压缩影响。保留 24 GiB 本地空间用于密文与隔离恢复足以覆盖目前的保守预算。以 2 Mbit/s 持续传输 1.74 GiB 理论约 2.1 小时，依实际出口波动、压缩和镜像导出结果决定维护开始时间。 [华为云 VNC 操作](https://support.huaweicloud.com/usermanual-flexusl/server_login_0002.html)

原地维护优先按照官方指南分段执行 `bullseye` → `bookworm` → `trixie`。每段先审查第三方软件源与模拟安装结果，再进行最小升级、完整升级和获准重启，逐段确认 VNC、SSH、新运行内核、系统服务、Docker、MariaDB 数据及旧项目停运状态。失败时保留恢复点，按照该段问题从控制台恢复。重装需要云端可用的 Debian 13 镜像，风险集中于单盘内容被覆盖与主机密钥更换，只有独立备份恢复通过并另有授权时才采用。 [Debian 12 升级](https://www.debian.org/releases/bookworm/amd64/release-notes/ch-upgrading.en.html) · [Debian 13 升级](https://www.debian.org/releases/trixie/release-notes/upgrading.en.html)
