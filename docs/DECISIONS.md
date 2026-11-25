# 技术选型与关键决策

记录日期为 2026-11-25。阶段 0 采用可审查的兼容版本线。具体补丁版本和依赖锁文件由对应实施阶段通过构建或安装验证后确定。

| 决策 | 初步选择 | 依据及验证时点 |
| --- | --- | --- |
| Web 与包管理 | Vue 3、TypeScript、Vite 8、Tailwind CSS、原创组件。优先使用 pnpm，统计阶段使用 ECharts | 现有 Node.js 22.19.0 达到 Vite 8 的 Node 22 门槛。本机 pnpm 可运行。阶段 1 验证安装、开发启动和生产构建 |
| Android | Capacitor 8 候选，保留现有 JDK 21.0.9 | 当前 Node.js 满足 Capacitor 8 要求。阶段 9 核验实际 Android Studio、SDK 36、Build Tools、Gradle 与 Android Gradle Plugin 组合 |
| 后端 | Python 3.13 候选，FastAPI、SQLAlchemy 2.x、Alembic | 本机 Python 3.13.9 可用。阶段 2 验证后端依赖和 MySQL 驱动，阶段 5 核验 Linux x86_64 的图像依赖与 ONNX Runtime wheel |
| 数据库 | MySQL 8.4 LTS，项目独立数据库、用户和迁移 | 本机 MySQL 8.0.34 可供开发环境评估。迁移验收使用独立的 8.4 实例。服务器现有 MariaDB 留给既有业务使用 |
| AI 食物识别 | 优先评估外部 Qwen-VL，通过服务端适配调用 | 可把多模态推理放在外部服务。阶段 4 根据质量、费用、延迟和图片处理约束选定具体模型与版本 |
| CPU 抠图 | rembg、ONNX Runtime CPU、Pillow，独立 Worker | 阶段 5 优先测 `u2netp` 与单任务并发，结合质量、峰值 RSS、CPU 和吞吐量决定模型、上线并发及 Worker 部署位置 |
| 图片存储 | 私有本地文件系统，预留对象存储接口 | 起步组件较少。项目需验证访问授权、备份恢复和真实图片存储增长 |
| 部署 | Docker Compose + Nginx，结合试运行确定部署位置 | 现有主机 Compose 可用，旧业务停服后 80/443 空闲、可用内存约 1.5 GiB。阶段 8 依据压测、安全支持、入口和运维授权确定部署方案 |

版本依据。[Vite 8 发布说明](https://vite.dev/blog/announcing-vite8) · [Capacitor 8 环境要求](https://capacitorjs.com/docs/getting-started/environment-setup) · [Capacitor 8 Android 迁移指南](https://capacitorjs.com/docs/updating/8-0) · [MySQL LTS 说明](https://dev.mysql.com/doc/refman/8.4/en/mysql-releases.html) · [rembg 依赖与平台配置](https://github.com/danielgatis/rembg/blob/main/pyproject.toml)
