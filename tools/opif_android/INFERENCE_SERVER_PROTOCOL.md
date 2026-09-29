# iPhone 远程推理 UDP 协议（OPIF v1）

本文档描述当前 `InferenceUDPServer.swift` 已实现的线协议，以及 comma/openpilot
`modeld` 接入时必须遵守的时序。代码是最终事实来源；本文不包含尚未实现的
HMAC、FEC、压缩或后台保活设计。

当前工作区核对（2026-09-19）：BigModel 已使用 `18452` 元素的 spatial 输出，
profile 为 `f32-d33-s4`。结果头的 `raw_output_layout` 尚未新增 spatial 枚举：
服务端仍按 `output.count == 2580 ? 1 : 0` 编码，因此 `18452` 当前也会发 `0`。
客户端必须用 READY 的完整 ABI、source SHA 和元素数选择对应输出 slices，不能仅凭
layout byte 推断为 legacy。仓库上一级 `script/inference_udp_client.py` 可参考传输实现，
但其 READY profile 白名单和 RESULT layout 校验尚未适配此 spatial profile，不能直接
用它验证当前 BigModel。下文第 15 节是接入伪代码，不是可直接运行的完整客户端。

## 1. 工作方式

Infer 菜单的“暂停 ApplePilot，等待远端连接”会关闭本地相机、推理、DM、GPS 与车辆控制，
保留 UDP listener，不建立 mock session，也不为待机主动加载模型。此模式下远端 STOP 或
租约过期后继续暂停等待，只有“恢复 ApplePilot”会恢复本地服务。App 仍需保持前台；
暂停不是 iOS 后台保活。远端推理页以最高 2 fps 显示收到的 img / big_img 当前输入，
paired12 选择各图的 current 半部；预览后台生成，不改变推理 tensor 或线协议。

- iOS App 启动后即在 UDP `5555` 端口监听。
- comma 发送 `START_SESSION`。iPhone 收到后自动暂停本地工作，关闭相机和预览，
  加载/预热当前选择的模型并清空时序状态。
- 只有资源切换和模型准备完成后，iPhone 才返回 `SESSION_READY`。pending activation
  从最初 START 起有绝对 60 秒 hard cap；在 READY 前不能发送推理请求。
- 会话中，comma 发送已经完成 openpilot 几何变换和 YUV packing 的模型输入；iPhone
  只维护图像配对历史、desire/feature recurrent state 并执行模型。
- iPhone 返回模型的原始扁平输出，不返回已解码的 `modelV2` Cap'n Proto 消息。
- `STOP_SESSION`、5 秒租约超时或连接失效会结束会话；若用户已暂停 ApplePilot 则继续
  待机，否则恢复本地相机/GPS。App 内主动退出/恢复会恢复本机模式；此前正在运行的
  车辆控制链路只在原先开启且允许恢复时恢复。

推理模式界面是 OLED 友好的黑色性能页，显示当前模型、peer、逐阶段耗时、完成吞吐率、
温度和实际在途窗口，并用可拖动的 ANE/GPU pipeline 图切换 1–4 帧在途；它不构造相机
预览、标定 Canvas、路线页或车辆遥测页。界面切换模型时会先让旧 session 停止接单并
排空，释放旧模型强引用、加载/预热新模型，然后等待 comma 用新 session 再次 START/READY。

## 2. 基本常量和编码规则

| 项目 | 值 |
|---|---:|
| UDP 端口 | `5555` |
| magic | ASCII `OPIF`，字节 `4f 50 49 46` |
| 协议版本 | `1` |
| 固定头长度 | `40` B |
| 默认/最大 UDP datagram | `1232` B |
| 可协商最小 UDP datagram | `512` B |
| 最大逻辑消息 body | `1,048,576` B |
| active session 空闲租约 | `5` s |
| pending activation 绝对 hard cap | `60` s（从最初 START 起，不可续期） |
| 非 owner UDP connection 空闲回收 | `15` s |
| 最大 UDP connections | `8` |
| terminal response cache | 最近 `32` 个 request ID |
| 输入压缩 | 仅 `0 = none` |
| 一个 packed 6-plane frame | `6 × 128 × 256 = 196,608` B |

除 magic、UTF-8 文本和原始 tensor 字节外，所有多字节数值均为 **little-endian**。
浮点数使用 IEEE-754：`float32` 或 `float16` 的 little-endian bit pattern。不要直接把
C/C++ struct 发到网络上，避免 padding 和宿主字节序问题。

`1232` 的选择是为了在 IPv6 最小 MTU `1280` 下容纳 40 B IPv6 header 和 8 B UDP
header，避免 IP 分片。OPIF 自己的 40 B header 包含在这 `1232` B 内。

## 3. 每个 UDP datagram 的 40 B header

| Offset | 长度 | 类型 | 字段 | 含义 |
|---:|---:|---|---|---|
| 0 | 4 | bytes | `magic` | 必须为 `OPIF` |
| 4 | 1 | `u8` | `version` | 必须为 `1` |
| 5 | 1 | `u8` | `message_type` | 见下一节 |
| 6 | 2 | `u16 LE` | `flags` | v1 未使用；发送端必须填 `0` |
| 8 | 2 | `u16 LE` | `header_bytes` | 必须为 `40` |
| 10 | 2 | `u16 LE` | `payload_bytes` | 此 datagram 在 header 后的字节数 |
| 12 | 8 | `u64 LE` | `session_id` | 会话 ID；`START_SESSION` 必须为 `0` |
| 20 | 8 | `u64 LE` | `request_id` | 请求/结果关联 ID |
| 28 | 2 | `u16 LE` | `fragment_index` | 从 `0` 开始 |
| 30 | 2 | `u16 LE` | `fragment_count` | 至少为 `1` |
| 32 | 4 | `u32 LE` | `message_bytes` | 重组后完整 body 长度，不含 40 B header |
| 36 | 4 | `u32 LE` | `message_crc32c` | 完整 body 的 CRC32C |

接收端至少应验证：

- datagram 实际长度等于 `40 + payload_bytes`；
- `fragment_index < fragment_count`；
- 同一逻辑消息所有分片的 type、session、request、fragment count、message bytes 和
  CRC 完全一致；
- 按 `fragment_index` 顺序连接 payload 后，长度等于 `message_bytes`，且 CRC32C 匹配；
- `message_bytes <= 1,048,576`。

## 4. 消息类型

| 值 | 名称 | 方向 | body |
|---:|---|---|---|
| `0x01` | `START_SESSION` | comma → iPhone | 启动参数 |
| `0x02` | `STOP_SESSION` | comma → iPhone | 空 |
| `0x03` | `PING` | comma → iPhone | 任意 echo 数据 |
| `0x04` | `RETRANSMIT_QUERY` | comma → iPhone | 目标消息元数据 |
| `0x05` | `MISSING_FRAGMENTS` | 双向 | 目标 type、分片数和缺片位图 |
| `0x06` | `MESSAGE_ACCEPTED` | 双向 | 已接受的目标 type |
| `0x07` | `DISCOVER` | comma → iPhone | 空；无状态服务发现，不启动推理模式 |
| `0x10` | `INFERENCE_REQUEST` | comma → iPhone | 32 B prefix + tensor |
| `0x81` | `SESSION_READY` | iPhone → comma | 模型能力和协商结果 |
| `0x82` | `SESSION_STOPPED` | iPhone → comma | 空 |
| `0x83` | `PONG` | iPhone → comma | 原样 echo `PING` body |
| `0x84` | `ANNOUNCE` | iPhone → comma | 固定 24 B 的被动发现回复 |
| `0x85` | `PIPELINE_STATUS` | iPhone → comma | 固定 12 B 的当前流水线窗口状态 |
| `0x90` | `INFERENCE_RESULT` | iPhone → comma | 24 B prefix + 原始输出 |
| `0xff` | `ERROR` | iPhone → comma | 错误码、期望序号和文本 |

iPhone 不处理收到的 `SESSION_READY`、`SESSION_STOPPED`、`PONG`、`ANNOUNCE`、
`PIPELINE_STATUS`、`INFERENCE_RESULT` 或 `ERROR`。

控制消息必须使用一个分片。当前服务端对 `START_SESSION`、`STOP_SESSION`、`PING`、
`RETRANSMIT_QUERY`、`MISSING_FRAGMENTS`、`MESSAGE_ACCEPTED` 和 `DISCOVER` 都验证
单分片元数据及完整 body CRC32C；推理请求在重组后验证 CRC。CRC 不匹配的 `START_SESSION` 返回
ERROR code `1`，其他 control 会被静默丢弃。
客户端也必须校验所有服务端消息。

### 4.1 被动自动发现（不使用 mDNS）

iPhone **不注册 Bonjour/mDNS 服务、不发送广播，也没有周期性 announcement**。comma
是唯一主动方：它向候选 IP 的 UDP 5555 发送一个合法的 `DISCOVER`。这样没有常驻广播
定时器，协议实现也不依赖 iOS Bonjour 生命周期。

`DISCOVER` 使用 `session_id=0`、非零随机 `request_id`、单分片空 body，因此
`message_bytes=0`、`message_crc32c=0`。服务端只做固定格式校验并被动返回同一
request ID 的 `ANNOUNCE`；不会取得 owner、加载模型、黑屏，也不会刷新 pending/active
session 的租约。

`ANNOUNCE` body 固定 24 B：

| Offset | 长度 | 类型 | 字段 | 含义 |
|---:|---:|---|---|---|
| 0 | 1 | `u8` | `schema` | 当前为 `1` |
| 1 | 1 | `u8` | `availability` | `0 available`、`1 activating/reconfiguring`、`2 active` |
| 2 | 2 | `u16 LE` | `flags` | bit 0：现在接受 START |
| 4 | 2 | `u16 LE` | `service_port` | 当前为 `5555` |
| 6 | 2 | `u16 LE` | `maximum_datagram_bytes` | 当前为 `1232` |
| 8 | 2 | `u16 LE` | `minimum_datagram_bytes` | 当前为 `512` |
| 10 | 2 | reserved | `0` |
| 12 | 4 | `u32 LE` | `lease_milliseconds` | active lease，当前 `5000` |
| 16 | 8 | `u64 LE` | `instance_id` | listener 每次启动生成的新随机 ID |

comma 推荐发现流程：

1. 先向上次成功的 IP 定向探测；失败后再并发探测 `192.168.7.1...254:5555`，跳过本机 IP。
2. 不先做 ICMP ping：iOS/网络策略可能丢 ICMP，而且 ping 后仍需做 OPIF 能力校验。
3. 每次 sweep 发 2 轮小包，约 0.75 秒收集窗口；严格校验 header、nonce、CRC、schema
   和端口，按 `instance_id` 去重。
4. 多台设备时优先 `accepts START`，再选 RTT 最低者；找到即停止扫描。
5. 未找到时按 5/10/30 秒退避，避免 comma 侧持续扫网。iPhone 侧始终只按请求回复。

## 5. CRC32C 和分片

CRC 是 **CRC32C/Castagnoli**，不是 IEEE CRC-32：

```text
reflected polynomial = 0x82f63b78
initial value        = 0xffffffff
final xor            = 0xffffffff
CRC32C("123456789")  = 0xe3069283
CRC32C(empty)        = 0x00000000
```

CRC 只覆盖重组后的完整 body，不覆盖 OPIF header。所有分片携带相同的
`message_bytes` 和 `message_crc32c`。

协商后的 `maximum_datagram_bytes` 为 `D` 时：

```text
payload_limit = D - 40
fragment_count = max(1, ceil(message_bytes / payload_limit))
fragment i = body[i * payload_limit : (i + 1) * payload_limit]
```

即使 body 为空也发送一个 `fragment_count=1`、payload 为空、CRC 为 0 的 datagram。
当前服务端最多同时保存 6 个未完成请求；未完成重组在最后一次有效分片后的约 500 ms
过期（维护 timer 周期为 250 ms）。协议没有 FEC；丢包恢复必须使用第 10 节的位图补片。

## 6. 建立、保活和结束会话

### 6.1 `START_SESSION` (`0x01`)

必须是单 datagram、单分片并带正确 CRC。

| Offset | 长度 | 类型 | 字段 | 值/含义 |
|---:|---:|---|---|---|
| 0 | 1 | `u8` | `input_layout` | `0=currentPacked6`；`1=pairedPacked12` |
| 1 | 1 | `u8` | `compression` | 必须为 `0` |
| 2 | 1 | `u8` | `output_encoding` | `0=float32LE`；`1=float16LE` |
| 3 | 1 | `u8` | reserved | 填 `0` |
| 4 | 2 | `u16 LE` | `requested_datagram_bytes` | 建议 `1232` |
| 6 | 4 | bytes | reserved | 全部填 `0` |
| 10 | 2 | `u16 LE` | `client_name_bytes` | 后续 UTF-8 字节数 |
| 12 | N | UTF-8 | `client_name` | 可为空；只用于 iOS 状态页显示 |

body 长度必须严格等于 `12 + client_name_bytes`。服务端把请求的 datagram 大小钳制到
`[512, 1232]`；`0` 不表示默认值，而会得到 `512`。握手 header 的 `session_id` 必须为
`0`，`request_id` 必须为非零握手关联 ID；它不是第一帧序号。

服务端只允许一个 owner。owner 由 Network.framework 的 UDP pseudo-connection（实际
上是 client IP + source port 对应的 endpoint）和 server 生成的 `session_id` 共同约束。
客户端必须在整个会话中复用同一 socket/source port。仅知道 session ID、但换了 source
endpoint 的数据会被丢弃。

同一 owner 的重复 START 行为分两种：

- activation 仍 pending 时，合法的重复 START 被**静默忽略**，不会启动第二个加载任务，
  也不会延长 pending 的绝对 60 秒 hard cap；最终 READY 仍使用最初 START 的 request ID。
  所以重试时应保留最初的 handshake ID；下文的 pending PING 只能探测，不能续期；
- session 已 active 时，合法的重复 START 会立即重发缓存的 READY，且 READY header
  使用这次**新 START 的 request ID**，便于客户端关联本次探测。

其他 endpoint 在 pending 或 active owner 存在时收到错误 `2`。listener 最多保留 8 个
UDP connections；非 owner connection 连续 15 秒没有任何非空 datagram 会被关闭。owner
不走这条 15 秒清理，而由 pending 绝对 hard cap / active 空闲租约管理。

### 6.2 `SESSION_READY` (`0x81`)

服务端生成的随机 `session_id` 位于 header；客户端必须把它当作 opaque `u64` 原样使用，
不能从 START request ID 推导。READY body 如下：

| Offset | 长度 | 类型 | 字段 | 含义 |
|---:|---:|---|---|---|
| 0 | 1 | `u8` | `status` | `0 = ready` |
| 1 | 1 | `u8` | `input_layout` | 已接受的 layout |
| 2 | 1 | `u8` | `compression` | `0 = none` |
| 3 | 1 | `u8` | `output_encoding` | 已接受的输出编码 |
| 4 | 2 | `u16 LE` | `maximum_datagram_bytes` | 双方之后必须使用的上限 |
| 6 | 2 | bytes | reserved | `0` |
| 8 | 4 | `u32 LE` | `tensor_byte_count` | 不含 32 B request prefix |
| 12 | 4 | `u32 LE` | `output_element_count` | 当前模型 metadata 为 `2576` / `18452`；协议还保留 `2580` 的编码分支，以 READY + ABI 为准 |
| 16 | 4 | `u32 LE` | `lease_milliseconds` | 当前为 `5000` |
| 20 | 2 | `u16 LE` | `feature_frames` | legacy 为 `24`，当前 spatial BigModel 为 `32`；以模型 ABI 为准 |
| 22 | 2 | `u16 LE` | `desire_history` | legacy 为 `25`，当前 spatial BigModel 为 `33`；以模型 ABI 为准 |
| 24 | 1 | `u8` | `frame_skip` | 当前 legacy / spatial BigModel 均为 `4`；其他 profile 以模型 ABI 为准 |
| 25 | 1 | `u8` | `maximum_in_flight` | 当前模型支持的在途上限；合法范围 `1...4`，实际窗口可由 App 动态调小 |
| 26 | 2 | `u16 LE` | `model_name_bytes` | 模型名长度 |
| 28 | 2 | `u16 LE` | `abi_identifier_bytes` | ABI 字符串长度 |
| 30 | M | UTF-8 | `model_name` | 当前 iOS 所选模型名 |
| 30+M | A | UTF-8 | `abi_identifier` | 原始输出/时序 ABI |

ABI 当前格式为：

```text
sha256:<source_onnx_sha256>;op-supercombo-<output_count>-f<feature_frames>-d<desire_history>-s<frame_skip>-v1
```

其中 `<source_onnx_sha256>` 是 64 个小写十六进制字符，标识转换前、保留同一 output ABI
的源 ONNX。`modeld` 必须校验 source SHA、layout、tensor size、输出元素数和完整 ABI；
不能只凭模型文件名或元素数猜 `output_slices`。不匹配时应停止会话，不能把未知扁平输出
交给错误的 parser。

### 6.3 `PIPELINE_STATUS` (`0x85`)

`SESSION_READY.maximum_in_flight` 只表示当前模型支持的上限。App profiler 可以在 active
session 内随时把实际窗口调小或调大；comma 必须使用最新 `PIPELINE_STATUS.current_depth`
限流，不能持续把 READY cap 当成实际窗口。status body 固定 12 B，格式为
`<BBBBQ>`：

| Offset | 长度 | 类型 | 字段 | 含义 |
|---:|---:|---|---|---|
| 0 | 1 | `u8` | `schema` | 必须为 `1` |
| 1 | 1 | `u8` | `current_depth` | 当前实际窗口，范围 `1...supported_maximum` |
| 2 | 1 | `u8` | `supported_maximum` | 模型支持上限，范围 `1...4`，必须等于 READY cap |
| 3 | 1 | `u8` | reserved | 必须为 `0` |
| 4 | 8 | `u64 LE` | `revision` | 非零、单调递增的 profile revision |

该消息必须是单分片，使用 active session ID，header `request_id` 等于 body `revision`。
服务端在发送 READY 后立即发送一次；用户每次改变调度档位时向当前 owner 单播一次；每个
合法 active PING 在 PONG 之外再重发一次。它不是发现广播，也没有独立周期 timer。

客户端按 session 保存 revision 最大的合法 status，忽略更小的 stale revision；同 revision
同内容是幂等重发，同 revision 不同内容属于协议错误。在拿到首个 status 前只能保守使用
D1，并应在 READY 后立即发送 active PING。status 更新丢包最多由下一次每秒 PING 修复。

这样 D1 不需要每帧先发送一整条约 393 KiB current6 请求再靠 code 9 学习窗口；升档也能
通过小包立即生效。code 9 仍是乱序、更新丢失和窗口刚刚缩小时的最终背压保护，不应作为
正常逐帧流控机制。

### 6.4 租约、`PING` 和 `PONG`

pending activation 从最初合法 START 起有绝对 60 秒 hard cap。owner 可以在模型尚未
READY 时发送 `session_id=0` 的合法 `PING`；也可使用先前 pending PONG 暴露的真实
session ID。服务端以 pending session ID 和同一 request ID 返回 PONG，但 PING、重复
START 或其他活动都**不会**改变 `pendingSessionStartedUptime`，因此不能延长 hard cap。
到 60 秒仍未 READY 时会取消 activation 并恢复本机模式。

active 会话的无活动租约为 5 秒，并在 activation 完成、发送 READY 前重新计时。因此
首次模型加载耗时不会直接消耗 active lease。服务端只有在**收到**属于 owner 的有效会话
消息时刷新活动时间；发送 READY/PONG/结果本身不刷新租约。客户端可从 START 后就在
独立 timer/thread 上每 1 秒发送 PING：pending 阶段用 session ID `0` 做启动探测，但仍
必须执行小于 60 秒的 activation deadline；READY 后立即切换为 READY header 中的真实
session ID，此后 PING 才承担 5 秒 active lease 的保活。即使暂时没有相机帧或正在等待
推理结果也不能停 active PING。

`PING` body 可为空或放客户端 timestamp/nonce，且必须是单分片、CRC 正确。`PONG` 使用
同一 request ID，原样返回 body；pending PONG 的 header session ID 是服务端已经分配的
ID。它可以同时用于 RTT 和存活检查。active PING 还会触发独立的 `PIPELINE_STATUS`；
PONG 本身仍保持严格 echo，不把 profile 字段混入其 body。

触发 pending 60 秒 hard cap 或 active 5 秒租约后，服务端静默结束 session、清空
terminal cache 和时序状态并恢复本地模式；不会主动发送 `SESSION_STOPPED`。客户端应把
长时间无 PONG/结果视为会话丢失，重新 START。

### 6.5 `STOP_SESSION` 和 `SESSION_STOPPED`

客户端主动退出时发送 body 为空且 CRC 正确的 `STOP_SESSION`。active 阶段使用真实
session ID；pending 阶段可以使用 `0` 或 pending PONG 返回的 session ID。服务端以真实
session ID 和相同 request ID 返回空 body 的 `SESSION_STOPPED`，随后结束会话并恢复本地
服务。客户端退出时即使未收到响应也应停止使用旧 session ID。

## 7. 推理请求

### 7.1 32 B request prefix

`INFERENCE_REQUEST` (`0x10`) 的完整 body 为固定 32 B prefix 加 tensor：

| Offset | 长度 | 类型 | 字段 | 值/含义 |
|---:|---:|---|---|---|
| 0 | 1 | `u8` | `input_layout` | 必须等于 READY 中的值 |
| 1 | 1 | `u8` | `compression` | 必须为 `0` |
| 2 | 1 | `u8` | `desire` | openpilot Desire index，允许 `0...7` |
| 3 | 1 | `u8` | `traffic_convention` | `0` 或 `1`，见下文 |
| 4 | 2 | `u16 LE` | `request_flags` | bit 0 = `RESET_TEMPORAL` |
| 6 | 2 | bytes | reserved | 填 `0` |
| 8 | 4 | `float32 LE` | `action_t[0]` | modeld 计算出的精确值，必须 finite |
| 12 | 4 | `float32 LE` | `action_t[1]` | modeld 计算出的精确值，必须 finite |
| 16 | 8 | `u64 LE` | `client_timestamp_ns` | 客户端 monotonic timestamp；当前只作元数据 |
| 24 | 4 | `u32 LE` | `uncompressed_tensor_bytes` | 必须等于 READY tensor size |
| 28 | 4 | `u32 LE` | `encoded_tensor_bytes` | 必须等于实际 tensor 长度和上一字段 |
| 32 | N | bytes | `tensor` | raw packed `uint8`，无压缩 |

v1 只定义 request flag bit 0；其余位必须为 0。服务端在激活 session 时已经清零状态，
所以首帧不带 `RESET_TEMPORAL` 也会被接受；客户端仍应在首帧显式设置，避免重连状态机
出错。相机几何/方向切换、发送帧丢失、modeld 重启、请求执行失败、服务端返回
“temporal reset required”，或无法确定前一帧是否进入 recurrent state 时，下一请求必须
设置它。该 flag 同时清空 iPhone 上的图像历史、feature history、desire history 和
desire edge state。

`client_timestamp_ns` 当前不回显，也不参与调度；用 header 的 request ID 计算端到端
延迟。建议填发送帧对应的客户端单调时间，供未来诊断。

### 7.2 packed 6-plane 格式

一个当前帧是 `uint8[6][128][256]`，共 `196,608` B。六个连续、row-major plane
的顺序必须是：

```text
Y00, Y10, Y01, Y11, U, V
```

它是 openpilot 已完成 camera warp 后的 packed YUV 模型输入；iPhone 不做 resize、warp、
标定或颜色转换，也不接收 JPEG/H.264/NV12 camera frame。值保持 `0...255` 原始 byte，
不要除以 255。iPhone 最终按 `older` 后 `current` 形成模型的
`[1, 12, 128, 256]` 输入。

### 7.3 `currentPacked6` (`input_layout=0`)

tensor 精确顺序和大小：

| 顺序 | 范围 | 内容 |
|---:|---:|---|
| 0 | `0 ..< 196608` | 当前 `img` 的 6 planes |
| 1 | `196608 ..< 393216` | 当前 `big_img` 的 6 planes |

tensor 为 `393,216` B，完整 request body 为 `393,248` B。此 layout 节省一半上行
带宽；iPhone 按 READY 返回的 `frame_skip` 分别维护 `img` 和 `big_img` 历史：

- `frame_skip=4` 时，模型 pair 为 `[t-4, t]`；
- `frame_skip=1` 时，模型 pair 为 `[t-1, t]`。

reset 后历史全为 0。因此前 `frame_skip` 个请求会用全零 older frame，之后才形成完整
历史。这里的 `t-n` 按**已接受的连续推理请求**计数，不按 camera
sequence 自动补洞；这也是丢帧后必须 RESET 的原因。

### 7.4 `pairedPacked12` (`input_layout=1`)

tensor 精确顺序和大小：

| 顺序 | 范围 | 内容 |
|---:|---:|---|
| 0 | `0 ..< 196608` | `img.older` 6 planes |
| 1 | `196608 ..< 393216` | `img.current` 6 planes |
| 2 | `393216 ..< 589824` | `big_img.older` 6 planes |
| 3 | `589824 ..< 786432` | `big_img.current` 6 planes |

tensor 为 `786,432` B，完整 request body 为 `786,464` B。服务端对显式 pair 不改写、不
检查时间关系。客户端必须根据 READY 的 `frame_skip` 自己提供 `[t-frame_skip,t]`。
`RESET_TEMPORAL` 会清空 recurrent state，但不会把 paired tensor 的
`older` 替换成 0；若希望 reset 首帧使用 0 older，客户端必须自己发送 0。

### 7.5 desire、traffic convention 和 `action_t`

- `desire` 是每帧当前 openpilot Desire enum，不是 one-hot，也不是预先生成的 pulse。
  iPhone 根据相对上一请求的 rising edge 构造 `desire_pulse`，并按 READY 中的
  `desire_history/frame_skip` 维护和采样历史。已知 index 为：`0 none`、`1 turnLeft`、
  `2 turnRight`、`3 laneChangeLeft`、`4 laneChangeRight`、`5 keepLeft`、
  `6 keepRight`；decoder 允许通道 `7`，其语义必须与所用模型 ABI 一致。
- `traffic_convention=0` 在模型中展开为 `[1,0]`（代码称 left-hand drive），`1` 展开为
  `[0,1]`（right-hand drive）。
- `action_t[0:2]` 必须是 modeld 原本将送给该模型的两个精确 float。远程路径不会再加
  iPhone 本地 lateral delay；NaN/Inf 会被拒绝。

feature buffer、desire history 和 hidden-state 推进完全由 iPhone 管理。comma 不应把
返回输出中的 hidden state 再作为额外网络输入。

## 8. 请求序号、排队和确认

- 每个新 session 的第一条推理请求 ID 必须为 `1`，之后严格加 1；START/PING/STOP 的
  request ID 不改变这个序列。
- 服务端按完整消息重组完成的时刻检查序号。未来序号不会越过缺口执行，而会返回错误
  `8` 和当前 `expected_request_id`。
- 客户端的绝对上限是 `SESSION_READY.maximum_in_flight`，实际发送窗口必须采用最新
  `PIPELINE_STATUS.current_depth`。生产版拆分 CoreAI
  `big-ane-gpu` 的支持上限为 `4`；默认 `small-coreml-all` 和其他当前同步 Core ML
  固定为 `1`。开发诊断构建若重新启用 ANE vision + GPU tail 两段的
  `small-ane-gpu`，其上限为 `2`。该字段表示模型支持上限，不是 App 此刻
  一定会接收的窗口；服务端的实际窗口可由黑屏 profiler 在
  `1...maximum_in_flight` 内动态调整。
- `big-ane-gpu` 的四档不是仅改变队列长度，而是改变 N+1 的放行点：D4 在 N 完成
  `vision_0` 后启动，D3 在 `vision_1` 后，D2 在 `vision_2` 后，D1 在 recurrent GPU
  tail 后启动（完全串行）。仅开发诊断使用的 `small-ane-gpu` 对应 D2 在 vision 后、
  D1 在 tail 后启动。每条请求仍按自己的 stage 依赖顺序执行。
- 拆分 CoreAI 允许多个 frame 的 ANE functions 并发提交，使 ANE 工作与较早 frame 的
  recurrent GPU tail 重叠。不过“并发提交”不保证 ANE 在具体 iPhone 上物理并行：CoreAI/
  系统调度器可能并行、交错或串行执行。深度 3/4 可能只增加队列、端到端延迟、内存和
  发热而不增加吞吐，必须用界面 timing、吞吐率和功耗实测选择。
- 当前在途数量已达到窗口时，完整且序号正好等于 expected 的新请求收到错误 `9`：
  `inference window full; retry this request ID`。该请求 ID **不消费**，error body 的
  `expected_request_id` 仍是它；客户端等待在途请求的 terminal response 后，必须用同一
  request ID 重发。建议重发完全相同的 body/分片。
- App profiler 可以在 active session 中把实际窗口动态设为模型支持范围内的任意值；big
  为 `1...4`，生产版 default/Core ML 固定为 `1`（诊断 small split 为 `1...2`）。服务端用单调 revision 的 `PIPELINE_STATUS` 立即单播
  新窗口，并在每个 active PING 时重发；客户端收到后无需重连即可调节 producer。窗口 1
  表示下一帧必须等上一帧 GPU terminal 完成，即关闭跨帧重叠。
- 多个请求可以执行，但 terminal response 始终按 request ID 顺序发布。图像历史在进入
  accelerator 前按序推进，GPU recurrent tail 严格按 request ID FIFO 执行；feature/
  desire/hidden state 只在该 FIFO tail gate 内推进。
- 带 `RESET_TEMPORAL` 的请求只在整个在途窗口为空时接受；否则返回 code 9 且不消费 ID。
- 对上述 iOS 后端，请求成功解码并真正开始 running 后，服务端才把 expected ID 加 1，并返回
  `MESSAGE_ACCEPTED` (`0x06`)；body 是一个字节 `0x10`。这只表示请求已开始执行，不表示
  推理成功。
- Android QNN HTP 后端固定支持 D2：一帧执行、一帧完整有序排队，整图 NPU 执行仍严格
  串行。该后端在请求进入这两个有界槽位时消费 ID 并返回 `MESSAGE_ACCEPTED`，因此 ACK
  表示已接纳，不保证已经开始 NPU 计算。满窗口与 RESET 的 code 9 规则不变；前帧失败时
  取消已接纳的待执行帧，两者分别按序返回可重放的 code 11，下一 ID 必须 RESET。
  STOP、断线和服务停止取消未开始的帧，等待正在执行的帧排空后才允许新会话。
- 服务端按 request ID 缓存最近 32 个 **terminal response**，包括成功
  `INFERENCE_RESULT` 和推理失败 `ERROR code 11`。它们都可按同一 request ID 幂等重放。
- 对已经消费的旧 request ID：fragment 0 或 retransmit query 会重放 cache 中的 terminal；
  若该 ID 仍在执行（Android 也包括已接纳的待执行槽位）则返回 `MESSAGE_ACCEPTED`；若既不在执行也已被 32 项 cache 淘汰，则
  返回 `ERROR code 12`，而不是静默丢弃。

错误对序号/时序的影响：

- `9 busy`：ID 未消费；等待后重试同一 ID，不要递增；
- `10 malformed/temporal reset required`：ID 未消费；修正同一 ID 后重发；
- `11 inference failed`：这是已缓存的 terminal，ID 已消费，body 中
  `expected_request_id` 是下一 ID；窗口排空后的下一 ID **必须**设置
  `RESET_TEMPORAL`。若失败时后一帧已经启动，其输出会被丢弃并同样按序返回 code 11，
  绝不会把可能错位的 recurrent 输出交给 comma；
- `12 terminal expired`：旧 ID 已消费，但对应 terminal 已从 32 项 cache 淘汰。客户端
  已无法从该 session 恢复那一帧结果，应按系统安全策略丢弃/重建 session，不能把它当作
  busy 再重跑旧 ID。

## 9. 推理结果和错误

### 9.1 `INFERENCE_RESULT` (`0x90`)

结果 header 的 session/request ID 对应原请求。body prefix 固定 24 B：

| Offset | 长度 | 类型 | 字段 | 含义 |
|---:|---:|---|---|---|
| 0 | 1 | `u8` | `status` | `0 = success` |
| 1 | 1 | `u8` | `encoding` | `0=float32LE`；`1=float16LE` |
| 2 | 1 | `u8` | `raw_output_layout` | 当前代码：元素数为 `2580` 时为 `1`，其他为 `0`（包括 `2576` 和 `18452`）；不能单独作为 ABI 判据 |
| 3 | 1 | reserved | `0` |
| 4 | 4 | `u32 LE` | `element_count` | 必须等于 READY 值 |
| 8 | 4 | `u32 LE` | `inference_time_us` | iPhone 模型执行耗时，四舍五入/钳制 |
| 12 | 4 | `u32 LE` | `queue_time_us` | 完成重组到开始推理的等待时间 |
| 16 | 8 | `u64 LE` | `server_uptime_ns` | 组装结果时的 iPhone monotonic uptime |
| 24 | N | floats | `raw_output` | 扁平逻辑元素顺序 |

`encoding=0` 时 N 必须为 `element_count × 4`；`encoding=1` 时为
`element_count × 2`。float16 是 iPhone 从内部 float 输出逐元素转换得到。客户端应按
READY 的 ABI 使用对应 openpilot output parser；`raw_output_layout` 和 count 必须再次
校验。

客户端完成并验证结果后可发送 `MESSAGE_ACCEPTED`，body 为一个字节 `0x90`。当前实现
把它当作活动消息，但不会因此提前移除 32 项 terminal cache。

### 9.2 `ERROR` (`0xff`)

| Offset | 长度 | 类型 | 字段 | 含义 |
|---:|---:|---|---|---|
| 0 | 2 | `u16 LE` | `error_code` | 见下表 |
| 2 | 2 | `u16 LE` | `message_bytes` | UTF-8 文本长度 |
| 4 | 8 | `u64 LE` | `expected_request_id` | 仅相关错误有值，否则为 `0` |
| 12 | N | UTF-8 | `message` | 人类可读诊断 |

| Code | 当前含义 |
|---:|---|
| 1 | malformed `START_SESSION` |
| 2 | server 已有 owner/active client |
| 3 | iOS inference runtime callback 不可用 |
| 4 | 进入 inference mode、加载或预热模型失败 |
| 5 | 未完成重组消息超过 6 个 |
| 6 | 同一请求的分片元数据不一致，或同 index 内容冲突 |
| 7 | 完整 request CRC32C 不匹配 |
| 8 | request sequence gap；`expected_request_id` 有效 |
| 9 | inference window 已满或 RESET 时窗口非空；当前 ID 未消费，按 `expected_request_id` 重试同一 ID |
| 10 | request prefix/tensor 非法，或上次失败后未 RESET |
| 11 | 模型推理执行失败；这是可重放 terminal，`expected_request_id` 为下一序号且下一请求必须 RESET |
| 12 | 旧 ID 的 terminal response 已被 32 项 cache 淘汰；`expected_request_id` 为当前下一序号 |

未知/格式错误 header、非 owner session 的消息以及部分不适用的旧消息可能被静默丢弃，
不能假定每种坏包都会收到 ERROR。

## 10. 丢包和位图补片

位图统一按 little-bit order 表示分片：

```text
fragment i 对应 bitmap[i / 8] 的 bit (i % 8)
bit = 1 表示缺失、请求重发
bit = 0 表示已收到/不请求
bitmap bytes = ceil(fragment_count / 8)
```

### 10.1 查询 request 缺片

客户端在尚未收到 `MESSAGE_ACCEPTED` 时发送 `RETRANSMIT_QUERY` (`0x04`)，其 header
request ID 为目标 inference request ID，body 为：

| Offset | 长度 | 类型 | 字段 | 值/含义 |
|---:|---:|---|---|---|
| 0 | 1 | `u8` | `target_type` | `0x10` |
| 1 | 1 | reserved | `0` |
| 2 | 2 | `u16 LE` | `fragment_count` | 原请求的分片数 |
| 4 | 4 | `u32 LE` | `message_bytes` | 原请求 body 长度 |
| 8 | 4 | `u32 LE` | `message_crc32c` | 原请求完整 body CRC |

若服务端仍有匹配 assembly，返回 `MISSING_FRAGMENTS` (`0x05`)：

| Offset | 长度 | 类型 | 字段 | 值/含义 |
|---:|---:|---|---|---|
| 0 | 1 | `u8` | `target_type` | `0x10` |
| 1 | 1 | reserved | `0` |
| 2 | 2 | `u16 LE` | `fragment_count` | 原请求的分片数 |
| 4 | B | bytes | `missing_bitmap` | bit 1 的分片需重发 |

若 assembly 已过期而 request ID 尚未消费，服务端会返回全 1 的有效分片位图，要求全部
重发。若 request ID 已消费，服务端按状态返回：正在执行则 `MESSAGE_ACCEPTED`；terminal
仍在 32 项 cache 则直接重放 RESULT 或 code 11 ERROR；cache 已淘汰则 code 12。客户端应
在 500 ms assembly 期限内尽早查询、重发位图中的原始 datagram，并重复查询直到收到
accepted 或 terminal。不要重建 body 后改变 CRC 或 fragment sizing。

### 10.2 请求 terminal/result 缺片

terminal cache 同时保存 `INFERENCE_RESULT` 和 `ERROR code 11`。客户端收到其中任一类
terminal 的部分分片时，都用 `MISSING_FRAGMENTS` (`0x05`) 请求缺片：

| Offset | 长度 | 类型 | 字段 | 值/含义 |
|---:|---:|---|---|---|
| 0 | 1 | `u8` | `target_type` | `0x90` |
| 1 | 1 | reserved | `0` |
| 2 | 2 | `u16 LE` | `fragment_count` | 实际 terminal header 中的分片数 |
| 4 | B | bytes | `missing_bitmap` | bit 1 的 terminal 分片需重发 |

服务端只重发 bitmap 指定的缓存 terminal 分片。也可以发送 target `0x90` 的
`RETRANSMIT_QUERY`；body 必须恰好为 12 B 且 CRC 正确，但当前实现对 RESULT query 不
比较 offsets 2...11 的 `fragment_count/message_bytes/message_crc32c`，因此这 10 个
metadata bytes 可以全部填 `0`；reserved offset 1 也填 `0`，即除 offset 0 的 target
`0x90` 外，其余 11 B 可全部为 0：

```text
90 00 00 00 00 00 00 00 00 00 00 00
```

这里 body 的 `target_type=0x90` 是 terminal-cache 查询键，不承诺缓存内容一定为 RESULT。
若 request ID 正在执行，返回 `MESSAGE_ACCEPTED`；若其 terminal（成功 RESULT 或 code 11
ERROR）仍在 32 项 cache，服务端重发整条 terminal；若已淘汰，返回 code 12。接收方必须
按每个返回 datagram 的实际 header type 分桶、按该 type 的 fragment metadata 重组，再用
实际 type 选择 RESULT 或 ERROR body parser。不能把 target `0x90` 强制解释为 RESULT。
已有部分 terminal 时，精确位图方式更省带宽。

## 11. iOS 资源切换行为

收到合法 START 后、发送 READY 前，当前 App 会：

- 立即暂停本地模型 preprocessing，阻止新的本机 live inference；
- 停止双摄 capture session，关闭 camera hardware；
- 停用 native sample-buffer preview，暂停两套 UIImage preview renderer，清空预览图；
- 关闭模型输入小预览；
- 退出标定模式并关闭 calibration capture；
- 取消 preview camera relay 和 manual-focus 延迟任务；
- 若 VO 路线正在记录则停止记录；
- 停止 GPS；
- 停止车辆 controls/FlexRay UDP pipeline，并记住进入前是否运行；
- 保留/加载所选模型，预热后只运行 remote inference pipeline；
- 把根 UI 切换成黑色低刷新性能页；模型菜单、stage timing 和 pipeline profiler 不会
  构造任何相机 view。

READY 代表以上切换已经完成，不只是 UDP socket 已建立。会话结束后会清空 remote image
和 recurrent state、重启 GPS 和相机；controls 仅在进入前运行时恢复。VO route recording
不会自动恢复。模型保持在内存中以避免重复加载。

若用户在黑屏页选择另一模型，App 不走上述本机恢复：它先禁止 START/INFERENCE、清除旧
READY/cache/session，排空 accelerator work 并结束旧 remote epoch，然后清掉旧模型的
functions/Core ML provider/array 强引用，加载和预热新模型。完成后相机/GPS/controls 仍
保持关闭，listener 回到可发现的 armed 状态；comma 必须重新 DISCOVER/START，并用新的
session ID 和 READY ABI 建立会话。加载失败时 listener 不接受 START，用户可改选其他模型
或退出 server mode。

仍然存在少量必要工作：UDP 网络栈、模型执行、最小 SwiftUI 状态页、系统事件、每 2 秒
一次的低频 thermal/battery poll，以及不快于每 0.5 秒一次的帧数/延迟 UI 发布。黑屏用于
降低显示和本地图像管线功耗，不代表 iOS 进入系统后台。

## 12. iOS 前台限制

当前 target 没有声明可维持此 UDP/计算服务的 `UIBackgroundModes`，也没有 Network
Extension。iOS App 退到后台、切换到其他 App、锁屏或被系统挂起后，UDP 接收和推理均
不保证继续运行。因此实际使用必须满足：

- App 保持前台 active，iPhone 保持解锁；
- 允许 Local Network 权限；
- 不要按 Home、锁屏或让其他全屏系统界面长期覆盖；
- 保持稳定供电和散热，并让 modeld 对无结果/租约丢失执行安全降级。

App 在 scene active 时设置 `isIdleTimerDisabled=true`，所以正常前台状态不会自动熄屏；
scene 不 active 时该设置会取消。iOS 调度、thermal throttling 和网络均不提供硬实时保证。

## 13. 带宽、包率和队列限制

在协商 datagram `1232` B 时，每片最多携带 `1192` B body。以下只计算 UDP application
payload（OPIF header + body），不含 IP/UDP/Wi-Fi/Ethernet 额外开销：

| 消息 | 逻辑 body | 分片数 | 每消息上线字节 | 20 Hz 上线速率 |
|---|---:|---:|---:|---:|
| current6 request | 393,248 B | 330 | 406,448 B | 8.13 MB/s，约 65.0 Mbit/s |
| paired12 request | 786,464 B | 660 | 812,864 B | 16.26 MB/s，约 130.1 Mbit/s |
| 2580 × float32 result | 10,344 B | 9 | 10,704 B | 0.214 MB/s，约 1.71 Mbit/s |
| 2580 × float16 result | 5,184 B | 5 | 5,384 B | 0.108 MB/s，约 0.86 Mbit/s |

current6 在 20 Hz 仅请求就约 6,600 datagram/s；paired12 约 13,200 datagram/s。更小的
协商 datagram 会进一步增加包率和 OPIF header 开销。float16 只减少下行结果，不会压缩
输入。

建议优先使用 `currentPacked6 + float16`，以及隔离、信号稳定的高吞吐链路；若 comma
与 iPhone 可通过有线 Ethernet/USB 网络可靠互通，通常比拥挤 Wi-Fi 更合适。发送端需要
适度 batch/pacing，避免瞬间把数百个分片灌满 socket buffer。在途不得超过 READY 窗口；
窗口满时 busy 请求会被拒绝而不是排队。宁可在 comma 端丢弃尚未发送的旧 camera frame，
并在时间连续性破坏时 RESET，也不要越过 expected request ID 试图排队。

### 13.1 热功耗预估与 profile 方法

这不是“模型不发热”模式：同一模型、同一 20 Hz 仍占主要 ANE/GPU 功耗，current6 网络还
新增约 65 Mbit/s、6,600 packet/s 的收包/重组成本。省下的是 iPhone 双摄 sensor/ISP、
20 Hz warp/pack、预览转换与非黑显示、GPS/标定/车辆控制等本地工作。

在没有同机功率仪实测前，合理的工程区间是：相对于 App 原先“双摄 + 预处理 + 非黑预览
+ 同模型 20 Hz”的 steady state，黑屏 inference server 的**整机持续功耗/发热约下降
15–35%**；原界面亮度高、标定或双预览活跃时可能接近 30–45%。这通常对应热稳态表面温度
约低 2–6°C，但环境温度、充电方式、手机壳、网络链路和具体机型会让结果显著变化，不能
把这个范围当产品保证。

在途 2–4 允许后续帧的 ANE work 与较早帧的 GPU tail 重叠，可能比在途 1 提高吞吐，也
可能让模型部分功耗上升；在途 1 是最低重叠/最低峰值功耗基线。CoreAI 并发提交不保证
ANE 物理并行，因此深度 3/4 可能主要增加排队和发热。统一模型/Core ML 当前没有真实
异步 stage overlap，因此强制为 1。

建议在同一手机、同一模型、同一输入速率和同一供电条件下各跑 15–20 分钟：

- A：正常双摄预览；B：default Core ML server D1；C–F：big server D1、D2、D3、D4；
- 记录 UI 的逐 stage ms、完成 FPS 和 thermal state；
- 用 Instruments Energy Log 或外部 USB 功率计记录平均功率，并固定屏幕亮度、环境温度；
- 确认 server 页面没有绿色相机指示、GPS 定位活动和 calibration/controls 日志；
- 分别报告前 2 分钟冷机与最后 5 分钟热稳态，避免把短时 turbo 当持续能力。

## 14. 安全边界

OPIF v1 当前：

- **没有身份认证或 HMAC**；
- **没有加密或防窃听**；
- **没有 anti-replay**；
- **没有 FEC**；
- **没有压缩**；
- CRC32C 只能发现随机损坏，不能防止恶意篡改；
- 随机 session ID 和单 owner endpoint 是状态隔离，不是安全认证；
- listener 未绑定特定 interface，能访问 iPhone UDP 5555 的主机都可能尝试 START，并
  触发相机/控制服务停用或制造网络/计算负载。

只能在受控的点对点链路、隔离 VLAN 或明确防火墙规则内使用；不要把 UDP 5555 暴露到
互联网或不受信任 Wi-Fi。`client_name` 是未认证显示文本，不能作为授权依据。用于车辆时，
modeld 必须设置结果 deadline、检查 request ID/CRC/ABI，并在超时、陈旧结果、热降频或
session 丢失时进入既有的安全 fallback，不能继续使用上一帧输出。

## 15. modeld 集成伪代码

以下是接入骨架，函数名不对应某一 openpilot revision。重点是 byte layout、状态所有权
和恢复时序。

```python
MAGIC = b"OPIF"
VERSION = 1
HEADER_BYTES = 40
MAX_DATAGRAM = 1232

def crc32c(body):
  crc = 0xffffffff
  for b in body:
    crc = CRC32C_TABLE[(crc ^ b) & 0xff] ^ (crc >> 8)
  return (~crc) & 0xffffffff

def fragment(msg_type, session_id, request_id, body, datagram_bytes):
  limit = datagram_bytes - HEADER_BYTES
  count = max(1, ceil(len(body) / limit))
  checksum = crc32c(body)
  out = []
  for index in range(count):
    payload = body[index * limit:(index + 1) * limit]
    header = pack_le(
      "4s BB H H H Q Q H H I I",
      MAGIC, VERSION, msg_type, 0, HEADER_BYTES, len(payload),
      session_id, request_id, index, count, len(body), checksum)
    out.append(header + payload)
  return out

# control 也走相同 fragment/header/CRC helper；它们必须恰好得到一个 datagram。
def send_control(msg_type, session_id, request_id, body=b""):
  packets = fragment(msg_type, session_id, request_id, body, MAX_DATAGRAM)
  assert len(packets) == 1
  send_all(packets)

# 1. 用一个长期复用、connected UDP socket 连 iPhone:5555。
sock = udp_connect(iphone_ip, 5555)

# START body: layout=current6, compression=none, output=float16,
# byte 3 + bytes 6..9 reserved，client name 长度在 offset 10。
name = b"comma-modeld"
start_body = pack_le("B B B B H I H", 0, 0, 1, 0, 1232, 0, len(name)) + name
send_all(fragment(0x01, 0, handshake_nonce, start_body, 1232))

# 2. pending activation 从最初 START 起绝对最多 60 s；重复 START 会静默。
# 每秒可用 session_id=0 的 CRC-valid PING 探测。PONG 会在 header 暴露 pending ID；
# PING 不延长 hard cap，客户端 activation deadline 必须小于 60 s。
# READY 仍关联最初 handshake_nonce。需要放弃启动时可用 session_id=0 STOP。
pending_session_id = 0
activation_deadline = monotonic_time() + 59.0
while True:
  if monotonic_time() >= activation_deadline:
    send_control(0x02, pending_session_id, shutdown_nonce, b"")
    abort_activation("60 s server hard cap")
  send_control(0x03, pending_session_id, next_ping_id(), monotonic_ns_as_bytes())
  event = receive_valid_message_or_timeout(1.0)
  if event is None:
    continue
  if event.type == 0x83:                 # pending PONG
    pending_session_id = event.header.session_id
    continue
  if event.type == 0x81 and event.header.request_id == handshake_nonce:
    ready = event
    break
  if event.type == 0xff:
    abort_activation(event)

# 3. 完整校验 SESSION_READY。active 的 5 s lease 从 READY 前重新开始。
session_id = ready.header.session_id
caps = parse_ready(ready.body)
assert caps.input_layout == 0
assert caps.compression == 0
assert caps.tensor_bytes == 393216
source_sha, output_abi = parse_full_abi(caps.abi_identifier)
assert source_sha == EXPECTED_SOURCE_ONNX_SHA256
assert output_abi == expected_output_abi(caps)
datagram_bytes = caps.maximum_datagram_bytes

# READY 后 keepalive 必须改用真实 session ID，仍独立于 camera/inference loop。
start_timer(every=1.0, callback=lambda:
  send_control(0x03, session_id, next_ping_id(), monotonic_ns_as_bytes()))

# READY cap 不是实际窗口。首个合法 status 前保持 D1；status 会紧随 READY，且每次
# active PING 都会重发，因此不需要用 393 KiB inference body 探测档位。
pipeline_revision = 0
effective_window = 1

next_send_id = 1
next_publish_id = 1
reset_next = True
inflight = OrderedMap()  # request_id -> frame/body/datagrams/terminal assembly

while modeld_running or inflight:
  # 独立收包路径持续做 ACK、缺片修复、PING 和 terminal 重组。服务端保证 terminal
  # 按 ID 发布；客户端仍按 request_id 分桶并只按 next_publish_id 交给 model parser。
  for event in receive_available_valid_messages():
    if event.type == 0x85:
      status = parse_pipeline_status_strict(event.body)
      assert event.session_id == session_id
      assert event.request_id == status.revision
      assert status.supported_maximum == caps.maximum_in_flight
      if status.revision < pipeline_revision:
        continue                    # stale UDP status
      if status.revision == pipeline_revision:
        assert status == latest_status  # equal revision must be identical
        continue
      pipeline_revision = status.revision
      latest_status = status
      effective_window = status.current_depth
      continue
    route_ack_repair_or_terminal(event, inflight)

  while next_publish_id in inflight and inflight[next_publish_id].terminal is not None:
    item = inflight.pop(next_publish_id)
    terminal = item.terminal
    validate_crc_session_and_request(terminal, session_id, next_publish_id)
    if terminal.type == 0x90:
      validate_result_prefix_and_abi(terminal.body, caps)
      raw_output = decode_f16_or_f32(terminal.body[24:])
      publish_using_matching_openpilot_model_parser(raw_output, item.frame.metadata)
      send_control(0x06, session_id, next_publish_id, bytes([0x90]))
      next_publish_id += 1
    elif terminal.type == 0xff and parse_error(terminal.body).code == 11:
      # 此帧和可能已启动的后续帧都不会发布。窗口排空后下一 ID 带 RESET。
      next_publish_id += 1
      reset_next = True
    elif terminal.type == 0xff and parse_error(terminal.body).code == 12:
      fail_safe_and_reconnect("terminal cache expired")
    else:
      handle_protocol_error_or_reconnect(terminal)

  # producer 只填满最新 status 的实际窗口；READY cap 仅作绝对上限。
  while modeld_running and len(inflight) < effective_window:
    if reset_next and inflight:
      break  # RESET 只能在空窗口边界发送
    frame = acquire_and_prepare_openpilot_model_inputs()
    tensor = frame.img12[196608:393216] + frame.big_img12[196608:393216]
    flags = 1 if reset_next else 0
    body = pack_le(
      "B B B B H H f f Q I I",
      0, 0, current_desire_enum(), traffic_convention_scalar(),
      flags, 0, action_t[0], action_t[1], frame.monotonic_ns,
      len(tensor), len(tensor)) + tensor
    datagrams = fragment(0x10, session_id, next_send_id, body, datagram_bytes)
    reply = send_with_fragment_repair_until_accepted_or_terminal(
      next_send_id, datagrams, body, deadline=REQUEST_DEADLINE)
    if reply.is_error(code=9):
      # status 更新可能与发送交错；ID 未消费，保留同一 body，等最新窗口有空位再重试。
      retain_for_same_id_retry(next_send_id, frame, body, datagrams)
      break
    if reply.is_error(code=10):
      reset_next = True
      retain_for_same_id_retry(next_send_id, frame, rebuild_with_reset(body), None)
      break
    if reply.is_error(code=12):
      fail_safe_and_reconnect("terminal cache expired")
    inflight[next_send_id] = Inflight(frame, body, datagrams, reply.terminal_if_any)
    next_send_id += 1
    reset_next = False

  repair_timed_out_inflight(
    inflight,
    # 完全没收到 terminal 分片时 target 后 11 bytes 可全 0。
    full_replay_query=bytes([0x90]) + bytes(11))

# 4. 正常退出。control 也必须使用正确的 empty-body CRC32C。
send_control(0x02, session_id, shutdown_nonce, b"")
wait_briefly_for(0x82)
```

实现时还必须注意：

- 收包线程要按 `(session_id, message_type, request_id)` 分桶，不要让 PONG、
  PIPELINE_STATUS、ACK、ERROR 和 RESULT 互相阻塞；
- 每个分片先检查 40 B header，再按完整消息校验 CRC；不能按“到达顺序”直接拼接；
- START 之后以 READY 返回的 datagram 上限为准；双向都不能继续假定本地配置值；
- `MESSAGE_ACCEPTED` 不是结果，结果也可能先于客户端处理 ACK；接收状态机必须容忍这种
  UDP 到达顺序；
- 客户端用最新 PIPELINE_STATUS 的 `current_depth` 限流，READY cap 只做绝对上限；status
  尚未收到时保持 D1。code 9 只是更新交错/丢包时的兜底，收到后必须保留并重试同一 ID，
  不能递增或越过该 ID 改发未来请求；
- 成功 RESULT 与 code 11 ERROR 都是可重放 terminal。请求重传得到的消息 type 可能是
  `0x90` 或 `0xff`，必须先分派 type 再解析 body；
- terminal cache 按最近 32 个 request ID 淘汰。deadline/retry 必须远短于填满 cache 所需
  时间；code 12 表示结果已经不可恢复，不能继续使用陈旧模型输出；
- pending activation 的重复 START 被静默忽略；CRC-valid、session ID 0 的 PING 只用于
  探测，不能延长绝对 60 秒 hard cap。READY 后立即改用真实 session ID 保持 active lease；
- 切换模型或 ABI 时，以 READY 的 ABI 和 `frame_skip` 为准重新建立 session，不能沿用旧
  image/recurrent state；
- 不把服务器时间与 comma 时间直接相减。端到端延迟应使用 comma 自己的 monotonic
  send/receive timestamp；`server_uptime_ns` 只在 iPhone 时钟域内有意义。

## OPIT v1 TCP stream transport (port 5556)

The app also listens on TCP port 5556. UDP and TCP share one session owner,
model activation callback, inference pipeline and teardown lifecycle. Only one
transport/client can own the model at a time. TCP may be reached directly or
through a USB forwarding endpoint; the service itself is a normal TCP listener.

Each logical message is one 32-byte little-endian header followed by its body:

| Offset | Field | Type |
| --- | --- | --- |
| 0 | Magic `OPIT` | 4 bytes |
| 4 | Version, 1 | u8 |
| 5 | Message type, same numeric IDs as OPIF | u8 |
| 6 | Flags, must be 0 | u16 |
| 8 | Session ID | u64 |
| 16 | Request ID | u64 |
| 24 | Body byte count, at most 1,048,576 | u32 |
| 28 | CRC32C of the complete body | u32 |

This is Python struct `<4sBBHQQII>`. START, READY, INFER, RESULT, ERROR, PING,
PONG, STOP and MESSAGE_ACCEPTED bodies retain the existing OPIF ABI. The READY
legacy datagram field is retained for ABI compatibility and does not fragment a
TCP body. TCP has no discovery, fragment headers, NACKs, retransmit queries or
terminal result cache. A malformed header, oversized body or CRC mismatch closes
the stream. TCP read calls may split or coalesce messages arbitrarily.

Immediately after READY the server sends STREAM_SETTINGS (type `0x86`), using
the same session ID, request ID 0 and four-byte body
`[schema=1, executionSlots, queuedSlots=1, reserved=0]`. The client waits for both
READY and SETTINGS before submitting inference. Execution slots are the current
model/window clamped to 1–2 (normally 2); READY's capacity byte matches this
execution count. Settings are immutable within a session and may be repeated
idempotently after PING or duplicate START. A window change affecting that count
ends the stream; reconnect to negotiate it again. The separate model vision
stage overlap policy is unchanged.

A valid complete INFER consumes the next contiguous request ID only if admitted.
At most `executionSlots + 1` requests are admitted but not terminally published:
two may execute and one complete request may wait in FIFO at the usual setting.
Additional requests receive existing code 9 with the unconsumed expected ID.
MESSAGE_ACCEPTED confirms admission, not completion, and releases no client
credit. No result ACK is required to free a server execution slot. As an execution
finishes, the waiting request is started before encoding/sending the result;
terminal outputs remain strictly request-ordered. RESET_TEMPORAL requires an
empty active/waiting window. Any executing inference failure closes the TCP
session and discards its pending work. Reconnect begins a fresh session and the
existing pipeline reset drains old accelerator work and resets temporal history.

Receive storage is limited to one 32-byte header or one body of at most 1 MiB
per connection (at most 8 combined UDP/TCP peers). Transmit storage has at most
64 frames and 1 MiB including headers; only one Network.framework send is pending.
Overflow or a partial frame/send stalled for 5 seconds closes the stream. Existing
active-session lease and pending-activation deadlines still apply. Connection
identity and session-generation checks discard old receive/send/task callbacks.

STOP immediately invalidates the session and cancels its pending inference, then
flushes the already queued SESSION_STOPPED reply before closing the TCP stream.
This flush has a 500 ms deadline (checked by 250 ms maintenance ticks); it cannot
hold up model teardown. Read admission stops as soon as STOP is processed.

TCP is an optional additional listener. Failure to bind TCP 5556, or a later TCP
listener failure, closes only TCP connections and logs `OPIF TCP listener
unavailable ...; UDP remains available`. The existing UDP listener and service
state remain operational. Stopping the service explicitly closes both listeners.
