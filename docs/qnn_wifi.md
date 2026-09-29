# 骁龙手机 NPU 外接算力（QNN Wi-Fi）

本分支 `c3xl-vip` 从 `c3xl-dev` 分出，集成了 OPIF/Cinque v3 的 Android 手机 NPU 外接推理链路。默认关闭，关闭时 modeld 完全走原有本地模型路径。

## 组成

- 车机侧：`openpilot/sunnypilot/modeld_v2/external_host/`
  - `qnn_cli.py`：配对、配置、状态、执行模式切换
  - `qnn_client.py`：固定手机证书指纹的 TLS/TCP 协议 v2 客户端
  - `qnn_discoveryd.py`：局域网/USB 发现
  - `qnn_hotstandby.py`：本地模型逐帧热备，手机结果通过资格窗口后接管
  - `qnn_model.py`：Cinque v3 输出适配
- 手机侧源码：`tools/opif_android/`
  - Kotlin App、JNI、QNN HTP 推理服务、双摄输入和 OPIF 协议
  - APK、QNN/QAIRT 二进制和模型权重不随仓库提交，需要按 `tools/opif_android/README.md` 单独构建/准备。
- UI：设置 -> 开发者 -> `Android NPU Wi-Fi` / `Snapdragon NPU status / pairing`
- 参数：`C3XLQnnWifiEnabled`、`C3XLQnnWifiControl`、`C3XLQnnWifiFailedThisOnroad` 等。

## 使用顺序

1. 手机和 C3XL 加入同一 Wi-Fi，启动 Android 推理服务并打开临时配对窗口。
2. 在设备开发者设置打开配对页，先发现或手动输入手机地址，核对手机屏幕上的 64 位 SHA256 指纹，再输入手机会话码。
3. 保持 `QNN control preference` 关闭进行 shadow 验证；只有独立资格记录通过后才允许控制输出接管。
4. 每次 onroad 首次失败会写入 `C3XLQnnWifiFailedThisOnroad` 并锁定本地模型到本次行车结束。

## 分支切换

从旧的 `c3xl-dev` 或任何还没有 QNN 参数/原生组件的分支切到本分支时，必须重新执行 `build.py`/`scons`。启动脚本会检测 `C3XLQnnWifiEnabled` 是否已编译进 Params，发现缺失时自动强制重建一次，避免 manager 因 `UnknownKeyName` 启动失败。

## 构建注意

启用后会通过 `openpilot/sunnypilot/SConscript` 编译 `external_host/opif/SConscript`，生成 `opif_native` 和 C3XL 用的 `wifi_power_ctl`。Android 端模型 ABI 是 Cinque v3，不是普通 supercombo pkl 的直接替换。
