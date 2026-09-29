# OPIF Android 完整源码快照

打包日期：2026-09-25。包含当前工作区中的 Android 实现（含尚未提交文件），与已安装版本同一轮源码。入口为 `android/app/src/main/kotlin/com/example/openpilotinference/android/MainActivity.kt`。

## 内容

- Kotlin 原生 View 界面、前台服务、模型安装器、JNI 桥接。
- C++ 完整 Cinque v3 QNN HTP 推理，严格禁止 CPU/GPU 算子回退；CPU 仍负责网络、UI 和调度。
- UDP / TCP / 同时监听选择、D2 流水线（1 帧执行、1 帧排队）、双摄输入预览、p50/p99 统计。
- 最近 10 秒 FPS 柱状图，自动纵轴，60 FPS 绘制目标。
- QNN EPContext 编译缓存、缓存失效/完整性检查和一次真实 NPU 预热。
- 构建/部署脚本、模型准备和验证工具、测试、协议与模型 ABI 文档。
- `script/` 中的协议客户端、双摄视频与车道线 overlay、流水线/网络基准源码。
- 离线模型验证所用两份小型输入 fixture：`OpenPilotInference/Resources/{img,big_img}.bin`。

本包是 Android 源码及相关客户端，不包含独立的 iOS/macOS App、Git 历史、APK、模型权重、SDK/NDK、QNN 二进制、视频素材和签名密钥。模型与依赖可按下方步骤恢复。原文档中的历史诊断文件、旧主机绝对路径和旧设备地址是记录，未全部作为运行素材收入此包。

## 从源码构建 APK

当前引导脚本支持 macOS ARM64/x64 和 Linux x64。需要 Python 3.12+、Git、CMake 3.22+，以及自行安装的 Android NDK r29；安装到手机时还需 adb。Windows、Linux ARM64 未提供当前工具链引导。

在本包根目录执行：

```bash
# 签名脚本会确认 .cache 内的调试密钥被 Git 忽略；解压后的目录需初始化仓库。
git init
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-model.txt

# 从固定 revision 下载原始模型，自动校验已固定的 SHA-256；约 731 MiB。
python package-tools/fetch_source_model.py

# 完整图准备与 QNN 图像路由兼容改写；不量化，不移动图内时序队列到 CPU。
python android/tools/prepare_model.py

# 改为自己已安装的 NDK r29 路径。
export ANDROID_NDK_HOME=/absolute/path/to/android-ndk-r29
bash android/scripts/build_apk.sh
```

SDK 35、JDK 17、Kotlin、D8、ORT 1.27.0、QNN EP 2.6.0 与 QAIRT 2.50.0 由现有脚本联网下载并校验。NDK 不会自动下载。首次构建需要较多磁盘空间供源码模型、部署模型、依赖和 APK 使用；后续复用 `.cache/`。

生成：`.cache/android-apk/OpenPilotInference-debug.apk`。编译默认使用 Kotlin，不依赖 Gradle、Compose 或协程。若已有准备好的部署模型，可将 `model.onnx` 与匹配的 `manifest.json` 放到 `.cache/android-models/cinque3/`，跳过模型下载和准备。

源码包不含原设备的调试签名密钥；新机器生成自己的密钥，因此其 APK 不能直接覆盖原密钥签名的安装。要保留原安装的数据，需要在原构建环境复用其现有私有签名缓存，不能把密钥放进源码包。

## 安装和命令行服务

```bash
adb connect PHONE_IP:WIRELESS_DEBUG_PORT
adb -s PHONE_IP:WIRELESS_DEBUG_PORT install -r .cache/android-apk/OpenPilotInference-debug.apk
adb -s PHONE_IP:WIRELESS_DEBUG_PORT shell am start -n com.example.openpilotinference.android/.MainActivity

# 可选：仅编译原生 Android 命令行服务。
bash android/scripts/build_android.sh
```

`PHONE_IP:WIRELESS_DEBUG_PORT` 使用手机开发者选项显示的当前无线调试连接地址，不是配对端口。App 打开即启动。完整使用说明见 `android/README.md`；CLI 部署见 `android/scripts/run_on_device.sh`。

## 本地客户端

`script/inference_udp_client.py` 是自包含 Python UDP 参考客户端；历史帮助中保留了 iOS 名称，线协议共用。`script/replay_opif_video.py` 和 `benchmark_opif_pipeline.py` 的 `--client` 可指向该文件。

`script/opif_overlay/viewer.py` 支持 `--transport udp` 或 `tcp`，带 D2 流水线与车道线显示。它需要自己的 openpilot/sunnypilot checkout（Parser、相机几何，读取 rlog 时还需 cereal），以及 NumPy、OpenCV、ffmpeg/ffprobe、配对视频；可选 ffplay。示例使用自己的素材与 checkout：

```bash
python script/opif_overlay/viewer.py   --openpilot /path/to/openpilot   --video-dir /path/to/paired-video   --host PHONE_IP --transport tcp --frames 600 --ffplay
```

`script/opif_overlay/start.command` 保留历史主机默认值，使用时以 `OPIF_OPENPILOT`、`OPIF_VIDEO_DIR`、`OPIF_HOST` 覆盖，或直接运行上面的 CLI。视频、日志和完整 openpilot 工程不在源码包内。

## 局部检查与已知状态

```bash
cmake -S android -B .cache/android-host-tests -DOPIF_BUILD_SERVER=OFF
cmake --build .cache/android-host-tests
ctest --test-dir .cache/android-host-tests --output-on-failure
python -m unittest discover -s android/tests -p 'test_*.py'

# 现有图表主机检查使用 macOS JDK Contents/Home 布局；Linux 不直接适用此命令。
python android/tests/check_performance_history.py
```

模型安装器 JVM 检查还需 `JSON_JAR` 指向 host org.json JAR，否则会显式 skip。离线完整模型数值对照另需 `onnxruntime`（该阶段参考版本 1.28.0），执行 `python android/tools/validate_model.py`；这是开发检查，不是 Android CPU fallback。

打包前已通过 APK 构建、JNI ABI、签名和 16 KB 对齐；局部协议、缓存、图表检查已通过。该轮 APK 已无线安装，首次 NPU 启动与 `QNN_CACHE_SAVED` 已确认。缓存命中后的启动耗时尚未确认：两次后续后台进程被手机系统结束；新图表的真机视觉与持续帧率亦未验收。历史 NPU 对 CPU 参考的数值对照仍未通过，见 `android/VALIDATION.md`；不要将全图 NPU 执行等同于精度验收。

`SOURCE_MANIFEST.json` 记录各文件 SHA-256，`MANIFEST.sha256` 可用于解压后完整性检查。本次打包只检查文件覆盖、校验和及归档完整性，没有重新执行 APK 构建或手机 E2E。
