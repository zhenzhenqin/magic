# FoodDiary 生产部署

本文件供阶段 7.2 经批准的执行使用。先确认宿主机支持周期、允许使用的 HTTPS 入口、云安全组与维护权限。 [实际状态](PHASE-7.2.md)

## 架构与目录

浏览器经 Nginx 访问 Vue API 模式静态构建及同源 API。单个 Uvicorn 进程监听 `127.0.0.1:18080`，确保每 IP 和账号的进程内限流一致。FastAPI、可选 CPU 贴纸 Worker 和可选外部 AI Worker 使用同一 SQLite WAL 和私有媒体根目录，由 systemd 管理。Nginx 单独运行，静态根只指向发布中的 `web/`。

| 路径 | 权限和用途 |
| --- | --- |
| `/opt/fooddiary/releases/<SHA>` | root 管理的应用版本、静态文件和 Python 虚拟环境 |
| `/opt/fooddiary/current` | 指向已验证版本的链接 |
| `/opt/fooddiary/shared/config` | root 与 `fooddiary` 组访问，环境文件 0640 |
| `/opt/fooddiary/shared/data`、`media` | `fooddiary` 私有 0700，持久化数据 |
| `/opt/fooddiary/shared/models` | 服务可读的本地模型目录，权重独立管理 |
| `/opt/fooddiary/shared/logs` | root 管理的维护锁及运维文件。服务日志使用 journald |
| `/var/backups/fooddiary` | root 私有 0700，已校验的恢复点 |

目标基线为受支持的 x86_64 Linux、Python 3.13、SQLite 3.35+、Nginx 与 systemd。复用现有 Docker 可作为隔离运行时的对照方案，例如选维护中的基础镜像来供应 CPython 与 glibc。Docker 与进程方案都依赖宿主机内核的安全维护。当前 Debian 11 上的 Python 3.9.2 无法安装本项目锁版本。Debian 13 可作为经授权的系统选择。 [Debian 11 LTS 结束公告](https://www.debian.org/News/2026/20260831) · [Debian 13 发行信息](https://www.debian.org/releases/trixie/)

现有实例只有系统盘，保留 Exam Guardian 文件、MariaDB 数据、Docker 本地卷及证书配置。优先考虑经过备份验证的 Debian 11 → 12 → 13 原地升级。每一段都需要检查第三方软件源、保存现有软件与数据、保留云控制台恢复入口，并验证 SSH 及旧服务状态。若选择重装，先在系统盘之外验证旧业务迁出和可恢复备份。具体镜像和整机备份可用性以实际云地域及控制台为准。 [Debian 升级指南](https://www.debian.org/releases/trixie/release-notes/upgrading.en.html) · [华为云镜像说明](https://support.huaweicloud.com/usermanual-ecs/ecs_03_0201.html)

## TLS 与公网入口

优先使用用户控制的域名及受信任证书。确认 DNS、ECS 地域、云安全组、现有站点和自动续签。中国大陆节点须依接入商要求确认网站备案或接入手续，IP 直连也需确认适用要求。 [华为云备案说明](https://support.huaweicloud.com/icp_faq/icp_05_0145.html)

本实例由用户确认为华为云 Flexus L 上海一，暂时没有域名或可核实的备案。免费 IP 证书的技术验证与公网接入授权独立。安全宿主机就绪后，可用已获准的可信私网入口。无现成入口时，可评估免费 Tailscale 方案，先在实际手机和服务器验证连通性及个人套餐条件。为 MagicDNS 全名签发证书，Nginx 仅绑定私网地址和回环，以保留现有发布维护检查。保持关闭公网 80 和 443，关闭 Funnel，内测访问限授权成员。实际验证精确 Origin、证书续签、Nginx 重载和私网维护门禁后再创建账号。 [华为云备案限制](https://support.huaweicloud.com/icprb-icp/icp_01_0008.html) · [Tailscale HTTPS](https://tailscale.com/docs/how-to/set-up-https-certificates)

没有域名时，技术上可评估 Let's Encrypt 公网 IPv4 证书。其有效期为六天，采用 Webroot 验证时官方要求 Certbot 5.4 或以上。需先确认 80 的 ACME 验证可达、证书更新和 Nginx 重载有效，以及获得相应公网许可。测试签发环境证书只作连通性验证。另一方案是通过已有可授权私网和带可信证书的入口限设备访问。普通公网 HTTP 仅可用作安全跳转或 ACME 验证。 [IP 证书及 Certbot](https://letsencrypt.org/2026/03/11/shorter-certs-certbot)

Nginx 模板由 `render-nginx.py` 生成独立站点，包含 HTTPS、固定主机名的跳转、同源代理、SPA 路由、媒体和隐藏路径拦截、TLS 响应头、10 MiB + 128 KiB 请求体上限及 130 秒代理时限。Nginx 禁用 API 上游缓存，覆盖其缓存响应头为 `no-store`。版本化哈希文件使用 30 天缓存。可信代理以清洗后的来源地址传递给 Uvicorn。反代验证保留真实 CA 校验。维护时只允许该站点的 `503` 与专用响应头通过维护验证。

相机需要页面本身的受信任 HTTPS。入口验证同时检查 `Permissions-Policy` 的 `camera=(self)`，以及 `Content-Security-Policy` 对 Blob 预览和实时媒体的允许范围。 [相机权限与兼容](CAMERA.md)

### 手机私网内测

1. 有合规公网入口后才开放 80 和 443。无域名时，免费 IP 证书仍须先满足华为云大陆接入条件。暂未满足时使用下述授权成员私网，不配置公网网站入口。 [华为云备案说明](https://support.huaweicloud.com/icp_faq/icp_05_0145.html) · [Let's Encrypt IP 证书](https://letsencrypt.org/2026/03/11/shorter-certs-certbot)
2. 使用现有私网或个人用途免费 Tailscale 网络。Tailscale 方案需要手机安装客户端并登录获准账号。只允许指定成员的设备访问标记为 FoodDiary 的节点 TCP 443，去除默认全网互通授权。确认上海实例和手机网络都能连接，包括直连或中继。禁用 Funnel，保留原有 SSH 22。 [Tailscale Grants](https://tailscale.com/docs/features/access-control/grants) · [个人方案](https://tailscale.com/pricing)
3. 在节点上获取 MagicDNS 实际全名，用 `tailscale cert` 生成浏览器信任证书。节点名称会出现在证书透明度日志，签发前使用不含私人信息的名称。Nginx 仅监听私网地址和回环，继续核对 `APP_ORIGINS`、Secure Cookie、真实 TLS、相机权限以及维护门禁。定时续签后先验 `nginx -t` 再重载。交付实测的 `https://<实际节点>.<实际网络>.ts.net`，当前尚未取得可访问的 URL。用户手机无需安装自签 CA。 [Tailscale HTTPS](https://tailscale.com/docs/how-to/set-up-https-certificates)
4. 对 Android Chrome 和 iPhone Safari 分别登录两个内测账号，从实际后置取景、换镜、重拍、拒绝权限和后台恢复，到上传、轮廓、贴纸、保存、刷新与好友同步。断网后恢复并检查只写入一条记录。用第三账号验证不可访问，并确认撤销授权后旧媒体地址失效、离开相机后系统停止使用镜头。手机测试只用获准样例，脱敏截图和视频留在 D 盘。
5. 备案及公网接入就绪后，新建公网 HTTPS 入口与精确 Origin，在同一发布版本上核验 TLS、账号重新登录、贴纸、撤销与备份。原私网入口可作为管理和恢复渠道，FastAPI 仍仅监听回环。

## 配置、密钥和账号

使用 `deploy/production/fooddiary.env.example`。正式文件通过安全渠道放在私有目录中，使用独立高熵 JWT 密钥，明确填写 `APP_ORIGINS` 中的 HTTPS 域名或 IP，确认 SQLite 与媒体路径为绝对路径。保留 `PUBLIC_REGISTRATION=false`。生产拒绝 Fake Provider，初始 AI 两家累计上限均为 0、服务停用。贴纸服务初始停用，待权重部署许可和服务器内存验证后再启用。应用上传仍校验每张 10 MiB、2000 万像素，使用全局磁盘保留空间。

授权的管理员可在后台路径下交互创建测试账号。密码提示隐藏输入，同时进行二次确认。

```bash
cd /opt/fooddiary/current/backend
sudo -u fooddiary .venv/bin/python -m app.create_account
```

## 阶段 7.2 执行顺序

1. 在 D 盘以 `scripts/build-release.ps1` 构建目标提交，核对产物目录 `REVISION`、`SHA256SUMS` 和计划发布的完整 SHA。可用 `python3.13 deploy/production/release-manifest.py verify 目录 SHA` 核对未准备的发布包。
2. 在受支持的 Linux 构建环境准备同架构 Python 3.13 二进制包及 wheelhouse。使用 `pip download --only-binary=:all: -r requirements.txt -r requirements-sticker.txt -d wheelhouse`。部署机准备工具、Python、Nginx 和 systemd 后，用 `bash deploy/production/prepare.sh check` 核对版本。
3. 只在批准后由管理员执行 `prepare.sh init` 创建项目专用用户和数据目录，布置独立配置。将已审核发布产物放入 `releases/<SHA>`，所有者 root，目录和公共静态文件允许只读。执行 `prepare.sh release <SHA> <WHEELHOUSE>` 创建隔离虚拟环境。确有授权时再加 `--with-sticker`。
4. 将模板作为新专用 systemd 单元和 Nginx 虚拟站点安装，复核所有权和安全策略。可先只配置经批准的 ACME 挑战入口，再启用 TLS 站点。使用 `systemctl daemon-reload` 与 `nginx -t` 检查。复用已有 Nginx 全局配置时确保它加载静态 MIME 类型。
5. 执行 `manage.sh publish <SHA>`，按需启用 API 的开机启动。初始仅启动 API。发布时 `APP_ORIGINS` 的第一项对应在本机监听 443 的 Nginx 主机名，系统 CA 必须信任该证书。授权和资源验收后再启动 Sticker Worker。连接可信入口并执行 `health.sh https <HOST> <SHA>`。
6. 使用两台设备和两个内测账号，依次验证登录、上传、真实贴纸、跨设备同步、好友申请、单向授权、双人手账和撤销后的旧 URL。检查受控重启后持久化，做一次独立目录恢复验证，并采样 CPU、RSS/峰值、Swap、磁盘及普通 API 延迟。

发布失败时保留旧版、已校验备份和失败日志。兼容的应用版本可以通过同一发布工具重新激活。涉及不兼容迁移时须在隔离环境先核对，避免覆盖线上新写入。 [备份与恢复](BACKUP-RESTORE.md) · [运维与回滚](OPERATIONS.md)
