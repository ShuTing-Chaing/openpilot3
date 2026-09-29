# Cinque v3 模型 ABI

核对日期：2026-09-24。本文描述指定版本 Cinque v3 原始 ONNX 模型的输入输出、图像格式、跨帧状态和输出语义。shape 按模型实际维度列出；切片使用 **从 0 开始、左闭右开 `[start,end)`** 的元素索引，不是字节偏移。

## 1. 模型身份

| 项目 | 固定值 |
|---|---|
| 源模型 | Cinque v3，`big_driving_supercombo.onnx` |
| 模型仓库 / revision | `commaai/openpilot_driving_models` / `81a9ad0139976653c041de50b60f1160a873869e` |
| checkpoint | `b9facbcc-4d47-410e-b3ce-dfcbad12ba92/56320/f78ed37d-afad-4dbc-8050-40ea885eedde/12864` |
| source ONNX SHA-256 | `404a18cfd86d29637d20c697dfde245bb47c666ae016730ab674c65f4d1e1aa4` |
| 输出 | `float32[1,18452]` |
| 特征历史 | 32 个采样点，每点 32 个空间 token × 512 维 |
| Desire 历史 | 33 个采样组，每组 8 类 |
| 历史采样间隔 | 4 帧 |

以源 ONNX 的 SHA-256 确认模型身份；仅凭文件名或输出元素总数不足以确认相同 ABI。

## 2. 原始 ONNX 接口

### 2.1 外部输入输出

以下签名适用于直接执行 `big_driving_supercombo.onnx`：

| 方向 | 名称 | dtype | shape |
|---|---|---|---|
| 输入 | `new_img` | `uint8` | `[2,6,128,256]` |
| 输入 | `desire` | `float32` | `[8]` |
| 输入 | `traffic_convention` | `float32` | `[1,2]` |
| 输入 | `action_t` | `float32` | `[1,2]` |
| 输入 | `state_img_q` | `uint8` | `[2,5,6,128,256]` |
| 输入 | `state_desire_q` | `float32` | `[132,1,8]` |
| 输入 | `state_feat_q` | `float32` | `[128,1,16384]` |
| 输出 | `outputs` | `float32` | `[1,18452]` |
| 输出 | `next_state_img_q` | `uint8` | `[2,5,6,128,256]` |
| 输出 | `next_state_desire_q` | `float32` | `[132,1,8]` |
| 输出 | `next_state_feat_q` | `float32` | `[128,1,16384]` |

`new_img` 首轴为两路相机，`[0]=img/MED`、`[1]=big_img/SBIG`，不是 batch=2。`desire` 是调用者已生成的 8 维上升沿 pulse；完整 ONNX 不负责从 enum 检测上升沿。

`traffic_convention` 使用 LHD `[1,0]`、RHD `[0,1]`。`action_t=[lateral_time,longitudinal_time]` 为横向、纵向动作时间，单位秒，由调用者根据延迟确定；这两个时间不是模型固定常量。

首帧将三个 `state_*` 队列置零。每次运行后，下一次输入 `state_*` 直接使用本次 `next_state_*`；队列推进与历史采样已在图内完成，不要在外部重复执行。

### 2.2 图内主要张量

以下为模型内部边界，帮助理解时序维度；它们不属于完整 ONNX 的外部输入列表。

| 含义 | dtype | shape | 逻辑顺序 |
|---|---|---|---|
| 配对后的 MED 图像 | `uint8` | `[1,12,128,256]` | `[batch,通道,高,宽]`，通道包含 `t-4`、`t` 两帧 |
| 配对后的 SBIG 图像 | `uint8` | `[1,12,128,256]` | 同上 |
| 当前视觉特征 `view_39` | `float16` | `[1,32,512]` | `[batch,空间 token,特征]` |
| 采样后的特征历史 | `float16` | `[1,32,32,512]` | `[batch,历史采样点,空间 token,特征]` |
| 汇聚后的 desire 历史 | `float16` | `[1,33,8]` | `[batch,历史采样组,类别]` |

网络内部使用 FP16，最终输出 cast 为 FP32；外部 FP32 状态与辅助输入也会在图内转换到 FP16。FP32 输出容器不表示内部网络全程 FP32。扁平输出按逻辑 C/row-major 顺序排列，最后一轴最快。

## 3. 图像 packing 与几何

两路图像均先 warp 到 `512×256` 的模型视图，再打包为 `uint8[6,128,256]`。MED 与 SBIG 使用不同视场，不能因两者 shape 相同而交换。

| 模型视图 | fx / fy | cx | cy |
|---|---:|---:|---:|
| MED / `img` | 910 | 256 | 47.6 |
| SBIG / `big_img` | 455 | 256 | 151.8 |

以下 `Y[row,column]` 指 warp 后的亮度图；每个 plane 按行连续，共 `32768` B：

| 通道 | 名称 | `plane[r,c]` |
|---:|---|---|
| 0 | Y00 | `Y[2*r,2*c]` |
| 1 | Y10 | `Y[2*r+1,2*c]` |
| 2 | Y01 | `Y[2*r,2*c+1]` |
| 3 | Y11 | `Y[2*r+1,2*c+1]` |
| 4 | U | 对应的色度 U |
| 5 | V | 对应的色度 V |

单路当前帧为 `196608` B。沿通道轴连接 `[older,current]` 得到 12 planes；前 6 个通道来自 `t-4`，后 6 个来自 `t`。它不是 RGB、交错 NV12 或 JPEG 字节流。

外部 `new_img` 只提供两路当前帧，合计 `393216` B；两路配对图由图内历史队列构造。

输入保持原始 `0…255` 字节。模型内部先将两路配对图拼接成 24 通道，转 FP16，再逐通道执行 `(x - 127.5) / 63.75`，对应范围 `[-2,2]`。归一化常量 `_mean`、`_std` 均为 `[1,24,1,1]`，所有通道分别取 `127.5`、`63.75`。调用者不预先归一化。

## 4. 跨帧状态契约

名义推理频率为 20 Hz，历史采样间隔 4 帧，对应 5 Hz context。这里的帧序号是连续模型执行序号；模型没有 timestamp 输入，不会自动插入缺失帧。

### 4.1 三种队列

| 状态 | 完整逻辑队列 | 输入采样方法 |
|---|---|---|
| 图像 | 每路 5 帧 packed6 | 先追加当前图，再取第 0、4 帧：`[t-4,t]` |
| feature | 128 帧，每帧 `[32,512]` | 推理前从最旧端取 `[0,4,…,124]`，得到 `[1,32,32,512]` |
| desire | 132 个 8 维 pulse | 先追加当前 pulse，按最旧到最新分成 33 组，每 4 个逐通道取 max |

执行第 `t` 帧时，采样后的 feature 历史为 `h[t-128],h[t-124],…,h[t-4]`，再与当前视觉特征一起送入时序网络。`next_state_feat_q` 移除最旧一帧，并追加当前 `h[t]`。**历史采样发生在追加当前特征之前，不能改成最近 32 个连续帧。**

`outputs[:,2066:18450]` 为当前视觉特征 `view_39` 的平铺，经最终 cast 输出，可 reshape 为 `[1,32,512]`。它不是额外的 RNN hidden 输出。外部 `state_feat_q` 使用 FP32，但写入的新特征来自 FP16。

### 4.2 Desire

调用者根据当前类别 `d` 生成 8 维 pulse：当 `d != 0 && d != previousDesire` 时，对应通道为 1，其余为 0，然后更新 `previousDesire=d`。将该 pulse 作为外部 `desire` 输入。持续保持同一个类别只在首次产生 pulse；0 通道始终不产生 pulse。

图内先追加本次 pulse，再对最近 132 个 pulse 分组 max pooling。第 `j` 组覆盖 `p[t-131+4*j]…p[t-128+4*j]`，`j=0…32`；最后一组为 `p[t-3]…p[t]`。因此本次 desire 会参与本次推理。

| index | 含义 |
|---:|---|
| 0 | none |
| 1 / 2 | turnLeft / turnRight |
| 3 / 4 | laneChangeLeft / laneChangeRight |
| 5 / 6 | keepLeft / keepRight |
| 7 | 第八个通道；本文未确认其名称，不自行赋予语义 |

### 4.3 初始化、顺序与 reset

新序列清零三种队列及 `previousDesire`。前 4 次推理的 older 图全零；第 5 次才出现首帧图像和首帧 hidden 的历史反馈。零历史填的是 byte `0`，不是中性灰 `127.5`。

同一序列须按时间顺序传递 `next_state_*`，不能混入其他序列的历史。切换模型、开始新序列或丢失状态连续性时，重新清零三个队列及调用者维护的 `previousDesire`。

## 5. 原始输出布局

`outputs` 为 `float32[1,18452]`，共 `73808` B。下表省略 batch；`μ + logσ` 表示**先存全部均值，再存全部 log 标准差**，不是逐元素交错。标准差按 `σ=exp(logσ)` 解码。

| head | start | end | 元素数 | 解码后的 shape / 含义 |
|---|---:|---:|---:|---|
| `lane_lines` | 0 | 528 | 528 | `μ[4,33,2] + logσ[4,33,2]`，每点 `(y,z)` |
| `lane_lines_prob` | 528 | 536 | 8 | 8 个独立 sigmoid logits；每条线取相对索引 `2*i+1` |
| `road_edges` | 536 | 800 | 264 | `μ[2,33,2] + logσ[2,33,2]`，每点 `(y,z)` |
| `meta` | 800 | 855 | 55 | 55 个独立 sigmoid logits，见下表 |
| `desire_pred` | 855 | 887 | 32 | `[4,8]`，逐行 softmax |
| `pose` | 887 | 899 | 12 | `μ[6] + logσ[6]`；线速度 xyz、角速度 xyz |
| `wide_from_device_euler` | 899 | 905 | 6 | `μ[3] + logσ[3]`；roll/pitch/yaw，rad |
| `road_transform` | 905 | 917 | 12 | `μ[6] + logσ[6]`；前三个均值为平移分量，m |
| `plan` | 917 | 1907 | 990 | `μ[33,15] + logσ[33,15]` |
| `lead` | 1907 | 2051 | 144 | `μ[3,6,4] + logσ[3,6,4]`，每点 `(x,y,v,a)` |
| `lead_prob` | 2051 | 2054 | 3 | 三个独立 sigmoid logits |
| `desire_state` | 2054 | 2062 | 8 | `[8]` softmax |
| `action` | 2062 | 2066 | 4 | 横向加速度、纵向加速度及对应两个 logσ |
| `hidden_state` | 2066 | 18450 | 16384 | `[32,512]`，原样用于时序反馈 |
| `pad` | 18450 | 18452 | 2 | 保留 padding，解析时忽略，原始输出中保留 |

不要对整个输出统一 sigmoid/softmax。`lane_lines_prob` 也不是把每两个值做二分类 softmax。`plan` 和 `lead` 已完成候选选择，不再按旧 MHP 数量解包或 argmax。

### 5.1 Plan、坐标与采样

| plan 每点列 | 字段 | 单位 |
|---|---|---|
| `[0,3)` | position x/y/z | m |
| `[3,6)` | velocity x/y/z | m/s |
| `[6,9)` | acceleration x/y/z | m/s² |
| `[9,12)` | 相对当前姿态 Euler roll/pitch/yaw | rad |
| `[12,15)` | orientation rate x/y/z | rad/s |

33 个 plan 时间点为 `T[i]=10*(i/32)^2` 秒，`i=0…32`，并非等间隔。车道线/道路边缘的 33 个纵向位置为 `X[i]=192*(i/32)^2` 米；x 不存储在各自 head 中。车道线顺序为左外、左内、右内、右外，道路边缘为左、右。

模型道路坐标为 x 前、y 右、z 下。`pose` 的前三个均值为线速度，单位 m/s，后三个为角速度，单位 rad/s，不应直接当逐帧位移。`road_transform` 后三个均值的具体语义尚未确认，保留原值。

### 5.2 Lead 与 action

三个 lead slot 的概率对应时间分别为 `0,2,4` 秒；每个 slot 自身的六个轨迹时间均为 `0,2,4,6,8,10` 秒，不再加上概率对应时间。slot 不是持久车辆 ID。

lead `(x,y)` 的单位为米，`v` 为前车模型速度（m/s），不是相对本车速度；`a` 为 m/s²。

```text
action[0] = lateral_acceleration_mean       # m/s²
action[1] = longitudinal_acceleration_mean  # m/s²
action[2] = lateral_acceleration_log_std
action[3] = longitudinal_acceleration_log_std
```

`action[0]` 不是曲率或方向盘角，正值向右、负值向左；`action[1]` 正值加速、负值减速。后两个值是对应加速度分布的 log 标准差，不是额外动作。

### 5.3 Meta 的 55 个 logits

下表索引相对于 `meta.start=800`；均先逐元素 sigmoid。

| 相对索引 | 含义 | 时间 |
|---|---|---|
| `0` | engaged probability | 当前 |
| `1+6*k` | gas disengage | `k=0…4` → 2/4/6/8/10 s |
| `2+6*k` | brake disengage | 同上 |
| `3+6*k` | steer override | 同上 |
| `4+6*k` | hard brake 3 m/s² | 同上 |
| `5+6*k` | hard brake 4 m/s² | 同上 |
| `6+6*k` | hard brake 5 m/s² | 同上 |
| `31+4*k` | gas press | `k=0…5` → 0/2/4/6/8/10 s |
| `32+4*k` | brake press | 同上 |
| `33+4*k` | left blinker | 同上 |
| `34+4*k` | right blinker | 同上 |

`desire_pred` 的四行时间定义尚未确认，本文只约定 `[4,8]` 与逐行 softmax，不套用 meta 时间轴。

## 6. 最小输出解析示例

下面直接接收模型返回的 `outputs` NumPy 数组，并按本版本切片。示例保留所有原始 head，另解码 plan、lead、action 和 hidden。

```python
import numpy as np

SLICES = {
    "lane_lines": (0, 528),
    "lane_lines_prob": (528, 536),
    "road_edges": (536, 800),
    "meta": (800, 855),
    "desire_pred": (855, 887),
    "pose": (887, 899),
    "wide_from_device_euler": (899, 905),
    "road_transform": (905, 917),
    "plan": (917, 1907),
    "lead": (1907, 2051),
    "lead_prob": (2051, 2054),
    "desire_state": (2054, 2062),
    "action": (2062, 2066),
    "hidden_state": (2066, 18450),
    "pad": (18450, 18452),
}


def decode_output(outputs):
    raw = np.asarray(outputs)
    if raw.shape != (1, 18452) or raw.dtype != np.dtype("float32"):
        raise ValueError("expected float32[1,18452]")
    if not np.isfinite(raw).all():
        raise ValueError("non-finite output")
    # 独立副本，后续激活或变换不会改写原始输出。
    heads = {name: raw[:, start:end].copy()
             for name, (start, end) in SLICES.items()}
    plan = heads["plan"][:, :495].reshape(1, 33, 15)
    plan_std = np.exp(heads["plan"][:, 495:]).reshape(1, 33, 15)
    lead = heads["lead"][:, :72].reshape(1, 3, 6, 4)
    lead_std = np.exp(heads["lead"][:, 72:]).reshape(1, 3, 6, 4)
    action_mean = heads["action"][:, :2]
    hidden = heads["hidden_state"].reshape(1, 32, 512)
    return heads, plan, plan_std, lead, lead_std, action_mean, hidden
```

完整 ONNX 已在 `next_state_feat_q` 中包含本帧 hidden。继续推理时传递完整 `next_state_*`，不需要根据示例中的 `hidden` 再手动推进一次队列。
