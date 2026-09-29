# Android ONNX 模型 patch

本包包含 prepare_model.py（原始 ONNX 的 Android 准备）、optimize_fusions.py（模型计算图优化）和依赖清单。不含模型权重。两个 Python 文件需放在同一目录。

## 使用方法

解压后进入本目录，使用 Python 3.10 或更新版本：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

# 1. 从原始 Cinque v3 big ONNX 生成 Android prepared 模型。
python prepare_model.py --source /absolute/path/to/original.onnx --output ./prepared

# 2. 对 prepared 模型执行最终采用的三个计算图改写。
python optimize_fusions.py --model ./prepared/model.onnx --passes last-query additive-mask pixel-qdq --output ./patched
```

如果已有 SHA256 匹配的 prepared 模型，可跳过步骤 1，直接将步骤 2 的 --model 指向该文件；其同目录必须有配套 manifest.json。
请显式传入 --source、--model、--output；脚本原有默认路径用于原仓库布局，不适用于本独立包。

交付产物为 patched/model.onnx 与 patched/manifest.json。替换模型时应一起使用；本脚本不会自动安装或更新 App。原始模型不会被覆盖。

## 模型校验

原始 ONNX SHA256：
404a18cfd86d29637d20c697dfde245bb47c666ae016730ab674c65f4d1e1aa4

prepared ONNX SHA256：
86890bf95af82adbcc85f20f3a60acda3bffc852224bfb00afdbb81ee2f4a677

最终 patched ONNX 参考 SHA256：
8cf7714f5d4f2601f273a7f4b7eddba25c9c6dbb8b38962c7600cda1fbd85961

可以用 shasum -a 256 文件路径 校验。脚本会拒绝不匹配的源模型；请勿删除 SHA 校验强行处理其他模型。依赖或序列化版本不同也可能影响文件 SHA，应先核实版本。

## 改了哪些计算

准备阶段：内联本地 ONNX 函数、将适用的 GatherND 改为 Gather、将常量负索引规范化、将像素搬运改为无损 FP16 内部表示，保留 UINT8 外部接口。

最终优化按以下顺序执行，不能交换：
1. last-query：两个 policy 最后 Transformer 块只计算最后一个 query 的后续路径，保留全部 288 个 K/V 和上游 Q 投影。合计减少 921,632,768 MAC。
2. additive-mask：余下六处 Where(Not(mask), -inf, scores) 改为 scores + 共享 FP16 0/-inf bias。有限 scores 下等价，不保证任意 NaN/+inf 输入等价。
3. pixel-qdq：11 个像素路由节点使用 scale=1、zero_point=0 的 Q/DQ，使 QNN 可融合为 UFIXED8 路由。0..255 整数像素无损，不是网络权重 INT8 量化。

训练权重数值、模型外部 ABI 和跨帧队列语义保持不变，状态更新仍在图内。脚本保留其他历史实验选项，本包的复现命令仅启用上述三项。

## 验证范围

本包脚本与仓库版本逐字节一致，已检查独立解压后的两个 CLI --help 可运行。此次打包未重新生成完整模型或进行真机验证。
