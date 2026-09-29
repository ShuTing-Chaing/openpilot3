# Android 实现与真机验证记录

记录按阶段保留，早期“无 ADB 设备”的结论只描述当时环境。**当前修复模型已在 PLZ110 / SM8850 / Android 16 完成整图 HTP warmup 与十帧执行，provider 检查通过，但设备输出数值对照未通过。** 主机改写逐位一致、NPU 执行归属和设备数值精度分别记录，不能合并为“全部验证通过”。

## 监听选择、FPS 图表与 QNN 编译缓存（2026-09-25，已无线安装）

当前 APK 包含 UDP/TCP/同时监听选择，切换时排空请求、结束会话并保留已加载的 NPU 模型；FPS 图保存最近 10 秒，纵轴自动缩放，60 FPS 是绘制目标。统计仍低频后台计算，绘制不逐帧排序。新增私有 QNN EPContext 编译缓存，按模型、运行库、HTP 配置及设备构建身份失效；首次生成成功才原子提交，再次加载校验内容完整性。所有启动仍执行一帧真实 NPU warmup 并清空时序状态，禁止 CPU/GPU 回退。

APK 为 **922,608,817 字节**，SHA-256 `87c8b3f3cfd5ea253f4da9de9adf1a60ed24aa292440f8409ced627e2f21b6b3`；包内模型未变。Kotlin/C++、JNI 字节码、DEX、签名和 16 KB 对齐检查通过。监听/D2 回归和缓存完整性检查通过 ASan/UBSan；图表的分桶、分位数、重叠样本与不同屏幕刷新率下的节奏检查通过。

用户打开 Wi-Fi 后，通过 `192.168.0.192:40457` 无线 ADB 安装成功，正式 MainActivity 冷启动 PID 22717。真机日志确认首次 `QNN_CACHE_SAVED`，建 session/生成 context 为 **89.533 秒**，一帧真实 NPU warmup 为 **26 毫秒**；从加载到 TCP/UDP 5555 监听共 **98.592 秒**，随后既有客户端自动连接。首次成本包括编译与缓存写入，不能作为缓存命中速度。后续无线端口变为 `44431`，两次缓存冷启动进程在后台被系统结束（reason 13、subreason 2040、`o-stop(40)`），尚未取得有效缓存命中耗时；未更改系统后台策略。**缓存实际命中与收益、监听模式切换端口及新图表画面/帧率仍待确认**。未启动完整视频 E2E 或性能 A/B。历史安装、回放数据只属于各自构建，不能作为本次缓存或绘制开销的证据。详见[本轮安装与检查记录](../diagnostics/android-listen-transport-20260925/README.md)。

## SM8850 图像路由修复与真机结果（2026-09-25）

初次真机加载使用 ORT 1.27.0、QNN EP 2.6.0、QAIRT 2.50.0 和 HTP V81。QNN 拒绝了以下四个节点的 raw UINT8 输入/输出类型组合：

| 节点 | 算子 |
|---|---|
| `node_cat` | Concat |
| `node_select_1` | Gather |
| `node_select` | Gather |
| `node_cat_2` | Concat |

日志随后明确报错：部分节点被分配给默认 CPU EP，但用户已禁止 CPU fallback。因此原版本未进入服务就绪状态，也没有绕过限制使用 CPU/GPU 推理。证据位于 `.cache/android-device-diagnostics/validate-original.log`。

`prepare_model.py` 现在默认将图像复制、切片、索引、拼接路径改为内部 FP16，保留原始 UINT8 图输入与 `next_state_img_q` 输出。0–255 的每个整数都能被 FP16 精确表示，转换不改像素值或权重。第一版修复消除了上述四个拒绝节点，但设备又拒绝直接 FP16 → UINT8 Cast；最终改为图内 **FP16 → FP32 → UINT8** 输出转换。第一版修复的拒绝证据位于 `.cache/android-device-diagnostics/validate-candidate.log`。原始 UINT8 路由可通过 `--original-image-routing` 复现，仅供诊断。

当前修复产物与已完成检查：

- 模型：`.cache/android-models/cinque3/model.onnx`，764,039,767 字节；这是从 `cinque3-npu-fix/` 晋升的同一修复产物。
- 部署 SHA-256：`86890bf95af82adbcc85f20f3a60acda3bffc852224bfb00afdbb81ee2f4a677`；源 SHA 仍为 `404a18cfd86d29637d20c697dfde245bb47c666ae016730ab674c65f4d1e1aa4`。
- 完整 7 输入 / 4 输出 ABI、原始权重及图内三组队列保持不变；没有增加 CPU/GPU provider。
- 20 项 Python 工具测试通过，包含全部 256 种像素值、不同相机/历史槽位、连续跨帧状态、输出 dtype 与输入输出 ABI 检查。
- 主机 ORT 1.28.0 关闭图优化，十帧完整源模型对照通过：所有 raw outputs 与三组 next-state 均逐位一致，max abs / RMSE 均为 0。报告为同目录 `validation.json`；其中 `validation_kind=offline_cpu_reference`、`npu_validated=false`。

设备第二版候选命令行执行已结束，退出码为 0，日志出现 `NPU_WARMUP_OK`。结果分层如下：

| 验证层次 | 本次结果 |
|---|---|
| 图改写语义 | 主机十帧 raw outputs 与三组 next-state 逐位一致，通过 |
| 设备完整执行 | HTP warmup + 10 帧完成，CPU fallback 保持禁用，通过 |
| Provider 归属 | 11 个 kernel 事件（warmup + 10 帧）全部为 `QNNExecutionProvider`，后端固定 `libQnnHtp.so`；未发现 CPU/GPU kernel |
| 短诊断耗时 | 10 帧平均 24,601.3 µs；开启详细日志和 profile，不代表稳态 benchmark 或实际 UDP 吞吐 |
| NPU 数值对照 | **失败**：`atol=0.05, rtol=0.005`，17,608 / 184,520 元素超限，max abs 4.0、RMSE 0.0613425381，NaN/Inf 元素数为 0 |
| UDP / D1 修复版 APK（历史） | `adb install -r` 返回 `Success`；正式 MainActivity 启动，NPU warmup 通过并进入 UDP 5555 `listening` 状态 |

设备输入为 10 个 currentPacked6 帧，固定 desire=0、LHD、`action_t=[0.4,0.7]`，首帧 reset；参考使用主机 ORT 1.28.0、关闭图优化的原始模型。数值误差原因尚未定位，不将其归因于已证实无损的图像路由改写，也不通过放宽容差宣布通过。

本次证据均保存在 `.cache/android-device-diagnostics/`：`validate-candidate2.log`、`benchmark10-packed6.bin`、`candidate-output.f32`、`candidate-output.comparison.json` 和 `candidate-qnn-profile.json`。比较报告仅核验数值，provider 归属由独立 profile 检查确认。

该阶段的 **UDP / D1 历史 Kotlin APK** 为 921,846,961 字节，SHA-256 `d07b649ce0094c1ba8b15626ae4a1ec3305ee146543d8653e7d92d0fd4b4b601`，包内模型 SHA 与上述修复模型一致。JNI ABI、签名、16 KB 对齐和模型打包 hash 检查通过。它当时产出于 `.cache/android-apk/OpenPilotInference-debug.apk`；该路径已先后被下文 `29afb54e…13584` 及后续构建覆盖，不能用当前路径文件代替这份历史产物。

该 APK 已通过 `adb install -r` 安装，返回 `Success`；`com.example.openpilotinference.android/.MainActivity` 启动后的 PID 为 31176。2026-09-25 18:53:37.571 的 `OpenPilotNPU` 日志为：

```text
state=listening NPU warmup passed; waiting for a remote OPIF client on UDP 5555
```

手机当时的 Wi-Fi 地址为 `192.168.0.192`。这次启动检查确认正式 App 的模型/JNI/HTP 加载和 UDP listener 就绪；不替代数值精度、停止/重启及持续后台验证。后续视频链路结果单独记录如下。构建报告中的构建期字段保持原记录，不用安装成功替代数值验收结果。

## 首轮双摄视频与车道线回放（2026-09-25）

既有 overlay 客户端向上述 Android 服务发送路段 `000001d4--2648a9a404--4` 的双摄视频，使用同一路段 rlog 的 `extrinsicsCalibration` 和配对 encode frame ID。握手报告模型为 `comma big model cinque v3 / QNN HTP`，ABI 为源 SHA `404a18cf…d1e1aa4` 对应的 `op-supercombo-18452-f32-d33-s4-v1`。该轮为 **UDP / D1，未包含后续 App 预览、性能卡或 TCP / D2 更新**。这是实际视频回放，不是上述十帧离线诊断；两组耗时的采集条件不同。

| 项目 | 本轮结果 |
|---|---|
| 完成帧数 | 600 / 600，帧索引连续为 0–599，输出 shape `[600, 18452]` |
| 客户端平均吞吐 | 16.2366 FPS |
| 往返延迟 p50 / p95 | 70.8974 / 159.0250 ms |
| 服务端推理平均 / p50 / p95 | 21.50098 / 21.3865 / 22.46025 ms |
| 补传 | 116 次 |
| 有限输出元素 | 11,071,200 / 11,071,200，无 NaN/Inf |
| 左右自车道线概率均 ≥ 0.1 | 547 / 600 帧 |
| 数值精度 / 真值准确率 | 十帧 NPU 参考对照仍为失败；本轮没有真值准确率验收 |

已查看第 [0049](../diagnostics/android-video-lanes-20260925/overlay-0049.jpg)、[0249](../diagnostics/android-video-lanes-20260925/overlay-0249.jpg)、[0549](../diagnostics/android-video-lanes-20260925/overlay-0549.jpg) 帧叠加图：车道线左右顺序和道路大体对应。有限值、模型概率和少量画面观察只说明本轮数据链路与可视化结果，不能证明几何精度或替代原模型数值对照。

证据保存在 `diagnostics/android-video-lanes-20260925/`：[客户端统计](../diagnostics/android-video-lanes-20260925/summary.json)、[输出指标](../diagnostics/android-video-lanes-20260925/metrics.json)、[叠加视频](../diagnostics/android-video-lanes-20260925/lanes-h264.mp4)及各帧 JPG。输出结果 SHA-256 为 `29cf1629a830879d9d53bf4a3080d1350aa52581026a0c25ee4010831dd58460`。

App 内输入画面预览是本轮回放之后新增的验证范围。同条件下关闭与开启预览的 A/B 结果尚未取得，不能用上述单次回放推断预览对吞吐、延迟或推理耗时的影响，也不能将 16.2366 FPS 作为 TCP / D2 的实测结果。

## App 视频预览与性能统计（新版已安装，短功能检查通过）

该阶段历史统一 APK 位于 `.cache/android-apk/OpenPilotInference-debug.apk`，**922,109,105 字节**，SHA-256 为 `29afb54ec7acabe03a808f810745586205c2ba450d1d0663ff6eabdad9d13584`。包内模型 SHA-256 仍为 `86890bf95af82adbcc85f20f3a60acda3bffc852224bfb00afdbb81ee2f4a677`。本次构建包含以下预览、性能统计及 TCP / UDP / D2 更新，已完成安装和合并短功能检查；旧 D1 的安装或回放结果仍单独保留。

Kotlin 界面已加入实际双摄模型输入预览，每路 512 × 256、左右合成 1024 × 256；左窄摄、右广摄，显示最新请求 ID 与实际预览 FPS。默认开启，开关偏好持久化，也支持 `MainActivity` intent 的布尔 extra `preview_enabled`，切换时不重启已经运行的模型。原生取帧及界面轮询上限均为 10 Hz；关闭或 Activity 不可见时停用原生预览，离开页面、开关变化与会话切换会使旧 generation 失效。

预览采用独立后台 worker、单个最新输入槽、单个待显示帧和两张复用 Bitmap；界面持有的 Bitmap 不会同时交给 worker 修改。UI 按固定周期取图，不为每个输入帧新增主线程消息。转换失败后停用原生预览复制，旧 owner 或旧 generation 的失败不能关闭新开启的预览；控制器不持有 Activity 引用。

性能统计使用最近最多 256 个成功推理帧的完整耗时及完成时间数组，JNI 每 500 ms 最多推送一次；后台 worker 计算 p50 / p99、均值、最近值及曲线，主线程最多 2 Hz 刷新。完成时间为 `CLOCK_MONOTONIC`，空闲判定使用同源的 `System.nanoTime()`；超过 1 秒没有新完成帧时 FPS 归零。客户端 STOP / 回到 listening 后保留最后窗口，新 START 清空旧窗口。预览关闭时性能卡仍正常更新。没有加入 Compose、协程或图表库，模型 NPU-only 限制保持不变。

| 检查 | 本次状态 |
|---|---|
| Kotlin 单独编译 | 使用固定 Kotlin 编译器、Android 35 SDK 编译全部应用 Kotlin 源码通过 |
| 统一 APK 构建 | 构建通过；六个静态 native 方法、四个 callback 的字节码校验通过，DEX 无 warning，签名与 16 KB 对齐通过；包内模型 SHA 不变 |
| 最终 D2 协议 | 合并后的 ASan/UBSan 检查通过，覆盖 UDP / TCP、排队、RESET、失败、排空及 STOP |
| 预览转换 | ASan/UBSan 检查通过 |
| 预览缓冲与所有权 | 主机夹具验证 UI 占用显示帧和待显示帧时不继续转换、只保留最新请求、Bitmap 数量不超过 2，通过 |
| 生命周期与失败路径 | 在途旧 generation 丢弃、旧 Activity owner 不能关闭新 owner、转换失败停用原生复制，通过 |
| 统计计算 | p50 / p99 / 均值 / 最近值 / FPS、STOP 保留窗口、新 run 清空及旧 run 样本拒绝，通过 |
| 新版 APK 真机安装与短视频 UI | `adb install -r` 返回 `Success`，正式 Activity 启动、NPU warmup 和 TCP / UDP 5555 监听通过；双摄预览与性能卡截图检查通过 |
| 预览开关 A/B 与持续运行 | **未运行**；按用户要求优先实现并安装，不能声称零性能影响 |

主机夹具位于 `.cache/android-kotlin-preview-hosttest/`，使用测试专用的 Bitmap / JNI 替身检查调度、所有权和数学逻辑，不运行设备转换或 NPU。本次协议更新的容量为 D2，即 1 帧执行、1 帧排队，TCP 和 UDP 共用服务；这些新增功能没有沿用上一节 UDP / D1 的 600 帧数据作为验收证据。

新版正式 MainActivity PID 为 **21852**。2026-09-25 **19:25:06.941** 的 `OpenPilotNPU` 日志报告 `state=listening`、NPU warmup 通过并监听 TCP / UDP 5555；见[应用日志](../diagnostics/android-preview-depth2-20260925/app.log)。本次合并短视频检查结果如下：

| 项目 | [TCP 摘要](../diagnostics/android-preview-depth2-20260925/tcp/summary.json) | [UDP 摘要](../diagnostics/android-preview-depth2-20260925/udp/summary.json) |
|---|---:|---:|
| 完成帧数 | 200 / 200 | 80 / 80 |
| READY 在途容量 | depth=2 | depth=2 |
| 平均完成帧率 | 17.0263 Hz | 17.9884 Hz |
| 服务端推理均值 | 21.61514 ms | 21.63785 ms |
| 服务端推理 p50 / p99 | 21.565 / 22.84013 ms | 21.555 / 22.86407 ms |
| 往返延迟 p50 / p99 | 62.93398 / 248.5669 ms | 65.30175 / 329.2268 ms |
| 输出有限值检查 | 全部有限 | 全部有限 |

两次回放前 80 帧 raw outputs **逐位一致，max abs=0**，见[输出检查](../diagnostics/android-preview-depth2-20260925/output-check.json)。这确认本次 TCP / UDP 相同输入段的输出一致性，**不代表输出通过原模型 CPU 参考的数值验收**；此前该数值对照失败的结论保留。两次回放帧数不同，以上数据仅记录短功能运行，不能作为 TCP / UDP 的公平性能比较，也不是预览开关 A/B 测试。

已检查[真机预览截图](../diagnostics/android-preview-depth2-20260925/app-live-preview.png)：左右双摄模型输入可见，最新请求为 101，实际预览 5.7 fps（上限 10），性能卡显示 p50 21.6 / p99 22.7 ms、完成 18 FPS，并有推理耗时和完成帧率两条曲线。截图是运行中某一时刻的滚动窗口，其数值不等于上述整段摘要。TCP / UDP 的摘要、客户端日志和应用截图保存在 [本次设备诊断目录](../diagnostics/android-preview-depth2-20260925/)。

`.cache/android-apk/build-report.json` 保留构建期的 `device_run_verified` 值；未因这次安装成功而修改。新版[安装记录](../diagnostics/android-preview-depth2-20260925/installation.json)、[构建记录](../diagnostics/android-preview-depth2-20260925/build.json)与短功能结果单独记录在上述设备诊断中，亦不改变先前 NPU 数值验收未通过的结论。按用户要求先完成功能安装，没有运行预览开关性能矩阵或长时稳定性测试，不能声称预览零开销。

Android D2 的协议语义为：窗口最多有 1 个 running 请求和 1 个已完整接收、按序排队的请求，NPU 始终串行。`MESSAGE_ACCEPTED` 确认 ID 已接纳进入有界执行窗口并被消费，不能作为该帧已开始 NPU 执行的证据。`RESET_TEMPORAL` 仅在空窗口接纳，非空窗口的 RESET 或满窗口的第三帧均返回 error code 9，且不消费 ID。执行失败时，失败帧及后续被取消的已接纳排队帧各返回 terminal error 11；这些 ID 已消费，客户端下一请求须使用下一个未消费 ID 并设置 `RESET_TEMPORAL`。本段是新增协议行为说明，不新增真机测试通过结论。

## Kotlin 迁移验证（2026-09-25，真机诊断前）

- Activity、前台 Service、状态对象、模型安装器及 JNI 声明共 5 个应用源码文件已迁移为 Kotlin，原 Java 应用源码已删除；继续使用原生 View。
- Kotlin 全源编译通过，并检查编译后字节码：四个 native 方法仍为静态方法，名称、参数、返回值与 C++ JNI 一致；两个回调方法描述符匹配。
- Kotlin 模型安装器通过原有 47 项主机断言，覆盖文件复制、hash 校验、缓存复用、失败、取消和重试。
- 使用 Kotlin 2.4.20 / D8 9.1.43 构建 APK 成功，DEX 编译无告警；APK 签名、16 KB ZIP 对齐和包内完整模型 SHA-256 检查通过，沿用已有调试签名身份。
- 代码审阅覆盖自动启动、停止/重试、旋转与进程恢复、前台通知和旧 Service 的延迟回调。未新增 Compose、协程或反射库。
- 本次没有执行真机 UI、后台服务或 NPU 推理验证；此前模型数值与协议检查的适用范围保持不变。

该阶段 Kotlin APK：`.cache/android-apk/OpenPilotInference-debug.apk`，921,838,769 字节（约 879 MiB），SHA-256 为 `162ef58542172635922d2d58761c12dc8b10dad3bc526265618d0120965ba80e`。这是图像路由修复前的历史产物，后续构建会复用同一路径；实际版本以 `.cache/android-apk/build-report.json` 为准。JNI 字节码检查：`.cache/android-apk/jni-abi.txt`。

## 初版 Java APK 验证（2026-09-25，应用源码现已迁移为 Kotlin）

- 新增 Java Activity、前台 Service 和 C++ JNI，打开应用自动准备模型并启动原有 UDP 服务。
- Android 35 / Java 8、ARM64 JNI、资源和 DEX 编译通过。
- `libopif_jni.so` 的四个 JNI 导出与 Java 声明匹配；ELF LOAD 段 16 KB 对齐。
- APK 签名、ZIP 16 KB 对齐、Launcher/前台服务 manifest 和 APK 内完整模型 SHA-256 检查通过；包含 9 个 JNI/ORT/HTP 库，无 QNN CPU/GPU 后端。
- 模型安装器 47 项主机断言通过，覆盖首次安装、缓存复用、不完整/错误模型、缺失 asset、空间不足、取消和中断恢复。这些测试使用小型假存储输入，验证真实文件复制和 SHA-256，不运行模拟 NPU。
- 审阅并修复旧 Service 回调覆盖新实例、重复启动改变通知状态，以及系统回收进程后 Activity 恢复未自动启动的问题。
- 本次 ADB 列表仍为空：未安装 APK，未做真机 UI、JNI、NPU 或后台运行验证。

初版 APK 包含完整模型，约 878 MiB；同路径产物现已更新为上述 Kotlin 版本。界面与状态逻辑仅完成编译和代码检查，没有将设计稿或主机测试作为 Android 截图/真机结果。

## 初次实现已完成的主机检查（图像路由修复前）

| 检查 | 结果 |
|---|---|
| Android ARM64 构建 | NDK r29 / Clang 21 / API 31 编译链接成功；生成 `/system/bin/linker64` 加载的 AArch64 ELF |
| 原生协议测试 | C++17、`-Wall -Wextra -Werror`；ASan/UBSan UDP 集成通过 |
| 既有客户端兼容 | 实际 UDP READY/RESULT 通过 `opif_overlay/opif/wire.py` 与 `opif_native_replay/modeld_opif/wire.py` 的解码 |
| Python 工具测试 | 17 项通过，包含索引等价改写、hash/ABI 拒绝、profile 禁止回退、benchmark 对照输入约束 |
| ONNX 导出 | 完整模型通过 checker，保留 7 输入 / 4 输出、原始精度和三组时序队列 |
| 十帧模型对照 | 主机 ORT 1.28.0，关闭图优化，与未改写源模型输出和所有 next-state 逐位一致，max abs / RMSE 均为 0 |
| 主机优化差异诊断 | 最大绝对误差 0.125，最大 RMSE 0.00268266；通过既有转换检查的 `atol=0.05, rtol=0.005`，属于主机 FP16 运算优化差异 |

协议测试覆盖会话 owner、pending PING、D1 背压、序号连续性、CRC、输入/输出补片、冲突分片、六项重组上限、32 项 terminal 缓存、失败后 RESET、MTU 512、5 秒租约和推理中 STOP 后排空。测试假运行时只编入测试程序。

Android 使用官方 Maven ORT 1.27.0、QNN EP 2.6.0、QAIRT 2.50.0。编译主机为 macOS ARM64，主机 ORT 对照与 Android ORT/QNN 是不同执行环境。

## 初次实现产物（图像路由修复前）

- 可执行文件：`.cache/android-build/opif-server`。
- 准备后的完整模型：当时为 `.cache/android-models/cinque3/model.onnx`，现已归档到 `.cache/android-models/cinque3-before-npu-fix/model.onnx`。
- 源模型 SHA-256：`404a18cfd86d29637d20c697dfde245bb47c666ae016730ab674c65f4d1e1aa4`。
- 部署模型 SHA-256：`372714acce2ed5efee12c55a9667bde541b9ffb2f1677bd2042c73bbc3e965d3`。
- 模型 manifest 和逐帧验证报告：同目录 `manifest.json`、`validation.json`。
- 运行库固定版本及文件 hash：`.cache/android-deps/runtime-manifest.json`。

## 当前待完成的真机验证

1. 定位并解决当前 NPU 输出超出既有容差的问题，再完成多帧输入、desire 变化和 RESET 后的设备数值对照。
2. 修复版 APK 的停止/重启及持续后台前台服务行为；自动启动和监听就绪已确认。
3. 包含预览、性能卡和 TCP / UDP / D2 的新版 APK 已安装并通过合并短视频 UI 检查；完整生命周期、预览开关 A/B 矩阵及长时稳定性尚未验证，本次按用户要求优先完成功能安装。
4. 首轮既有客户端 UDP / D1 的 600 帧视频/车道线回放已完成；尚未验证真值准确率、实际 comma 设备链路及持续运行下的温度、内存和稳定性，不能据此推断新版吞吐或预览开销。

目前已证实这次命令行运行使用完整 QNN HTP 图，但尚未通过 NPU 数值验收，也没有 20 Hz 或其他持续帧率承诺。网络、调度和缓冲区处理使用 CPU；代码禁止的是模型算子回退到 CPU/GPU。
