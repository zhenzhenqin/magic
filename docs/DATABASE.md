# FoodDiary 数据库

`0008_friend_sharing` 在阶段 5 后新增五张表。原有饮食、图片、识别账本和图鉴保留原表结构及已有行。

| 表 | 约束与用途 |
| --- | --- |
| `friend_requests` | 用户顺序归一，每对仅一条当前或最近申请。收件、发件及过期查询有索引 |
| `friendships` | 每个规范化用户对只有一个有效关系。解除后旧关系 ID 随记录删除 |
| `share_permissions` | 主键为关系 ID 与所有者，包含查看者、权限位、固定边界、授予时间和修改版本。删除好友关系会级联撤销两条方向的授权 |
| `share_audit` | 保存操作者、相关账号、时间和事件。写入时删除 90 天前的记录，并限制当事人最近 100 条。账号删除会级联清理 |
| `media_write_reservations` | 原照片和贴纸写入暂存空间共用的短期预留。保存字节数及带索引的到期时间 |

授权、申请及解除在 SQLite 短写事务中处理。已有用餐归属和日期索引用于共享范围，SQLite 确定函数提供共享图鉴名称分组及稳定的分组标识。 [权限与历史](SHARING.md)

阶段 5 的 `0007_stickers_catalog` 增加 `sticker_jobs`、`sticker_runtime`、`media_derivatives`、`food_catalog`、`catalog_names` 与 `catalog_links`。迁移用原有 `meal_items` 回填图鉴，保留现有明细 ID 和识别来源。用户与媒体使用复合外键，派生文件及任务随原图行删除。 [图鉴数据规则](CATALOG.md)

开发使用 SQLite 和同步 SQLAlchemy 2.x。默认 `DATABASE_URL=sqlite:///data/fooddiary.db` 的相对路径从 `backend/` 解析，实际开发文件为 `D:/桌面/mjc/fooddiary/backend/data/fooddiary.db`。每个 SQLite 连接启用外键约束，文件库使用 WAL，忙等待上限 5 秒。

| 表 | 主键、约束与字段 |
| --- | --- |
| `users` | 内部 UUID `id` 主键，`public_id`、规范化的 `username` 数据库唯一。另含 `password_hash`、`nickname`、可空 `avatar_key`、`is_active` 和创建、更新时间 |
| `user_settings` | `user_id` 主键兼外键，删除用户时级联删除。含 `timezone`、`show_calories`、`show_nutrition` 和创建、更新时间 |
| `auth_sessions` | UUID `id` 主键，`user_id` 外键并有索引。含唯一 `refresh_token_hash`、有索引的 `previous_token_hash`、`created_at`、有索引的 `expires_at`、`last_used_at`、可空 `revoked_at` |
| `alembic_version` | Alembic 的迁移版本表 |

用户和默认设置在同一事务创建。公开 ID 由服务器随机生成。默认时区 `Asia/Shanghai`，两个展示项均开启。数据库字段保存 UTC 值，读取恢复 UTC 时区，接口序列化为带时区的时间。用户时区用于后续界面展示转换，数据库时间基准始终为 UTC。会话的 `last_used_at` 记录登录和最近一次成功刷新。

在项目根目录执行迁移和核对。

```powershell
.\scripts\setup-backend.ps1 -Action Migrate
.\scripts\setup-backend.ps1 -Action CheckSchema
```

空库和阶段 2 现有库均可迁至 `0002_meal_diary`，迁移可重跑。独立升级测试验证原有用户、设置与会话仍可使用。后端与浏览器测试在 D 盘创建独立 SQLite 和媒体目录，拒绝把仓库内路径作为测试库。

## 阶段 3 饮食表

| 表 | 字段及约束要点 |
| --- | --- |
| `meals` | UUID、owner、餐次、UTC 用餐时间、本地日期和时区、备注、版本、审计时间。索引覆盖 owner、日期、用餐时间和 ID。同日同餐次允许多条 |
| `meal_items` | 主记录外键、稳定排序、名称、分类、重量和四项营养、备注、来源及审计时间。同餐排序唯一。餐次删除级联明细 |
| `media_assets` | owner、原图及缩略图唯一存储键、MIME、尺寸、文件大小、SHA-256、草稿或关联状态及时间。状态和更新时间用于清理 |
| `meal_media` | 记录与图片联合主键，同餐排序唯一。包含 owner，双方复合外键校验同一所有者并索引图片引用 |
| `meal_requests` | owner 与幂等键联合主键，存请求指纹及所创建记录。记录删除后保留请求标识，防止旧重试重新建立 |

输入为用户确认的本地日期、当地钟表时间与 IANA 时区，服务端转换为 UTC。夏令时不存在的时间被拒绝，重复时刻选该钟表时间的第一次出现。修改默认时区不回算既有记录本地日期。创建时间和用餐时间相互独立。

营养与重量可为 null，已知量支持两位小数。日报分别返回有限值合计、填写数量和是否完整。任何项目均未知时，该项合计为 null。

MySQL 8.4 保留为后续生产候选。现有宿主机数据库未用于本阶段，MySQL 驱动、迁移、事务与并发兼容性未验证。数据库文件、WAL、日志、签名密钥和虚拟环境不提交。


## 阶段 4 增量迁移

`0003_ai_recognition` 在 `0002_meal_diary` 上增量升级。已有用户、会话、设置、餐次、明细 ID、媒体文件和旧请求指纹保留。旧明细仍为 `manual`，新来源字段为空。迁移和模型核对仍用上面的命令。

| 表或字段 | 主要约束和用途 |
| --- | --- |
| `ai_jobs` | 行为为食物识别。状态检查、账号和创建幂等键唯一、提示词和授权版本、调度时间、尝试上限、领取标识和租约、结构化结果、已采用此任务的餐次 ID。队列、账号状态和完成时间加索引 |
| `ai_job_media` | 任务与图片联合主键，顺序唯一。复合外键分别绑定任务和媒体的所有者 |
| `ai_usage_logs` | 每个领取标识一行。记录归属、供应商、模型、发送状态、Token、已知标记、上游请求 ID 和时间。删除任务后保留用量，并置空外键 |
| `ai_retry_requests` | 账号、任务、重试键联合主键。保留所有尚在任务期内的重试指纹 |
| `meal_items.ai_*` | 任务、候选、Provider、模型、提示词版本和原估算摘要。来源字段保持独立，可在任务结果清除后继续核对后续编辑 |

编辑先核对餐次版本与已提交明细 ID，再用短事务释放旧排序位置并写入新顺序。同餐次内沿用已有 ID。阶段 3 客户端缺少 ID 时尽量按原值精确匹配。旧餐次删除和创建幂等行为照常有效。[任务保留和额度](AI.md)

## Phase 4.1 增量迁移

`0004_ai_recovery` 为任务加入有序照片快照与编辑餐次关联。老任务使用原有指纹校验完整关联，历史结果保持可查询。用量表新增耗时及安全错误码，删除账号后解除用户外键关联，保留计费记录至原保留期。已有使用记录的任务与账号关系随升级保存。

`ai_call_budgets` 保存按 Provider 的累计发送量。迁移将旧库仍保有的 Qwen 已发送和未知尝试计入。额度递增及尝试从预留到发送的转换同事务完成，确认未发送才退回。累计值独立于用量明细保留时长。`ai_worker_heartbeats` 按 Provider、模型与地址的配置摘要保存最近心跳，用于判断相同配置的 Worker 是否在线。
