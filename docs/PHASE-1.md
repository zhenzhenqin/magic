# FoodDiary 阶段 1 汇报

## 一、阶段完成情况

已交付原创响应式 Web 原型。用户可通过手账、月历和图鉴回看记录，用本地图片或手动输入记一餐，管理饭搭子和共享权限，并在双人手账查看两人同一天的记录。全部样例和识别结果为演示数据。当前原型具备提交审查的条件，真实后端、认证、部署、模型和 APK 仍在各自阶段的范围内。

## 二、磁盘占用报告

可用空间取自 Windows 磁盘查询。Chrome 直接复用已安装版本，因此没有浏览器下载后的检查点。

| 检查点 | C 盘可用 | D 盘可用 |
| --- | ---: | ---: |
| 开始前 | 28.675 GiB | 320.822 GiB |
| 安装依赖后 | 28.584 GiB | 320.578 GiB |
| 食物和字体素材准备后 | 28.551 GiB | 320.543 GiB |
| 最后一次构建后 | 28.536 GiB | 320.527 GiB |
| 最终截图后 | 28.535 GiB | 320.525 GiB |
| 提交前复测 | 28.536 GiB | 320.532 GiB |
| 提交前相对起点净变化 | −142.76 MiB | −297.00 MiB |

| 目录 | 实际路径 | 提交前逻辑文件大小 |
| --- | --- | ---: |
| 项目 | `D:/桌面/mjc/fooddiary` | 149.31 MiB，含依赖与生成物 |
| pnpm store | `D:/DevEnv/pnpm-store/v10` | 144.13 MiB |
| pnpm 元数据 | `D:/DevEnv/pnpm-store/metadata` | 75.86 MiB |
| npm cache | `D:/DevEnv/npm-cache` | 8,497 B |
| Playwright 浏览器下载路径 | `D:/DevEnv/playwright` | 0 B |
| 实际使用的浏览器 | `C:/Program Files/Google/Chrome/Application/chrome.exe`，Chrome 158.0.8127.38 | 现有安装目录约 526.23 MiB |
| 临时文件和浏览器配置 | `D:/DevEnv/tmp` | 31.91 MiB，含中转图片和测试临时缓存 |
| 依赖和 Vite 缓存 | `frontend/node_modules` 与其中的 `.vite` | 146.33 MiB，包含 5.18 MiB Vite 缓存 |
| 构建和测试结果 | `frontend/dist` 与 `frontend/test-results` | 1.04 MiB 与 45 B |
| 项目素材和截图 | `frontend/src/assets/food` 与 `docs/screenshots/phase-1` | 0.76 MiB 与 0.87 MiB |

内置 ImageGen 固定在 C 盘 Codex 缓存生成 12 张原始 PNG，合计约 24.10 MiB。处理和最终素材存储在 D 盘。D 盘中转副本仍保留，清理该副本的命令被自动策略拦截。整盘变化也受 Windows 和其他程序影响。目录文件大小是逻辑值，pnpm 硬链接可能在目录汇总中重复计入。

## 三、视觉设计

奶油纸张底色搭配深橄榄字色、浅鼠尾草绿、奶油黄和低饱和暖色。标题使用本地 Noto Serif SC，正文使用系统中文无衬线字体。以原创手绘线条、透明摄影风格食物贴纸和餐次纵向留白形成手账感。间距、配色、字体、圆角和阴影由 Design Tokens 统一管理。动效包括贴纸轻微转动与控件过渡，并尊重系统减少动态效果设置。[素材来源与许可](ASSETS.md)

## 四、技术实现

| 项目 | 实装 |
| --- | --- |
| Vue、Router、Pinia | 3.5.46、4.6.5、3.0.4 |
| TypeScript、Vite、Vue 插件、vue-tsc | 5.9.3、8.3.8、6.0.11、3.3.14 |
| Tailwind CSS / Vite 插件、Lucide | 4.3.5、0.577.0 |
| Node.js、pnpm、Playwright | 22.19.0、10.17.1、1.65.1 |
| 路由 | `/`、`/calendar`、`/catalog`、`/capture`、`/friends`、`/friends/:id/{diary,catalog,together,permissions}`、`/me`、`/me/stats` |
| 数据 | Pinia 协调类型化 Mock Repository，localStorage 存小体积记录与权限，IndexedDB 存经过浏览器重新编码的照片 |
| 权限 | 每对关系独立保存「授予人 → 接收人」的九项权限，由同一套数据投影实现名称、备注、照片等字段隐藏。好友视图只读，可切换演示账号验证 |

## 五、运行方式

在 D 盘项目根目录的 PowerShell 中执行。

```powershell
.\scripts\setup-dev-env.ps1 -Action Install
.\scripts\setup-dev-env.ps1 -Action Dev
```

开发服务器实测返回 HTTP 200。启动后访问 [127.0.0.1:5173](http://127.0.0.1:5173/)。

## 六、页面截图

实际 Chrome 页面捕获，统一在北京时间 2026-11-25 的演示日期取样。

| 页面 | 截图 |
| --- | --- |
| 手机首页 | [390 × 844](screenshots/phase-1/01-home-mobile.jpg) |
| 电脑首页 | [1440 × 900](screenshots/phase-1/02-home-desktop.jpg) |
| 饮食月历 | [月历](screenshots/phase-1/03-calendar.jpg) |
| 美食图鉴 | [图鉴](screenshots/phase-1/04-catalog.jpg) |
| 拍照及识别确认 | [图片预览与结果](screenshots/phase-1/05-capture.jpg) |
| 饭搭子 | [好友与申请](screenshots/phase-1/06-friends.jpg) |
| 双人手账 | [两人餐次记录](screenshots/phase-1/07-together.jpg) |
| 好友共享授权 | [九项权限](screenshots/phase-1/08-permissions.jpg) |
| 个人中心 | [账号与演示设置](screenshots/phase-1/09-profile.jpg) |

## 七、测试报告

| 验证内容 | 结果 |
| --- | --- |
| 依赖安装、TypeScript、生产构建、开发服务器 | 全部通过 |
| 手账日期、月历月份、跳回指定日期、浏览器返回 | 通过 |
| 键盘进入详情、Escape 关闭和焦点还原 | 通过 |
| 图鉴分类、搜索、收藏和收藏刷新后保留 | 通过 |
| 本地文件选择预览、模拟识别、保存、编辑、删除，跨手账、月历和图鉴联动 | 通过 |
| 记录和照片刷新后保留、手动记录、重置演示数据 | 通过 |
| 好友申请、接受和拒绝、好友手账与图鉴只读 | 通过 |
| 双人手账日期切换、未记录和未授权状态 | 通过 |
| 九项权限控件、单向授权、不同账号视角、字段过滤及全部撤销后刷新 | 通过 |
| 360×800、390×844、430×932、768×1024、1440×900 | 11 个核心路由逐一访问。横向溢出、导航留白、图片比例和减少动态效果检查通过 |
| Playwright 测试 / 截图 | 12 个交互与响应式场景通过，9 个截图场景通过 |

首轮测试发现贴纸溢出干扰点击，已约束图像尺寸和点击区域。测试中选择餐次、权限页导航和营养详情断言的定位也已修正，最终整套验证通过。

## 八、Git 信息

阶段分支为 `feature/phase-1-ui`，基于阶段 0 的 `4b4a8e9`。阶段 1 最终 SHA 为 `75023b4475a5541d655b87f901a5f3179f1f5f3e`，阶段 2 开始前已与远端逐字核对。本次交付包含前端源码、测试与锁文件，新增 D 盘启动脚本、素材许可和阶段报告，并更新 `AGENTS.md`、`README.md`、`PROGRESS.md`、`.gitignore` 及架构决策文档。[阶段 1 提交](https://github.com/zhenzhenqin/magic/commit/75023b4475a5541d655b87f901a5f3179f1f5f3e)

## 九、问题与风险

- 授权与身份是浏览器内演示。真实访问控制和跨端同步仍待后端实现。
- 响应式验证使用 Windows Chrome 的不同视口。Android 真机、系统安全区行为以及其他浏览器未验收。
- Docker 引擎、Android SDK、服务器容量、Debian 11 扩展安全覆盖、旧业务恢复和 GitHub 审查账号 404 均记录在[项目进度](../PROGRESS.md)。

## 十、阶段结论

阶段 1 达到开发交付及提交审查条件，等待架构顾问审查和用户验收。阶段 2 尚未开始。
