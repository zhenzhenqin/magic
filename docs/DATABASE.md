# FoodDiary 阶段 2 数据库

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

空库迁至 `0001_identity`，迁移可重跑，模型对比无待应用变化。后端与浏览器测试各自在 D 盘临时目录创建独立 SQLite 文件，通过 Alembic 初始化，并使用明确的测试配置。测试不读开发 `.env`，拒绝把仓库内路径当作测试库。

MySQL 8.4 保留为后续生产候选。现有宿主机数据库未用于本阶段，MySQL 驱动、迁移、事务与并发兼容性未验证。数据库文件、WAL、日志、签名密钥和虚拟环境不提交。
