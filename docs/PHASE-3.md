# FoodDiary 阶段 3 汇报

## 一、阶段完成情况

已交付真实账号下的个人手账闭环，包括手动录入、相册选择、浏览器拍摄入口、多食物、多照片、服务端保存、手账、月历、详情、编辑与删除。个人设置可隐藏手账的热量和营养信息。Demo 和真实模式分别构建。阶段 1、2 的源码、素材和原始截图保留。

真实 AI、自动抠图、完整图鉴、好友共享、趋势、APK 和部署仍属后续阶段。本次未修改云服务器、Docker、WSL 或 Android 环境。

## 二、认证遗留问题

先以真实账号 A、B 和共用 Cookie 的测试客户端复现。旧 A 的访问令牌仍只访问 A，但以该凭据向旧刷新接口发请求时，接口返回 200 并使用 B 的 Cookie。旧退出实现也会无条件发出清除 Cookie 的响应。

现在刷新和退出校验签名的账号和会话绑定。旧 A 搭配 B 的 Cookie 刷新返回 401。旧 A 退出撤销 A 的会话并保留 B 的 Cookie，B 随后仍可请求与续期。浏览器使用 BroadcastChannel 通知其他标签页，Web Locks 避免 Cookie 操作交错。账号变化会取消在途请求并暂停旧标签页自动恢复，该标记不含身份或凭据。后端和浏览器均已覆盖复现、修复及旧标签页刷新。原有认证测试全部通过。[安全说明](SECURITY.md)

## 三、磁盘占用

| 检查点 | C 盘可用 | D 盘可用 |
| --- | ---: | ---: |
| 开始前 | 28.553 GiB | 315.031 GiB |
| 首次安装新增依赖后 | 28.512 GiB | 315.005 GiB |
| 构建、测试及截图后的一次检查 | 28.519 GiB | 314.953 GiB |
| 相对起点变化 | −34.04 MiB | −80.36 MiB |

| 项目 | D 盘路径与逻辑大小 |
| --- | --- |
| 原有 Python 虚拟环境 | `backend/.venv`，约 82.60 MiB |
| 新增依赖 | Pillow 13.0.0 约 15.54 MiB，python-multipart 0.0.34 约 0.19 MiB |
| pip 缓存 | `D:/DevEnv/pip-cache`，约 20.57 MiB |
| 临时文件与测试库 | `D:/DevEnv/tmp`，pytest 和浏览器测试每次生成独立目录 |
| 开发库与媒体 | `backend/data/fooddiary.db` 为 151,552 B。开发媒体目录未写入样例图片，验收图在独立测试目录 |
| 浏览器 | 复用 Chrome，`D:/DevEnv/playwright` 下载目录 0 B |

安装前核验已有虚拟环境的安装方案和 pip 配置，锁文件复验及 `pip check` 均通过。C 盘低空间和异常占用阈值均未触发。整盘变化包含其他进程活动。未清理系统盘或其他项目。

## 四、数据库与迁移

`0002_meal_diary` 新增 `meals`、`meal_items`、`media_assets`、`meal_media` 与 `meal_requests`。包括主记录与图片同所有者的复合外键、幂等键联合主键、餐次日期及用餐时间索引、同餐明细和照片排序唯一约束。已在开发库升级，独立测试验证 0001 阶段的账号、会话及设置保留。模型核对无待应用操作。[表、索引与时区规则](DATABASE.md)

## 五、图片存储

认证后流式限额接收 JPEG、PNG 或 WebP，校验单图大小与像素，规范化方向和色彩模式并去 EXIF/GPS。原图和缩略图使用 WebP，两种尺寸通过环境配置。存储位于 D 盘私有运行目录，读取再次验证所有者。失败时补偿清理已发布文件。草稿和无记录文件超期后可检查与清理，同一图片仍有引用时保留。[存储策略和清理命令](STORAGE.md)

## 六、真实 API

新增 11 项操作，包含私有原图和缩略图、照片上传删除、餐次 CRUD、按日期/餐次分页、月历和日报。餐次和明细与关联一起提交。重复创建复用请求标识，更新使用版本。摘要返回各项营养的已知合计及完整性，未知保留 null。[API 契约](API.md)

## 七、前端模式

沿用独立的 Vite 入口。真实手账和照片只访问服务端，API 构建无 Demo 数据层，Demo 构建无真实认证调用。图片通过带 Bearer 的 Blob 请求再创建 Object URL，组件卸载或账号变更时取消、释放。日历只请求所需月份及缩略图。

## 八、运行截图

保留阶段 1 的奶油纸色、手账日期、餐次标记、抹茶绿与留白。真实照片以圆角相片框展示。截图来自 Chromium 中执行真实上传、保存和读取后的页面，仅含测试账户与无隐私样例。

[空手账](screenshots/phase-3/01-empty.jpg) · [本地选图预览](screenshots/phase-3/02-photo-preview.jpg) · [新增多食物](screenshots/phase-3/03-multiple-foods.jpg) · [保存后的桌面手账](screenshots/phase-3/04-desktop-saved.jpg) · [月历](screenshots/phase-3/05-calendar.jpg) · [详情](screenshots/phase-3/06-detail.jpg) · [编辑](screenshots/phase-3/07-edit.jpg) · [手机端](screenshots/phase-3/08-mobile.jpg) · [账号 A](screenshots/phase-3/09-account-a.jpg) · [账号 B](screenshots/phase-3/10-account-b.jpg)

## 九、双账号隔离

独立真实账户 A、B 直接请求后端。A 不能读取、编辑、删除 B 的记录，也不能读取、关联或删除 B 的原图和缩略图。跨账号与随机资源的 404 一致。无身份及撤销会话返回 401。相同账号在独立浏览器登录时可恢复该账号保存的记录和照片。

## 十、自动化测试

| 测试 | 最终执行结果 |
| --- | --- |
| 后端 pytest | 66 通过，含阶段 2 的 34 项 |
| API Playwright | 13 通过，含原有 7 项及阶段 3 的 6 项 |
| Demo Playwright | 12 项交互/响应式、9 项截图回归均通过 |
| 阶段 3 截图场景 | 1 通过，产出 10 张截图 |
| 构建与联调 | TypeScript、API/Demo 两套生产构建、构建模式隔离、Alembic 模型核对、联合启动和代理通过 |

覆盖本地图片格式和限额、EXIF/GPS、补偿、实际清理、事务回滚、幂等、并发更新及 SQLite 锁、重启、时间边界和双账号授权。浏览器覆盖回包丢失后的同键重试、双击、过期照片请求、快速切日、账号切换和营养隐藏。

## 十一、本地性能

用独立 Windows 进程重复处理 4000×3000、6,240,910 B 的合成 JPEG 五次。规范化原图为 1600×1200、642,616 B，缩略图 4,014 B。耗时中位 561.2 ms、最高 838.2 ms。进程工作集从处理前 65.7 MiB 到峰值 101.4 MiB，包含 Python 和已加载库。实际服务器性能尚未测量。

## 十二、实际启动

```powershell
.\scripts\setup-backend.ps1 -Action Install
.\scripts\setup-backend.ps1 -Action Migrate
.\scripts\start-dev.ps1 -FrontendPort 15175 -BackendPort 18021
```

本机 5173 已有进程。备用端口下的前端 HTTP 200、后端 ready 和 Vite 代理均实测。开发脚本仅绑定 `127.0.0.1`，验收进程已停止。默认仍为 5173/8000，可按需覆盖。

## 十三、当前不足

MySQL 8.4、云主机负载、生产代理上传与 HTTPS、HEIC、真实手机相机和其他浏览器尚未验证。媒体文件和数据库的生产备份恢复仍待部署阶段。测试使用 httpx，Starlette TestClient 报一条弃用提示，测试通过。

## 十四、Git 信息

分支为 `feature/phase-3-meal-diary`，基础提交 `7e4abd0b29af084d86be8c206c3c0f5ede95bf3a`。最终 SHA 和工作区状态随推送验收结果提供。[远端阶段分支](https://github.com/zhenzhenqin/magic/tree/feature/phase-3-meal-diary)

## 十五、验收结论

阶段 3 达到本地开发及提交审查条件。等待架构顾问与用户验收，阶段 4 尚未开始。
