# FoodDiary 数据库

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
