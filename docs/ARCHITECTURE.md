# FoodDiary 初步架构

这份文档供阶段审查。组件边界、应用版本与部署位置在对应阶段结合验证结果确定。

阶段 1 的 Demo 保留原有 Vue 路由、Pinia、Mock Repository 和 IndexedDB 媒体。阶段 2 增加独立 API 入口、真实认证 Pinia Store 与 HTTP Repository。Vite 在启动或构建时只解析所选模式的入口，API 构建只挂载真实账号页面及未开放模块的空状态。

阶段 2 后端由 FastAPI、同步 SQLAlchemy、Alembic 与本地 SQLite 组成。认证依赖从已验证且有效的服务端会话解析账户，个人资料和设置按该账户读写。短期访问令牌留在内存，浏览器通过 HttpOnly Cookie 刷新。[API](API.md) · [数据库](DATABASE.md) · [安全](SECURITY.md)

```text
浏览器 / Capacitor Android
            │ HTTPS
            ▼
公网入口 → FoodDiary Web 静态资源与 API 路由
                          │
                          ▼
                      FastAPI ── SQLAlchemy / Alembic ── MySQL
                         ├── 外部多模态识别 API
                         └── 私有媒体存储 ← 图片处理 Worker
```

## 客户端和 API

- Web 采用 Vue 3、TypeScript、Vite、Tailwind CSS 和原创组件。Android 包装复用 Web 页面与交互，Capacitor 负责相机、相册等原生能力。图表在统计阶段加入 ECharts。
- FastAPI 提供账户、饮食记录、图片授权访问和亲友授权接口。SQLAlchemy 管理数据库访问，Alembic 管理版本化迁移。
- 图片原图、缩略图和贴纸放在私有本地文件系统，数据库保存对象标识与用途。通过统一的媒体访问接口预留对象存储适配。Web 静态目录与私有媒体根目录分开放置。

## 记录、识别与贴纸

用户导入或拍摄图片后，API 校验图片格式、大小与解码尺寸，再保存原图引用。服务端按需调用外部多模态服务，优先评估 Qwen-VL，向用户展示可编辑的识别建议。用户确认后的饮食记录作为手账和统计的数据来源。识别失败时保留手动记录路径。

CPU 抠图由独立 Worker 异步执行。计划用 rembg、ONNX Runtime CPU 和 Pillow 生成带透明通道的贴纸与预览图。Worker 通过持久任务状态支持失败重试，任务和结果标识应支持幂等处理。阶段 5 再确定任务传递方式、模型和资源上限。

## 权限与隐私

记录和媒体默认仅对本人可见。亲友权限按授予人、接收人和允许的数据范围进行服务端校验。双方互看由两条独立授权实现，任一方撤销其授予的权限后，后续查询、媒体读取与统计均执行最新授权规则。对私有图片保持可撤销的访问路径。

模型密钥仅存于服务端。外部识别服务只接收必要的图片数据，去掉无关元数据。阶段 4 评估供应商的数据处理约束、成本、延迟和识别质量。

## 部署边界

- 目标部署用 Docker Compose 管理应用、独立 MySQL 和必要的 Worker，MySQL 仅通过项目私有网络访问。持久化 MySQL 与媒体分别纳入备份及恢复演练。
- 独立主机可由 Nginx 承担公网入口和反向代理。现有主机停服后 80/443 空闲。若旧业务恢复并与 FoodDiary 共机，先确定统一入口与按域名转发的方案。
- 现有主机停服后可用内存约 1.5 GiB，Debian 11 项目的 LTS 已结束。生产部署决策需结合主机的安全覆盖、项目资源压测、图片容量预估以及旧业务是否恢复。部署可行性证据见[环境检查](ENVIRONMENT.md)。
