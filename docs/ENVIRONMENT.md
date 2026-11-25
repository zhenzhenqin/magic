# 阶段 0 环境检查

检查日期为 2026-11-25（北京时间）。内存、磁盘、负载和监听状态均为检查时的快照。

## 本地开发机

| 项目 | 实测结果 |
| --- | --- |
| 工作目录 | `D:\桌面\mjc` 原为空，未处于已有 Git 仓库内。项目初始化于 `D:\桌面\mjc\fooddiary` |
| 操作系统 | Windows 11 家庭版中文版，64 位，版本 `10.0.26200`，内部版本 `26200` |
| CPU | Intel Core i5-13500H，12 核、16 逻辑处理器 |
| 内存 | 总计 15.75 GiB，可用 1.90 GiB |
| 磁盘 | C: 200 GiB，总可用 28.71 GiB。D: 751.64 GiB，总可用 320.82 GiB。两者均为 NTFS |
| Git | `2.49.0.windows.1` |
| Node.js | `22.19.0` |
| 包管理器 | npm `10.9.3`、pnpm `10.17.1`、Corepack `0.34.0`，均可运行 |
| Python | `3.13.9`，`py` 启动器识别此安装 |
| Docker | Docker Desktop `4.41.2`，CLI `28.1.1`。`desktop-linux` 上下文的 Linux 引擎命名管道不可用，客户端无法连接服务端 |
| Docker Compose | `docker compose` 与 `docker-compose` 均报告 `v2.35.1-desktop.1`。容器执行未验证，受引擎状态限制 |
| WSL | 可查询状态。默认发行版 Ubuntu，WSL 2，检查时为 `Stopped`。发行版启动及内部工具链未验证 |
| Java JDK | Oracle JDK 与 `javac` 均为 `21.0.9`，`JAVA_HOME` 指向现有 JDK |
| Android SDK | `ANDROID_HOME`、`ANDROID_SDK_ROOT` 未设置。默认 SDK 目录、已检查的 SDK 注册项和 PATH 未发现 SDK 或 `sdkmanager` |
| Android Studio | 已检查常见安装路径、Toolbox 默认位置及卸载注册项，未发现安装。非标准自定义安装位置未验证 |
| adb | PATH 中不可用，默认 SDK 位置未发现 Platform Tools |
| Android APK | 当前不具备已验证的本地构建条件。需可用的 SDK Platform、Build Tools 和项目 Gradle 工具链。真机调试另需 Platform Tools / adb |
| MySQL | MySQL Community 客户端及服务端二进制 `8.0.34`，Windows 的 `MySQL` 服务处于运行状态。数据库登录、内容与应用迁移未验证 |
| SSH | Windows OpenSSH `9.5p2`，已用现有密钥完成本次服务器检查 |

## 云服务器初始盘点

对 `113.44.64.113` 使用现有密钥进行非交互 SSH 登录，连接启用了已知主机密钥严格校验。以下结果来自远程只读命令。

| 项目 | 实测结果 |
| --- | --- |
| 主机名 | `hcss-ecs-d2f4` |
| 操作系统与内核 | Debian GNU/Linux 11 (bullseye)，`5.10.0-34-amd64`，`x86_64`，KVM |
| CPU | AMD `General Purpose Processor`，2 vCPU，`lscpu` 报告 1 插槽、1 核/插槽、2 线程/核 |
| 负载 | 1/5/15 分钟均为 `0.00`，`top` 采样 CPU 空闲约 `96.8%`，开机约 167 天 |
| 内存 | 总计 `1.9 GiB`，已用约 `1.3 GiB`，可用 `440 MiB`，完全空闲约 `111 MiB`。Swap `2.0 GiB`，采样时使用 `0 B` |
| 磁盘 | 单块 `vda` 40G，`/dev/vda1` 挂载 `/`。`df -h` 显示总 `40G`、已用 `15G`、可用 `23G`、使用率 `40%`。Docker 的 overlay 挂载共用该根盘 |
| Docker | Engine Community 客户端和服务端均为 `29.6.1`，Compose `v5.2.0`，守护进程运行 |
| 容器 | `docker ps -a` 列出 7 个运行中的 Exam Guardian 容器。包括 HTTP 入口、Web、Worker、evidence、SEB、cron 和数据库 |
| 镜像 | `docker images` 列出 4 个带标签镜像，涉及 Exam Guardian runtime 和 MariaDB、SEB Server 以及 Ubuntu 基础镜像 |
| Web | 80 端口由 Python 进程监听，443 端口由 Apache 监听。另有回环 Gunicorn、Apache 与 Java 监听，Nginx 的 systemd 单元未找到，监听列表也未发现 Nginx。所检查的常见站点目录无输出。现有站点的实际域名、虚拟主机、证书和站点根路径未验证 |
| 数据库 | 宿主机 `mariadb.service` 运行，显示 MariaDB `10.11.18`。另见 Exam Guardian MariaDB 容器及两个回环 MariaDB 监听。具体实例归属、数据内容、备份和 MySQL 8.4 实际运行未验证 |
| 主机防火墙 | 读取了 nftables 和 iptables 规则。IPv4 iptables 的 INPUT、OUTPUT 默认 `ACCEPT`，FORWARD 默认 `DROP`，可见 Docker 转发和 NAT 链。云安全组、外部 HTTP/HTTPS 可达性以及 ELTS 生效情况未验证 |

### 停服前监听端口

| 监听地址与端口 | 进程 |
| --- | --- |
| `0.0.0.0:22`、`[::]:22` (TCP) | `sshd` |
| `0.0.0.0:80` (TCP) | `python` |
| `0.0.0.0:443` (TCP) | `apache2` |
| `127.0.0.1:3306`、`:13316` (TCP) | `mariadbd` |
| `127.0.0.1:18080` (TCP，经 IPv4 映射) | `java` |
| `127.0.0.1:18081`、`:18092` (TCP) | `apache2` |
| `127.0.0.1:18090` (TCP) | `gunicorn` |
| `127.0.0.1:29338`、`:29339` (TCP) | `uniagentd` |
| `127.0.0.1:323`、`[::1]:323` (UDP) | `chronyd` |

## 授权停服与缓存清理

初始只读盘点完成后，用户追加授权停止 Exam Guardian 和宿主机 MariaDB，并清理可重建的缓存。基本系统服务、Docker 和 SSH 均继续运行。

| 项目 | 停服及清理后的复查 |
| --- | --- |
| Exam Guardian | 7 个容器均已停止。HTTP 入口、Web、cron 和 Worker 在 60 秒等待期后以 `137` 退出，`OOMKilled=false`。evidence 与数据库容器退出码为 `0`，SEB 为 `143` |
| 宿主机 MariaDB | `inactive`，原有 `enabled` 开机配置保留，主机重启时可能再次启动 |
| 保留项 | 业务数据、服务配置、容器、镜像和卷保留。清理前后的容器 ID、镜像 ID 和卷名清单一致。业务数据可读性与恢复启动未验证 |
| 缓存 | APT 下载缓存从约 `136 MiB` 降至 `24 KiB`。Docker Builder 缓存条目由 31 个降至 0，镜像保留 |
| 根盘 | `df -h` 可用从 `23G` 增至 `26G`，使用率从 `40%` 降至 `33%`。清理前后 `df -B1` 的净增量为 `2,792,366,080` 字节，约 `2.60 GiB` |
| 内存和 CPU | 可用内存从 `440 MiB` 增至约 `1.5 GiB`，Swap 仍未使用。复查 1/5/15 分钟负载为 `0.06 / 0.02 / 0.00`，CPU 空闲约 `96.8%` |
| 监听 | `80`、`443`、`3306`、`13316` 及原业务回环端口均无监听。剩余 SSH `22/TCP`、回环 `uniagentd` 端口 `29338/29339 TCP` 和回环 `chronyd` 端口 `323/UDP` |

## 可行性与待验证事项

- **本机开发**。现有 Node.js 和 Python 可用于 Web 原型及后端开发。Vite 8 的 Node 22 分支要求至少 22.12，本机满足。Docker 路径需等 Linux 引擎可连接后验证。本机 MySQL `8.0.34` 与预定 `8.4 LTS` 存在版本差异，数据库迁移验收应在目标版本的独立实例上执行。[Vite 8 版本说明](https://vite.dev/blog/announcing-vite8) · [MySQL 8.4 手册](https://dev.mysql.com/doc/refman/8.4/en/)
- **服务器容量**。Compose 可作为部署方式。停服后约 `1.5 GiB` 可用内存，可作为受控轻量试运行的候选。全机仍只有 2 vCPU 和约 `1.9 GiB` 内存，API、MySQL、Nginx 与 CPU 抠图同机长期运行需压测。若原业务恢复则重新测量资源。MySQL 使用项目独立实例及私有网络，避免和现有数据库争用宿主机端口或共享数据。
- **CPU 抠图**。由独立进程执行，先在本机或测试环境用 `u2netp`、单任务并发和限制输入像素数的设置测量。按真实食物照片的质量、峰值 RSS、冷启动和处理耗时决定模型与部署。测量前不在现有服务器安排生产抠图任务。[rembg 模型与 CPU 安装说明](https://github.com/danielgatis/rembg)
- **图片存储**。清理后 `26G` 是根盘共享余量。少量样例可用于估算，生产容量仍需根据日新增量、原图与缩略图及贴纸的合计平均字节数、保留期、备份和磁盘余量计算。当前未发现单独的图片数据盘。
- **Android**。Capacitor 8 候选满足 Node 22 前提。其模板使用 compile/target SDK 36，最低运行 API 24。安装批准后核对 SDK Platform 36、匹配的 Build Tools、Android Studio 和 Gradle 所用 JDK，再做调试 APK 与真机验证。[Capacitor 环境要求](https://capacitorjs.com/docs/getting-started/environment-setup) · [Capacitor 8 Android 版本配置](https://capacitorjs.com/docs/updating/8-0)
- **域名和 HTTPS**。正式域名、DNS 管理权限、安全组规则和 TLS 终止位置尚待确认。80/443 当前无监听，若旧站恢复，需评审统一入口或分开部署。证书可使用能更新 DNS TXT 记录的 DNS-01，或通过公网 80 入口执行 HTTP-01 验证。若使用中国大陆云节点，正式上线前按接入商要求核验网站与 App 的备案适用情况。域名、备案与证书均未验证。[Let's Encrypt 验证方式](https://letsencrypt.org/docs/challenge-types/) · [华为云备案说明](https://support.huaweicloud.com/icp_faq/icp_05_0145.html)
- **操作系统支持**。Debian 11 项目的 LTS 于 2026-08-31 结束。正式部署前需确认宿主机的扩展安全覆盖，或选用受支持的部署主机。当前未检查 ELTS 订阅与补丁覆盖。[Debian LTS 公告](https://www.debian.org/News/2026/20260831)

## 实际检查命令

- 本机使用 `Get-Location`、`Get-ChildItem`、`git rev-parse`、`rg --files`、`Get-CimInstance`、`Get-Command`、`Get-ItemProperty`、`Get-Service`、`Test-Path` 及工具版本命令。另查询了 WSL 列表、Docker 引擎状态、Compose 和 MySQL 二进制版本。
- 服务器执行 `hostname`、`uname -a`、`cat /etc/os-release`、`lscpu`、`free -h`、`df -h`、`lsblk`、`uptime`、`top -bn1`、`ss -lntup`、`docker version`、`docker compose version`、`docker ps -a`、`docker images`、`systemctl status nginx --no-pager --lines=0`、`systemctl list-units`，并检查常见站点目录与可用的主机防火墙命令。
- 获授权后用 `docker inspect`、`systemctl show`、`docker system df` 和 `du` 核对维护范围。应用容器按入口、Web 和 cron、Worker 和依赖服务、数据库的顺序通过 `docker stop --timeout 60` 停止，随后执行 `systemctl stop mariadb.service`。使用 `apt-get -o Dir::Cache::archives=/var/cache/apt/archives clean` 和 `docker builder prune --all --force` 清理缓存，再复查服务、端口、资源和保留清单。[APT 手册](https://manpages.debian.org/bullseye/apt/apt-get.8.en.html) · [Docker Builder 命令手册](https://docs.docker.com/reference/cli/docker/builder/prune/)
