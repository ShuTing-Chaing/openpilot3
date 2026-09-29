> 2026-09-28 分支实现：**OPIF 0.1.4 / code 5**，SP同帧路径、后台预览、真实队列计时与显式compact结果协商；[构建与E2E](../docs/PHONE_BUILD_AND_REPLAY.md)。设备验证由主线程执行。

> 2026-09-28 先前模型优化版本：**OPIF 0.1.3 / code 4**。由用户提供的 `android-model-patch-kit` 从 SHA 钉扎的 prepared 基线依次执行 `last-query additive-mask pixel-qdq`，部署图 SHA 为 `8cf7714f5d4f2601f273a7f4b7eddba25c9c6dbb8b38962c7600cda1fbd85961`。
>
> 同一手机410帧四输出逐字节一致；单模型 A/B/A 中候选 p50 16.36ms，prepared 基线22.36–23.09ms。安装后200帧20Hz USB App回放通过（实际App推理p50 21.46ms，C3接收帧龄p50 74.99ms）。另通过5分钟真实双摄shadow台架：6,018条modelV2全部有效、0相机ID缺口，末次状态5,987个手机结果。离线模型计时、实际App链路和道路验收须分开。
>
> 复现命令、模型/运行库审计、安装与回滚证据见 [本次报告](../diagnostics/model-patch-kit-20260928/REPORT.md) 和 [复跑说明](../diagnostics/model-patch-kit-20260928/REPRODUCE.md)。补丁原文件保存在 `tools/model_patch_kit/`，请显式传入输入/输出路径。C3端接口和200ms截止时间保持原值。

# Android OPIF inference server — Cinque v3 / SM8850

2026-09-28 源码更新：`tools/prepare_model.py` 默认把8层常量 attention mask 的 `Where(Not(mask), -Inf, scores)` 改为共享 FP16 Add bias。此改写发生在导出阶段，保留原有权重、输入输出和状态逻辑，不增加在线认证或逐帧对比。用 `--original-attention-mask` 可重现旧 OPIF 图作同机 A/B。离线 E2E、IEEE754 边界与复跑方法见 [ATTENTION_MASK_E2E.md](ATTENTION_MASK_E2E.md)；本机实测结果见根目录 `diagnostics/opif-attention-mask-20260928/`，不能直接采用截图的17.9ms作为本机成绩。

0.1.2 构建报告会记录具体模型 SHA 和 attention mask 模式。导出、构建成功与手机安装／实际运行是不同状态，以各自收据为准。下文为此前版本的历史记录。

Android ARM64 推理服务，提供打开即启动的 APK 界面，也保留 adb 命令行版本。兼容当前 comma 客户端的 OPIF v1 UDP 协议，本次更新增加同端口 TCP 传输，目标是 Snapdragon **8 Elite Gen 5 / SM8850 / HTP V81**。本目录独立于 iOS/macOS 工程，不改动其模型和构建缓存。

模型计算强制使用 Qualcomm QNN HTP。CPU 仍负责网络、协议校验、desire enum 上升沿、内存分配/搬运和 NPU 调度；这不可能是整个 Android 进程零 CPU 使用。

**修复模型已在 PLZ110 / SM8850 / Android 16 完成整图 HTP warmup 和十帧推理，但 NPU 数值验收未通过。** 本次 profile 的 11 个 kernel 事件全部属于 QNN，运行时后端固定为 `libQnnHtp.so`。设备输出对原模型 CPU 参考，在 `atol=0.05, rtol=0.005` 下有 17,608 / 184,520 个元素超限，最大绝对误差 4.0、RMSE 0.0613425，无 NaN/Inf。不能将“全图能在 NPU 执行”视作“精度已验证”。

初次真机加载曾因图像队列中两个 raw UINT8 Concat、两个 raw UINT8 Gather 不受当前 QNN HTP 支持而失败。现将图像复制/索引路径改为内部 FP16，队列输出通过 FP16 → FP32 → UINT8 保留原始 ABI；权重和像素值不变。修复已通过 20 项工具测试及主机十帧全输出、三组状态逐位一致对照；上述 NPU 精度差异仍未解决。十帧设备诊断的平均推理时间为 24.6013 ms，开启了详细日志和 profile，尚不能代表持续运行或实际 UDP 吞吐。详见 [验证记录](VALIDATION.md)。

## APK 界面：打开即启动

安装包位于 [`.cache/android-apk/OpenPilotInference-debug.apk`](../.cache/android-apk/OpenPilotInference-debug.apk)，应用名称 **OPIF Server**。APK 约 879 MiB，包含完整模型和 HTP 运行库，无需另行推送模型。首次打开会在应用私有目录解包约 729 MiB 模型并校验 SHA-256；后续启动复用已验证文件。

首个包含预览、性能卡和 TCP / UDP / D2 的历史统一构建为 **922,109,105 字节**，APK SHA-256 为 `29afb54ec7acabe03a808f810745586205c2ba450d1d0663ff6eabdad9d13584`；包内模型 SHA-256 为 `86890bf95af82adbcc85f20f3a60acda3bffc852224bfb00afdbb81ee2f4a677`。后续监听选项与图表更新记录见下方及 `.cache/android-apk/build-report.json`。

界面使用黑色背景，显示准备进度、NPU 加载/等待连接状态、手机 IPv4 地址和 TCP / UDP 5555、最近推理耗时和累计帧数，提供复制地址、停止和重新启动按钮。加载或运行库错误会直接显示在界面，只有 NPU warmup 和端口绑定都成功后才显示服务就绪。

连接卡提供 **UDP / TCP / 同时** 三个监听选项，默认为同时监听，选择自动保存。只创建所选协议的 5555 端口；切换会结束当前客户端会话，等待正在执行的推理结束，再关闭旧监听并绑定新协议。NPU 模型保持加载，客户端需重新连接。快速来回选择允许合并为最终模式，停止请求始终优先。也可通过 Activity intent 的 `--es listen_transport udp`、`tcp` 或 `both` 选择。

FPS 图改为最近 **10 秒**的柱状图，纵轴自动缩放；**60 FPS 是绘制目标，不是纵轴范围，也不是推理帧率**。统计与分桶仍在后台低频完成，界面只平滑滚动已有柱状数据；没有开头人为补零的折线。具体构建及检查结果见 [监听与图表更新记录](../diagnostics/android-listen-transport-20260925/README.md)。

APK 现在启用 [QNN EPContext 编译缓存](https://onnxruntime.ai/docs/execution-providers/QNN-ExecutionProvider.html#qnn-context-binary-cache-feature)：首次从 ONNX 编译完整图，验证输入输出并完成一次真实 NPU warmup 后，将编译结果原子写入应用私有缓存；下次启动校验并加载缓存，省去重复编译。模型、实际 ORT/QNN 运行库、HTP 配置或系统/驱动指纹变化会失效重建；Android 清理应用缓存也会触发重建。缓存不保存模型时序状态，也不能省去 NPU 上下文加载和一次真实预热。缓存损坏或保存失败不启用 CPU/GPU，继续按严格 NPU 路径重编译或运行。`OPIF-QNN` 日志分别记录 `QNN_CACHE_*`、`QNN_SESSION_READY create_ms` 与 `NPU_WARMUP_OK warmup_ms`；本轮新版已通过无线 ADB 安装，真机首次编译/序列化 89.533 秒、真实预热 26 毫秒，成功保存缓存并开始监听；后续冷启动命中和耗时尚待确认，详见本轮验证记录。

本次新增的视频预览显示客户端实际提交的双摄模型输入：左侧窄摄、右侧广摄，各 **512 × 256**，并排为 **1024 × 256**。预览默认开启，状态卡下方的开关会保存偏好；画面标注最新请求 ID 和实际预览帧率，原生取帧及界面刷新均以 **10 Hz** 为上限。关闭预览或 Activity 不可见时停用原生预览复制，模型服务继续运行；重新打开或切换客户端会话时丢弃旧帧。

相邻性能卡显示最近最多 **256 个成功推理帧**的 p50 / p99、平均和最近耗时，以及按完成时间计算的 FPS。原生每 0.5 秒最多推送一次完整样本窗口，后台排序和统计最多 **2 Hz** 更新；FPS 柱按 0.5 秒分桶增量去重保存最近 10 秒，不受单次 256 帧窗口限制。图表以 60 FPS 为目标滚动已有数据，柱高不插值、不填首帧零值；上图为推理耗时，下图为完成帧率。超过 1 秒没有完成帧时显示空闲、FPS 归零；客户端停止后保留最后统计窗口，下次 START 清空，柱子退出时间窗后停止动画。

预览转换在独立后台 worker 执行，使用一个最新输入槽、一个待显示帧和两张复用 Bitmap；界面忙时覆盖待处理输入，不累积转换任务或逐帧 UI 消息。性能计算也在后台、采用有界样本窗口，不依赖图表库；关闭预览时性能统计继续运行。上述显示工作使用 CPU，模型仍强制整图 QNN HTP，禁止 CPU/GPU 算子回退。

**此前预览、性能卡、TCP / UDP 5555 及 D2（1 帧执行、1 帧排队）已构建并安装到 PLZ110，短功能检查通过。** `adb install -r` 返回 `Success`；MainActivity PID 为 21852，2026-09-25 19:25:06.941 日志确认 NPU warmup 通过并监听 TCP / UDP 5555。六个静态 native 方法与四个 callback 的字节码校验、无 warning 的 DEX 编译、签名和 16 KB 对齐检查通过；最终 D2 协议及预览转换的 ASan/UBSan 检查通过。

新版完成 TCP **200 / 200 帧**和 UDP **80 / 80 帧**短视频回放，两次握手均报告 depth=2，全部输出为有限值；两次回放的前 80 帧 raw outputs 逐位一致、max abs=0。这验证了本次两种传输的输出一致性，不代表原模型数值验收通过。已检查[真机截图](../diagnostics/android-preview-depth2-20260925/app-live-preview.png)：双摄画面、请求 101、预览 5.7 fps、p50 21.6 / p99 22.7 ms、完成 18 FPS 和两条曲线均可见。详细短回放指标见 [验证记录](VALIDATION.md)。两种传输的测试帧数不同，不能据此公平比较性能；按用户要求优先完成功能安装，没有运行预览开关 A/B 矩阵，也未证明预览零开销。

此前 **UDP / D1 修复版 APK** 已在 PLZ110 真机安装成功并打开正式应用。2026-09-25 18:53:37.571，`OpenPilotNPU` 日志报告 `state=listening`、NPU warmup 通过并等待 UDP 5555 客户端；当时手机 Wi-Fi 地址为 `192.168.0.192`。这确认了该历史版本的模型、JNI、HTP 加载和端口就绪；上面的 NPU 数值验收失败结论仍然有效。

此前既有 overlay 客户端已完成 **600 / 600 帧**双摄视频回放，使用同一路段 rlog 的 `extrinsicsCalibration` 和配对 encode frame ID。该轮采用 **UDP / D1，未包含本次 App 预览和性能卡**，实际平均吞吐为 **16.24 FPS**，往返延迟 p50 / p95 为 70.90 / 159.02 ms，服务端推理平均耗时 21.50 ms；发生 116 次补传。11,071,200 个输出元素均为有限值，547 帧的左右自车道线概率均至少为 0.1。抽查叠加画面的车道线左右顺序和道路大体对应，**没有通过真值准确率验收，也不改变十帧 NPU 数值对照失败的结论**。见[回放指标](../diagnostics/android-video-lanes-20260925/metrics.json)、[客户端统计](../diagnostics/android-video-lanes-20260925/summary.json)与[叠加视频](../diagnostics/android-video-lanes-20260925/lanes-h264.mp4)。不能将这组旧数据作为 D2、TCP 或开启预览后的性能结果。

打开应用自动启动；切换到后台后由前台服务继续运行，通知栏提供停止按钮。首次通知权限提示不影响服务启动。停止时会取消模型解包或等待正在执行的 NPU 任务结束，完成释放后可重新启动。系统回收进程后，下次打开应用会重新启动服务。

```bash
# 重新构建完整 APK；SDK/JDK/Kotlin 编译器自动缓存，使用已有 NDK 和准备后的模型
android/scripts/build_apk.sh

# 有连接的 Android 手机时安装并打开（也可以直接把 APK 传到手机安装）
adb install -r .cache/android-apk/OpenPilotInference-debug.apk
adb shell am start -n com.example.openpilotinference.android/.MainActivity

# 同一 APK 切换并保存预览偏好；已运行的模型无需重启
adb shell am start -n com.example.openpilotinference.android/.MainActivity --ez preview_enabled false
adb shell am start -n com.example.openpilotinference.android/.MainActivity --ez preview_enabled true
```

APK 为本地调试签名，构建重复使用 `.cache/android-apk-tools/` 中的密钥，不会更换已有身份。构建脚本完成 Kotlin/JNI/资源编译、JNI 字节码签名核验、模型打包 hash 检查、签名检查和 16 KB ZIP 对齐检查。详细产物记录在 `.cache/android-apk/build-report.json`。

APK 构建固定使用 Kotlin 2.4.20、D8 9.1.43、JDK 17 和 Android SDK 35。编译器和 D8 仅用于主机构建，不打入 APK。

界面、前台服务、状态管理、模型安装器和 JNI 声明全部使用 Kotlin，采用 Android 原生 View；仅引入 Kotlin 标准库，不依赖 Compose、协程或反射库。C++ 推理核心通过 JNI 复用，模型仍强制 QNN HTP，禁止 CPU/GPU 算子回退。APK 的模型和运行库来自与命令行版本相同的固定版本。新版安装、预览、性能卡及 TCP / UDP / D2 短回放已确认；持续后台与完整生命周期行为尚待真机验证，APK 内实际模型版本以构建报告的 hash 为准。

## 运行约束

- 完整 Cinque v3 图：7 个输入、4 个输出；图像队列、desire pooling、feature 采样/队列更新保留在模型内。CPU 只交换两组 state buffer，不重复推进队列。
- 保留 FP16 网络及原始 uint8/FP32 输入输出，不自动量化。源模型 SHA 固定为 `404a18cfd86d29637d20c697dfde245bb47c666ae016730ab674c65f4d1e1aa4`。
- 图像路由修复仅对 0–255 整数像素作无损类型转换；图像队列更新仍在模型图内。当前修复模型 SHA-256 为 `86890bf95af82adbcc85f20f3a60acda3bffc852224bfb00afdbb81ee2f4a677`。
- 仅注册 QNN 插件并选择 NPU，后端限定 `libQnnHtp.so`，设置 `session.disable_cpu_ep_fallback=1` 和 `offload_graph_io_quantization=0`。没有 CPU/GPU 模型路径或失败后重试其他 provider 的代码。
- 启动先编译/加载完整图，校验模型身份与每个输入输出的 shape/dtype，完成一次 NPU warmup，再开放网络 listener。warmup 状态会清零。
- 当前已部署版使用 TCP / UDP IPv4 5555，共用会话和模型；在途容量 D2 为 1 帧执行、1 帧排队，按顺序推进时序状态，不并行运行两个模型任务。此前完成 600 帧回放的版本为 UDP / D1。
- 只支持 `currentPacked6`、FP32 输出，其他输入/编码在握手时明确拒绝。输出 ABI 为 `18452-f32-d33-s4`（这里 `f32` 表示 32 个 feature 采样点）。
- 提供发现、单 owner、5 秒租约、CRC32C、分片补传、32 项结果缓存、幂等重发和失败后强制 temporal reset。不会打开相机、建立车辆连接或发送车辆控制。

Android D2 的窗口最多包含 **1 个 running 请求和 1 个已完整接收、按序排队的请求**，NPU 始终串行执行。`MESSAGE_ACCEPTED` 表示请求 ID 已接纳进入这个有界窗口、该 ID 已被消费；它不证明该帧已开始 NPU 执行。

- `RESET_TEMPORAL` 仅在执行窗口为空时接纳；窗口非空则返回 error code 9，不消费该 ID。
- 窗口已满时，第三帧返回 error code 9，不消费该 ID，客户端可用同一 ID 重试。
- 执行失败会取消后续已接纳的排队帧；失败帧和被取消帧各返回 terminal error 11。已接纳的 ID 不会退回，下一请求须使用下一个未消费 ID 并设置 `RESET_TEMPORAL`。

## 准备与构建

从仓库当前目录 `OpenPilotInference/` 执行。需要 Python/ONNX、CMake、Android NDK r29、adb。运行时下载来自官方 Maven Central，固定 ORT **1.27.0**、QNN EP **2.6.0**、QAIRT **2.50.0**，下载脚本校验包 SHA-256。

```bash
# 使用当前仓库已有的 ONNX 环境；默认读取 .cache/cinque3/ 原始模型
../.venv/bin/python android/tools/prepare_model.py

# 缓存官方运行库和头文件（不包含模型和 NDK）
python3 android/scripts/fetch_runtime.py

# 已安装的 NDK；如已在默认 .cache/android-deps/android-ndk-r29，可省略环境变量
ANDROID_NDK_HOME=/path/to/android-ndk-r29 android/scripts/build_android.sh
```

构建产物：`.cache/android-build/opif-server`。修复模型为默认产物 `.cache/android-models/cinque3/model.onnx` 和 `manifest.json`；修复前的导出归档于 `.cache/android-models/cinque3-before-npu-fix/`。下载依赖：`.cache/android-deps/`。所有大文件留在忽略的缓存中，重复构建使用同一目录。

模型准备内联源图中的 tinygrad Identity 函数、规范化常量负索引、等价改写一处一维索引 GatherND，并删除不需要的生产者注释。现在默认将图像队列和图像拼接的内部路由改为 FP16；输入保留 UINT8，外部 `next_state_img_q` 通过 FP16 → FP32 → UINT8 恢复原类型，网络入口已有的 UINT8 → FP16 Cast 改为 Identity。完整 ABI、原始权重和队列语义保留，像素不做归一化或量化；manifest 记录具体改写和部署文件 hash。`--original-image-routing` 仅用于诊断复现已知的 raw UINT8 不支持问题。导出完成不代表设备数值验收通过。

## 真机启动与验证

手机开启 USB 调试并授权当前 Mac。先验证全图加载和运行；多台设备用 `--serial SERIAL`。

```bash
android/scripts/run_on_device.sh \
  --model .cache/android-models/cinque3/model.onnx \
  --validate-only --profile

# 验证成功后启动服务；保持这个 adb shell 会话运行
android/scripts/run_on_device.sh \
  --model .cache/android-models/cinque3/model.onnx
```

脚本核对 `ro.soc.model` 和模型 manifest，再用 `adb push --sync` 部署到 `/data/local/tmp/opif`；设置 `LD_LIBRARY_PATH`、`ADSP_LIBRARY_PATH`，仅携带 V81 HTP 相关运行库。成功日志先出现 `NPU_WARMUP_OK`，服务模式随后出现 `READY OPIF UDP 5555`。客户端连手机实际 USB 网络/Wi-Fi 地址的 UDP 5555；`adb forward` 的 TCP 转发不能代替此 UDP 链路。

如果出现未支持算子、HTP 库不匹配、FastRPC/设备权限、图编译内存不足等错误，程序直接退出。应根据 QNN 日志修复/等价重写图，并再次做数值验证，不能打开 CPU fallback 来掩盖问题。上述命令行版本默认每次从 ONNX 编译；APK 已启用自身生成、身份和完整性校验后的私有 EPContext 缓存，不接受任意外部 context 文件。

基准运行独立于网络服务，输入文件为连续的 `393216` 字节两路 currentPacked6 帧，文件耗尽后循环。固定 desire=0、LHD、action_t=[0.4,0.7]；首帧 reset，之后保留时序。

```bash
android/scripts/run_on_device.sh \
  --model .cache/android-models/cinque3/model.onnx \
  --benchmark 120 --benchmark-input /path/to/packed6.bin \
  --benchmark-output outputs.f32 --profile

adb pull /data/local/tmp/opif/profiles .cache/android-profiles
adb pull /data/local/tmp/opif/outputs.f32 .cache/android-outputs.f32
python3 android/tools/verify_profile.py .cache/android-profiles/qnn_YYYY-MM-DD_HH-MM-SS.json
```

profile 文件名以退出日志 `PROFILE ...` 为准。检查器要求存在 QNN kernel 事件，并拒绝 CPU/GPU、无法归属的 kernel 以及空 trace。ORT profile 证明 provider 分配；结合只允许 HTP 的运行时设置核验 NPU 路径。耗时应在实际输入、稳态温度和持续运行中测量，不能由芯片 TOPS 推算。

## 本机检查

主机协议测试使用测试专用的假运行时，不是生产推理后端。

```bash
cmake -S android -B .cache/android-host-tests -DOPIF_BUILD_SERVER=OFF
cmake --build .cache/android-host-tests
ctest --test-dir .cache/android-host-tests --output-on-failure
../.venv/bin/python -m unittest discover -s android/tests -p 'test_*.py'

# 离线 CPU 参考对照，仅用于开发验证，不是 Android 推理回退
../.venv/bin/python android/tools/validate_model.py

# 对比从手机取回的 benchmark 输出；容差需显式设定
../.venv/bin/python android/tools/compare_benchmark.py \
  --input /path/to/packed6.bin --output .cache/android-outputs.f32 \
  --atol 0.05 --rtol 0.005
```

已完成 Android ARM64 交叉编译、本机协议集成测试（含 ASan/UBSan），以及实际 UDP 回复与两个现有 Python 客户端解析器的兼容性检查。修复模型在主机关闭图优化的十帧对照中输出与三组状态全部逐位一致。早期导出的主机 FP16 图优化检查曾观察到舍入差异，不能把离线逐位一致结论外推到 QNN。上面数值容差沿用仓库转换检查，仅作初步对照，不代表 NPU 精度验收；比较工具按 head 报告误差，profile 检查另行完成。详见 [验证记录](VALIDATION.md)。

## 官方依据

[QAIRT 芯片支持表](https://docs.qualcomm.com/nav/home/QNN_general_overview.html?product=924033590759186372) 将 SM8850 列为 SoC 87 / V81；不要使用 SM8750 的配置。[Qualcomm 维护的 QNN 插件文档](https://github.com/onnxruntime/onnxruntime-qnn/blob/main/docs/execution_providers/QNN-ExecutionProvider.md) 说明 Android 分发、HTP 浮点执行和 fallback 选项；芯片支持 FP16不等于任意 ONNX 算子和 shape 都支持。

完整线协议见 [INFERENCE_SERVER_PROTOCOL.md](../INFERENCE_SERVER_PROTOCOL.md)，模型输入输出与跨帧语义见 [CINQUE3_MODEL_ABI.md](../CINQUE3_MODEL_ABI.md)。
