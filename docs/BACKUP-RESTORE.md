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

## 旧业务及宿主机维护

Exam Guardian 的离机归档独立于 FoodDiary。用受信任 SSH 把停运应用、配置、Compose、必要镜像和卷、MariaDB 数据、证书、定时器及 systemd 配置流式移至经批准的 D 盘私有加密目录，逐项核对清单和 SHA-256。隔离核验数据库与 Docker 恢复能力后再安排维护。对单系统盘还需准备云控制台 VNC 或救援入口，并保留足以恢复整机的途径。当前实际归档、迁出与恢复均等待维护范围和目的地确认。
