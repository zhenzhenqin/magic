# 本地美食贴纸

在 Windows D 盘项目中执行以下命令。

```powershell
.\scripts\setup-sticker-worker.ps1 -Action Install
.\scripts\setup-backend.ps1 -Action Migrate
.\scripts\start-dev.ps1 -WithStickerWorker
```

`setup-sticker-worker.ps1 -Action Check` 验证独立虚拟环境、CPU Provider 和权重 SHA-256。Worker 读共享 SQLite 和媒体根目录。准备脚本下载一个权重，运行时只读已校验的本地权重。默认不启动外部识别。Windows 开发机实测，Linux CPython 3.13 x86-64 wheel 已核对。

## 用餐流程

选图后默认自动制作，可在录入页关闭当前浏览器的自动制作。等待时可以填写和保存。一张照片可查看原图、透明抠图或最终白边贴纸。失败时保存原图，也可重新生成或手动裁剪。手动裁剪按原图坐标截取，用于用户自行选取画面。图鉴和月历使用缩略图，手账用同一张照片的贴纸，详情仍可看原图。稳定的角度由媒体 UUID 决定。

API 模式拍摄照片上传后自动排队。浏览器由真实裁切透明图层和白边结果播放动画。可以在完成前保存或明确选择原图，选择会跟随该餐记录。 [拍摄和动画](CAMERA.md)

## 任务与磁盘

- `StickerWorker` 原子领取一项全局任务，持久子进程复用单线程 ONNX 会话。推理期间释放数据库事务。默认增量等待上限 25 秒，超时会终止推理子进程，旧租约恢复最多两次。
- 服务端比较图片 SHA-256、处理版本、裁剪和尺寸指纹，通过任务令牌阻止过期结果覆盖。取消后，现有图片仍可用。运行中的派生任务使用租约保护源图，待处理任务保护期为一天。
- 派生图生成后补验用户额度及全局剩余磁盘。WebP 保存真实 RGB 和 Alpha。自动抠图裁掉空白边缘并对 Alpha 膨胀、柔化，形成轮廓描边。用户保留原图。
- 文件使用私有键及授权读取路径。图鉴封面须来自现有餐次。未跟踪文件由 dry-run 清理报告。公开仓库仅纳入授权的照片示例和截图。

完整 rembg 安装遇到大体积依赖下载停滞，实际推理保留其 u2netp 权重和预处理算法，使用 ONNX Runtime CPU 与 Pillow。默认外边长 768，模型内部输入为 320×320。模型判断显著前景，可能留下餐具或把非食物当作主体。 [真实视觉与性能](PHASE-5.md)

### U²-NetP 私测用权重

现有 `u2netp.onnx` 大小 4,574,861 字节。实测 MD5 `8e83ca70e441ab06c318d82300c84806` 与 rembg 下载器校验值一致。项目用更强的 SHA-256 `309c8469258dda742793dce0ebea8e6dd393174f89934733ecc8b14c76f4ddd8` 运行时复验。rembg 模型目录将该 ONNX 产物直接追溯到 U²-Net 上游。上游作者对公开模型与代码适用同一许可有明确答复，仓库许可为 Apache-2.0。已知训练集为 DUTS，其公开说明没有给出一项可以替代模型许可的条款。 [rembg 转换文件来源](https://github.com/danielgatis/rembg/blob/main/rembg/sessions/u2netp.py) · [rembg 上游映射](https://github.com/danielgatis/rembg#models) · [作者说明](https://github.com/xuebinqin/U-2-Net/issues/208) · [Apache-2.0](https://github.com/xuebinqin/U-2-Net/blob/master/LICENSE) · [DUTS](https://saliencydetection.net/duts/)

据此保留该 4.36 MiB 权重作为非公开服务器端内测首选。在授权部署时，权重从服务器私有模型目录加载，随部署保存 Apache-2.0 文本、U²-Net 论文及作者署名、转换出处和摘要。仓库、站点和内测用户设备只接收业务图像。公网商业使用或权重再分发另核对适用条件和原始转换链，当前未向云主机传输或启用权重。
