#!/usr/bin/env python3
"""Export opt-in Cinque3 QNN fusion candidates; never overwrite the deployed model.

attention: commute a positive scalar Mul across a -inf Where mask, exposing
QNN EP 2.6's Mul->Softmax beta fusion. ONNX pointwise FP16 rounding is preserved;
the fused backend kernel still needs independent numerical validation.
linear: MatMul+constant bias -> Reshape/Gemm/Reshape, exposing QNN FullyConnected.
This changes intermediate FP16 rounding and is explicitly experimental.
layout: cancel an inverse Transpose/Gather/Transpose sandwich (vector indices).
qk: absorb a last-two-axis key Transpose into com.microsoft.FusedMatMul transB.
last-query: specialize the last policy transformer blocks to their only used
query, retaining every key/value token and the original per-token arithmetic.
heads: pack independent Gemm output heads with the same input into one Gemm,
then split the output; concatenation preserves every original weight value.
vision-conv: lower NHWC pointwise MatMul+bias to 1x1 Conv with lossless weight
repacking, allowing the backend to choose its convolution implementation.
image-quantize: replace the pixel queue FP16->FP32->UINT8 cast chain with an
exact scale=1, zero=0 QuantizeLinear. This does not quantize network weights.
pixel-qdq: carry that lossless unit encoding through pixel routing operations,
allowing QNN to fuse Q/DQ into an 8-bit queue and layout path.
additive-mask: replace Where(constant mask, -inf, x) with Add(x, 0/-inf bias).
Exact for finite and -inf scores; QNN HTP runs this bool Where very slowly.
No weights are quantized, no state updates leave the graph, and ABI is unchanged.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import tempfile

import numpy as np
import onnx
from onnx import helper, numpy_helper

from prepare_model import ROOT, sha256_file, validate_abi, operator_inventory

BASE_SHA256 = "86890bf95af82adbcc85f20f3a60acda3bffc852224bfb00afdbb81ee2f4a677"


def attrs(node):
    return {a.name: helper.get_attribute_value(a) for a in node.attribute}


def index(model):
    producers = {o: n for n in model.graph.node for o in n.output}
    consumers = defaultdict(list)
    for n in model.graph.node:
        for i in n.input:
            consumers[i].append(n)
    # Graph outputs are observable consumers: never absorb these intermediates.
    for o in model.graph.output:
        consumers[o.name].append(None)
    constants = {t.name: numpy_helper.to_array(t) for t in model.graph.initializer}
    return producers, consumers, constants


def replace_nodes(model, replacements, removed):
    nodes = []
    for n in model.graph.node:
        if n.output[0] in replacements:
            nodes.extend(replacements[n.output[0]])
        elif n.output[0] not in removed:
            nodes.append(n)
    del model.graph.node[:]
    model.graph.node.extend(nodes)
    live = {v.name for v in [*model.graph.input, *model.graph.output, *model.graph.initializer]}
    live.update(o for n in nodes for o in n.output)
    infos = [v for v in model.graph.value_info if v.name in live]
    del model.graph.value_info[:]
    model.graph.value_info.extend(infos)


def attention_scale(model):
    producers, consumers, constants = index(model)
    replacements, removed, changes = {}, set(), []
    names = set(producers) | set(constants) | {i.name for i in model.graph.input}
    for softmax in model.graph.node:
        if softmax.domain or softmax.op_type != "Softmax":
            continue
        mask = producers.get(softmax.input[0])
        if mask is None or mask.domain or mask.op_type != "Where" or len(consumers[mask.output[0]]) != 1:
            continue
        fill = constants.get(mask.input[1])
        if fill is None or fill.size != 1 or not np.isneginf(fill).all():
            continue
        mul = producers.get(mask.input[2])
        if mul is None or mul.domain or mul.op_type != "Mul" or len(consumers[mul.output[0]]) != 1:
            continue
        const_inputs = [i for i in mul.input if i in constants]
        if len(const_inputs) != 1:
            continue
        scale_name = const_inputs[0]
        scale = constants[scale_name]
        if scale.size != 1 or not np.isfinite(scale).all() or not (scale > 0).all() or scale.dtype != fill.dtype:
            continue
        data = mul.input[1] if mul.input[0] == scale_name else mul.input[0]
        unscaled = mask.output[0] + "_opif_unscaled"
        if unscaled in names:
            raise ValueError(f"Fusion name collision: {unscaled}")
        names.add(unscaled)
        replacements[mask.output[0]] = [
            helper.make_node("Where", [mask.input[0], mask.input[1], data], [unscaled], name=mask.name + "_before_scale"),
            helper.make_node("Mul", [unscaled, scale_name], list(mask.output), name=mul.name + "_softmax_beta"),
        ]
        removed.add(mul.output[0])
        changes.append({"pass": "attention", "softmax": softmax.name, "scale": float(scale.item()),
                        "qnn_candidate": "Mul->Softmax", "pointwise_rounding_preserved": True})
    replace_nodes(model, replacements, removed)
    return changes


def additive_mask(model):
    producers, consumers, constants = index(model)
    replacements, changes, biases, nots = {}, [], {}, defaultdict(set)
    names = set(producers) | set(constants) | {i.name for i in model.graph.input}
    for where in model.graph.node:
        if where.domain or where.op_type != "Where":
            continue
        cond, invert = where.input[0], False
        mask = constants.get(cond)
        if mask is None and cond in producers and producers[cond].op_type == "Not" and not producers[cond].domain:
            cond, invert = producers[cond].input[0], True
            mask = constants.get(cond)
        if mask is None or mask.dtype != np.bool_:
            continue
        # Exactly one branch must be a scalar -inf; the other is the kept score.
        for fill_at, data_at in ((1, 2), (2, 1)):
            fill = constants.get(where.input[fill_at])
            if fill is not None and fill.size == 1 and np.isneginf(fill).all() and where.input[data_at] not in constants:
                break
        else:
            continue
        masked = np.logical_not(mask) if invert else mask
        if fill_at == 2:
            masked = np.logical_not(masked)
        key = (masked.tobytes(), masked.shape, fill.dtype.str)
        if key not in biases:
            bias = f"opif_additive_mask_{len(biases)}"
            if bias in names:
                raise ValueError(f"Fusion name collision: {bias}")
            names.add(bias)
            model.graph.initializer.append(numpy_helper.from_array(
                np.where(masked, -np.inf, 0).astype(fill.dtype), bias))
            biases[key] = bias
        replacements[where.output[0]] = [helper.make_node(
            "Add", [where.input[data_at], biases[key]], list(where.output), name=where.name + "_additive_mask")]
        if invert:
            nots[where.input[0]].add(where.output[0])
        changes.append({"pass": "additive-mask", "where": where.name, "bias": biases[key],
                        "masked_elements": int(masked.sum()), "exact_for_finite_scores": True})
    # A Not is removed only when every consumer was one of the rewritten Wheres.
    removed = {n for n, outs in nots.items()
               if all(c is not None and c.output[0] in outs for c in consumers[n])}
    replace_nodes(model, replacements, removed)
    return changes


def layout_gather(model):
    producers, consumers, constants = index(model)
    replacements, removed, changes = {}, set(), []
    for tail in model.graph.node:
        if tail.domain or tail.op_type != "Transpose":
            continue
        gather = producers.get(tail.input[0])
        if gather is None or gather.domain or gather.op_type != "Gather" or len(consumers[gather.output[0]]) != 1:
            continue
        head = producers.get(gather.input[0])
        indices = constants.get(gather.input[1])
        if head is None or head.domain or head.op_type != "Transpose" or len(consumers[head.output[0]]) != 1 or indices is None or indices.ndim != 1:
            continue
        p, q = attrs(head).get("perm"), attrs(tail).get("perm")
        if p is None or q is None or len(p) != len(q) or [p[i] for i in q] != list(range(len(p))):
            continue
        axis = attrs(gather).get("axis", 0) % len(p)
        replacements[tail.output[0]] = [helper.make_node("Gather", [head.input[0], gather.input[1]], list(tail.output), name=gather.name + "_no_transposes", axis=p[axis])]
        removed.update([head.output[0], gather.output[0]])
        changes.append({"pass": "layout", "node": gather.name, "removed_transposes": 2})
    replace_nodes(model, replacements, removed)
    return changes


def linear_gemm(model, scope="all"):
    producers, consumers, constants = index(model)
    shapes = {v.name: [d.dim_value for d in v.type.tensor_type.shape.dim]
              for v in [*model.graph.input, *model.graph.value_info, *model.graph.output]}
    replacements, removed, changes = {}, set(), []
    names = set(producers) | set(constants) | {i.name for i in model.graph.input}
    for add in model.graph.node:
        if add.domain or add.op_type != "Add":
            continue
        pair = [(producers.get(add.input[i]), add.input[1-i]) for i in (0, 1)]
        pair = [(m, b) for m, b in pair if m is not None and not m.domain and m.op_type == "MatMul" and b in constants]
        if len(pair) != 1:
            continue
        mm, bias_name = pair[0]
        if len(consumers[mm.output[0]]) != 1 or mm.input[1] not in constants:
            continue
        if scope == "vision" and not bias_name.startswith("model.vision."):
            continue
        if scope == "policy" and bias_name.startswith("model.vision."):
            continue
        shape = shapes.get(mm.input[0])
        weight, bias = constants[mm.input[1]], constants[bias_name]
        if not shape or not 2 <= len(shape) <= 4 or min(shape) <= 0 or weight.ndim != 2 or bias.ndim != 1 or shape[-1] != weight.shape[0] or bias.shape[0] != weight.shape[1]:
            continue
        if weight.dtype != bias.dtype or weight.dtype not in (np.float16, np.float32):
            continue
        prefix = add.output[0] + "_opif_fc"
        fresh = [prefix + s for s in ("_in", "_out", "_in_shape", "_out_shape")]
        if any(n in names for n in fresh):
            raise ValueError(f"Fusion name collision: {prefix}")
        names.update(fresh)
        flat_in, flat_out, in_shape, out_shape = fresh
        output_shape = [*shape[:-1], int(weight.shape[1])]
        model.graph.initializer.extend([
            numpy_helper.from_array(np.array([int(np.prod(shape[:-1])), shape[-1]], np.int64), in_shape),
            numpy_helper.from_array(np.array(output_shape, np.int64), out_shape)])
        replacements[add.output[0]] = [
            helper.make_node("Reshape", [mm.input[0], in_shape], [flat_in], name=prefix + "_flatten"),
            helper.make_node("Gemm", [flat_in, mm.input[1], bias_name], [flat_out], name=prefix + "_gemm", alpha=1.0, beta=1.0, transA=0, transB=0),
            helper.make_node("Reshape", [flat_out, out_shape], list(add.output), name=prefix + "_restore")]
        removed.add(mm.output[0])
        changes.append({"pass": "linear", "node": add.name, "shape": shape, "out_channels": int(weight.shape[1]),
                        "qnn_candidate": "Reshape->Gemm->Reshape", "pointwise_rounding_preserved": False})
    replace_nodes(model, replacements, removed)
    return changes


def qk_transpose(model):
    producers, consumers, _ = index(model)
    replacements, removed, changes = {}, set(), []
    for mm in model.graph.node:
        if mm.domain or mm.op_type != "MatMul":
            continue
        transpose = producers.get(mm.input[1])
        if transpose is None or transpose.domain or transpose.op_type != "Transpose" or len(consumers[transpose.output[0]]) != 1:
            continue
        perm = attrs(transpose).get("perm")
        if perm is None or len(perm) < 2 or list(perm) != [*range(len(perm)-2), len(perm)-1, len(perm)-2]:
            continue
        replacements[mm.output[0]] = [helper.make_node(
            "FusedMatMul", [mm.input[0], transpose.input[0]], list(mm.output),
            name=mm.name + "_transpose_b", domain="com.microsoft", alpha=1.0, transA=0, transB=1)]
        removed.add(transpose.output[0])
        changes.append({"pass": "qk", "node": mm.name, "removed_transpose": transpose.name,
                        "qnn_candidate": "MatMul(transpose_in1=true)", "pointwise_rounding_preserved": True})
    replace_nodes(model, replacements, removed)
    if changes and not any(i.domain == "com.microsoft" for i in model.opset_import):
        model.opset_import.append(helper.make_opsetid("com.microsoft", 1))
    return changes


def last_query(model, query_tokens=1):
    """Pinned graph specialization, not truncation of attention history.

    The final Gather selects token 287. From Q normalization through residual
    MLP, every query row is independent; the attention matmuls retain full K/V.
    Refuse extra observers or an altered mask, rather than silently dropping
    computation that a different model could still need.
    """
    if query_tokens not in (1, 8, 16, 32, 64):
        raise ValueError("Final-query tile must be 1, 8, 16, 32 or 64")
    producers, consumers, constants = index(model)
    values = {v.name: v for v in [*model.graph.input, *model.graph.value_info, *model.graph.output]}
    replacements, changes = {}, []
    branches = [
        ("off", "layer_norm_59", "matmul_6", "mul_40", "masked_fill_3", "softmax_3", "matmul_7", "transpose_9", "_unsafe_view_5", "add_51", "add_52", "add_53", "select_4"),
        ("on", "layer_norm_82", "matmul_14", "mul_47", "masked_fill_7", "softmax_7", "matmul_15", "transpose_17", "_unsafe_view_9", "add_71", "add_72", "add_73", "select_7"),
    ]
    for branch, qnorm, score, scale, mask, softmax, av, trans, view, residual, add, final, selected in branches:
        for name in (qnorm, score, scale, mask, softmax, av, trans, view, residual, add, final, selected):
            if name not in producers or name not in values:
                raise ValueError(f"Missing pinned final-query tensor {name}")
        gather = producers[selected]
        if gather.op_type != "Gather" or attrs(gather).get("axis") != 1 or gather.input[0] != final or constants[gather.input[1]].shape != () or constants[gather.input[1]].item() != 287:
            raise ValueError("Expected final Gather(axis=1, index=287)")
        if producers[qnorm].op_type != "LayerNormalization" or attrs(producers[qnorm]).get("axis") != -1:
            raise ValueError("Q normalization must be per head, last dimension")
        # Only the final query is observed. Extra tile rows may be computed
        # unmasked because no subsequent operation mixes them into that query.
        where = producers[mask]
        not_node = producers.get(where.input[0])
        if where.op_type != "Where" or where.input[2] != scale or not_node is None or not_node.op_type != "Not":
            raise ValueError("Expected original attention masking chain")
        mask_data = constants[not_node.input[0]]
        if mask_data.shape != (1, 1, 288, 288) or not mask_data[:, :, 287:288, :].all():
            raise ValueError("Final query must attend to all original 288 keys")
        nodes = list(model.graph.node)
        start = next(i for i, n in enumerate(nodes) if n.output[0] == view)
        end = next(i for i, n in enumerate(nodes) if n.output[0] == final)
        token_nodes = nodes[start:end+1]
        if any(n.op_type not in {"Reshape", "MatMul", "Add", "LayerNormalization", "Gelu"} for n in token_nodes):
            raise ValueError("Unexpected operation in final token-local MLP")
        for n in token_nodes:
            if n.op_type == "LayerNormalization" and attrs(n).get("axis") != -1:
                raise ValueError("MLP normalization mixes token rows")
            if n.op_type == "MatMul" and n.input[1] not in constants:
                raise ValueError("MLP MatMul must have constant weights")
        changed = {qnorm, score, scale, mask, softmax, av, trans, *(n.output[0] for n in token_nodes)}
        for name in changed:
            for user in consumers[name]:
                if user is None or user.output[0] not in changed | {selected}:
                    raise ValueError(f"Final-query intermediate has another observer: {name}")
        prefix = f"opif_{branch}_last_query"
        fresh = [prefix + s for s in ("_index", "_zero", "_shape", "_q", "_residual")]
        if any(n in producers or n in constants for n in fresh):
            raise ValueError("Final-query name collision")
        idx, zero, shape, q, res = fresh
        model.graph.initializer.extend([
            numpy_helper.from_array(np.arange(288-query_tokens, 288, dtype=np.int64), idx),
            numpy_helper.from_array(np.array(query_tokens-1, np.int64), zero),
            numpy_helper.from_array(np.array([1, query_tokens, 512], np.int64), shape)])
        qnode = producers[qnorm]
        old_q = qnode.input[0]
        qnode.input[0] = q
        replacements[qnorm] = [helper.make_node("Gather", [old_q, idx], [q], name=prefix + "_gather_q", axis=2), qnode]
        add_node = producers[add]
        if residual not in add_node.input:
            raise ValueError("Expected final attention residual input")
        add_node.input[list(add_node.input).index(residual)] = res
        replacements[add] = [helper.make_node("Gather", [residual, idx], [res], name=prefix + "_gather_residual", axis=1), add_node]
        replacements[mask] = [helper.make_node("Identity", [scale], [mask], name=prefix + "_unmasked")]
        producers[view].input[1] = shape
        gather.input[1] = zero
        for name in changed:
            dims = values[name].type.tensor_type.shape.dim
            axis = 2 if name in {qnorm, score, scale, mask, softmax, av} else 1
            if dims[axis].dim_value != 288:
                raise ValueError(f"Unexpected final query dimension: {name}")
            dims[axis].dim_value = query_tokens
        # Estimate removed MACs from QK, AV, attention projection and two MLP FCs.
        macs = (288-query_tokens) * (2 * 8 * 288 * 64 + 512 * 512 + 2 * 512 * 1024)
        changes.append({"pass": "last-query", "branch": branch, "query_tokens_before": 288,
                        "query_tokens_after": query_tokens, "key_value_tokens": 288,
                        "removed_macs": macs, "original_initializers_unchanged": True})
    replace_nodes(model, replacements, set())
    # Remove newly dead constant mask operations with a reverse liveness walk.
    live = {o.name for o in model.graph.output}
    keep = []
    for node in reversed(model.graph.node):
        if any(o in live for o in node.output):
            keep.append(node)
            live.update(node.input)
    keep.reverse()
    del model.graph.node[:]
    model.graph.node.extend(keep)
    replace_nodes(model, {}, set())
    return changes


def pack_heads(model):
    producers, _, constants = index(model)
    groups = defaultdict(list)
    for node in model.graph.node:
        if node.domain or node.op_type != "Gemm" or len(node.input) != 3 or len(node.output) != 1:
            continue
        a = attrs(node)
        if (a.get("transA", 0), a.get("transB", 0), a.get("alpha", 1.0), a.get("beta", 1.0)) != (0, 1, 1.0, 1.0):
            continue
        if node.input[1] not in constants or node.input[2] not in constants:
            continue
        w, b = constants[node.input[1]], constants[node.input[2]]
        if w.ndim != 2 or b.shape != (w.shape[0],) or w.dtype != b.dtype:
            continue
        groups[(node.input[0], w.shape[1], str(w.dtype))].append(node)
    replacements, removed, changes = {}, set(), []
    for (data, _, _), nodes in groups.items():
        if len(nodes) < 2:
            continue
        prefix = nodes[0].output[0] + "_opif_packed_heads"
        names = [prefix + s for s in ("_w", "_b", "_sizes", "_out")]
        if any(n in producers or n in constants for n in names):
            raise ValueError("Packed-head name collision")
        weights, biases, sizes, packed = names
        lengths = [constants[n.input[1]].shape[0] for n in nodes]
        model.graph.initializer.extend([
            numpy_helper.from_array(np.concatenate([constants[n.input[1]] for n in nodes], axis=0), weights),
            numpy_helper.from_array(np.concatenate([constants[n.input[2]] for n in nodes]), biases),
            numpy_helper.from_array(np.array(lengths, np.int64), sizes)])
        replacements[nodes[0].output[0]] = [
            helper.make_node("Gemm", [data, weights, biases], [packed], name=prefix + "_gemm", transA=0, transB=1, alpha=1.0, beta=1.0),
            helper.make_node("Split", [packed, sizes], [n.output[0] for n in nodes], name=prefix + "_split", axis=1)]
        removed.update(n.output[0] for n in nodes[1:])
        changes.append({"pass": "heads", "input": data, "heads": len(nodes), "widths": lengths,
                        "weight_values_preserved": True, "backend_rounding_requires_validation": True})
    replace_nodes(model, replacements, removed)
    return changes


def vision_conv(model):
    producers, consumers, constants = index(model)
    shapes = {v.name: [d.dim_value for d in v.type.tensor_type.shape.dim]
              for v in [*model.graph.input, *model.graph.value_info, *model.graph.output]}
    replacements, removed, changes = {}, set(), []
    for add in model.graph.node:
        if add.domain or add.op_type != "Add":
            continue
        matches = [(producers.get(add.input[i]), add.input[1-i]) for i in (0, 1)]
        matches = [(mm, bias) for mm, bias in matches if mm is not None and not mm.domain and mm.op_type == "MatMul"
                   and (bias.startswith("model.vision.") or
                        (bias.endswith("_folded_scale_bias") and mm.input[1] == bias.removesuffix("_bias") + "_weight"))
                   and bias in constants]
        if len(matches) != 1:
            continue
        mm, bias = matches[0]
        shape = shapes.get(mm.input[0])
        if len(consumers[mm.output[0]]) != 1 or mm.input[1] not in constants or not shape or len(shape) != 4 or min(shape) <= 0:
            continue
        w, b = constants[mm.input[1]], constants[bias]
        if w.ndim != 2 or w.shape[0] != shape[-1] or b.shape != (w.shape[1],) or w.dtype != b.dtype:
            continue
        prefix = add.output[0] + "_opif_conv1x1"
        weight, inp, out = [prefix+s for s in ("_w", "_in", "_out")]
        if any(n in producers or n in constants for n in (weight, inp, out)):
            raise ValueError("Pointwise-convolution name collision")
        model.graph.initializer.append(numpy_helper.from_array(w.T.copy().reshape(w.shape[1], w.shape[0], 1, 1), weight))
        replacements[add.output[0]] = [
            helper.make_node("Transpose", [mm.input[0]], [inp], name=prefix+"_to_nchw", perm=[0, 3, 1, 2]),
            helper.make_node("Conv", [inp, weight, bias], [out], name=prefix, kernel_shape=[1, 1], strides=[1, 1], pads=[0, 0, 0, 0], dilations=[1, 1], group=1),
            helper.make_node("Transpose", [out], list(add.output), name=prefix+"_to_nhwc", perm=[0, 2, 3, 1])]
        removed.add(mm.output[0])
        changes.append({"pass": "vision-conv", "node": add.name, "input_shape": shape,
                        "weight_shape": list(w.shape), "weight_values_preserved": True})
    replace_nodes(model, replacements, removed)
    return changes


def image_quantize(model):
    producers, consumers, constants = index(model)
    out = producers.get("next_state_img_q")
    if out is None or out.op_type != "Cast" or attrs(out).get("to") != onnx.TensorProto.UINT8:
        raise ValueError("Expected UINT8 image-state output cast")
    bridge = producers.get(out.input[0])
    if bridge is None or bridge.op_type != "Cast" or attrs(bridge).get("to") != onnx.TensorProto.FLOAT or len(consumers[bridge.output[0]]) != 1:
        raise ValueError("Expected sole FP16 -> FP32 output bridge")
    if bridge.input[0] != "openpilot_image_fp16_next_state_img_q":
        raise ValueError("Expected pinned lossless pixel routing")
    scale, zero = "opif_pixel_unit_scale", "opif_pixel_zero"
    if any(n in constants or n in producers for n in (scale, zero)):
        raise ValueError("Pixel conversion name collision")
    model.graph.initializer.extend([
        numpy_helper.from_array(np.array(1, np.float16), scale),
        numpy_helper.from_array(np.array(0, np.uint8), zero)])
    node = helper.make_node("QuantizeLinear", [bridge.input[0], scale, zero], list(out.output), name="opif_pixel_queue_convert")
    replace_nodes(model, {out.output[0]: [node]}, {bridge.output[0]})
    return [{"pass": "image-quantize", "scale": 1, "zero_point": 0,
             "pixel_domain": "integer 0..255", "network_weights_quantized": False}]


def pixel_qdq(model):
    """Describe lossless UINT8 pixel routing as QDQ fixed-point operations.

    Raw QNN UINT8 routing is unsupported on this HTP; UFIXED8 with scale=1 is
    a distinct backend type. Every routed value remains an integer in 0..255.
    Arithmetic is outside this pass; only copy/index/reshape operations qualify.
    """
    producers, consumers, constants = index(model)
    scale, zero = "opif_routing_scale", "opif_routing_zero"
    if any(n in producers or n in constants for n in (scale, zero)):
        raise ValueError("Pixel QDQ constant name collision")
    model.graph.initializer.extend([
        numpy_helper.from_array(np.array(1, np.float16), scale),
        numpy_helper.from_array(np.array(0, np.uint8), zero)])
    allowed = {"Slice", "Unsqueeze", "Squeeze", "Concat", "Gather", "Reshape", "Transpose", "Identity"}
    reachable = set()
    nodes, routed = [], []
    inputs = {"new_img", "state_img_q"}
    bridge = "openpilot_image_fp32_next_state_img_q"
    if len(consumers[bridge]) != 1 or consumers[bridge][0].output[0] != "next_state_img_q":
        raise ValueError("Unexpected observer of pixel output bridge")
    for node in model.graph.node:
        if node.op_type == "Cast" and node.input[0] in inputs:
            if attrs(node).get("to") != onnx.TensorProto.FLOAT16:
                raise ValueError("Expected FP16 pixel input widening")
            nodes.append(helper.make_node("DequantizeLinear", [node.input[0], scale, zero], list(node.output), name=node.name+"_unit_dq"))
            reachable.add(node.output[0])
            continue
        if node.output[0] in {bridge, "next_state_img_q"}:
            if node.op_type != "Cast":
                raise ValueError("Expected original pixel output bridge")
            continue
        data_inputs = list(node.input) if node.op_type == "Concat" else list(node.input[:1])
        if not node.domain and node.op_type in allowed and data_inputs and all(i in reachable for i in data_inputs):
            if len(node.output) != 1:
                raise ValueError("Unexpected multi-output pixel operation")
            name = node.output[0]
            wide, narrow = name+"_opif_qdq_wide", name+"_opif_qdq_u8"
            if name == "openpilot_image_fp16_next_state_img_q": narrow = "next_state_img_q"
            if any(n in producers or n in constants for n in (wide, narrow) if n != "next_state_img_q"):
                raise ValueError("Pixel QDQ tensor name collision")
            node.output[0] = wide
            nodes.extend([node,
                          helper.make_node("QuantizeLinear", [wide, scale, zero], [narrow], name=node.name+"_unit_q"),
                          helper.make_node("DequantizeLinear", [narrow, scale, zero], [name], name=node.name+"_unit_dq")])
            reachable.add(name)
            routed.append(node.name)
        else:
            nodes.append(node)
    if "openpilot_image_fp16_next_state_img_q" not in reachable or "_to_copy_4" not in reachable:
        raise ValueError("Incomplete lossless image-routing chain")
    del model.graph.node[:]
    model.graph.node.extend(nodes)
    replace_nodes(model, {}, set())
    return [{"pass": "pixel-qdq", "routed_nodes": routed, "scale": 1, "zero_point": 0,
             "network_weights_quantized": False, "pixel_values_exact": True}]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", type=Path, default=ROOT / ".cache/android-models/cinque3/model.onnx")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--passes", nargs="+", choices=["attention", "layout", "linear", "qk", "last-query", "heads", "vision-conv", "image-quantize", "pixel-qdq", "additive-mask"], required=True)
    p.add_argument("--linear-scope", choices=["all", "vision", "policy"], default="all")
    p.add_argument("--last-query-tokens", type=int, choices=[1, 8, 16, 32, 64], default=1,
                   help="Keep an NPU-friendly query tile; only its last output is observable")
    a = p.parse_args()
    if sha256_file(a.model) != BASE_SHA256:
        raise ValueError("Expected pinned, prepared Cinque3 baseline")
    if a.output.resolve() == a.model.parent.resolve():
        raise ValueError("Use a separate candidate directory")
    model = onnx.load(a.model)
    validate_abi(model)
    before = operator_inventory(model)
    weights_before = {t.name: t.SerializeToString() for t in model.graph.initializer}
    changes = []
    for name in dict.fromkeys(a.passes):
        changes.extend(last_query(model, a.last_query_tokens) if name == "last-query" else
                       linear_gemm(model, a.linear_scope) if name == "linear" else
                       {"attention": attention_scale, "layout": layout_gather, "qk": qk_transpose,
                        "last-query": last_query, "heads": pack_heads, "vision-conv": vision_conv,
                        "image-quantize": image_quantize, "pixel-qdq": pixel_qdq,
                        "additive-mask": additive_mask}[name](model))
    if not changes:
        raise ValueError("No matching fusion patterns")
    for t in model.graph.initializer:
        if t.name in weights_before and t.SerializeToString() != weights_before[t.name]:
            raise ValueError("Original initializer changed")
    # Weight repacking must not double the deployment size. Remove only tensors
    # with no node or graph-I/O references; original live values remain exact.
    used = {i for n in model.graph.node for i in n.input}
    used.update(v.name for v in [*model.graph.input, *model.graph.output])
    unused = [t.name for t in model.graph.initializer if t.name not in used]
    if {"vision-conv", "additive-mask"} & set(a.passes):
        kept = [t for t in model.graph.initializer if t.name in used]
        del model.graph.initializer[:]
        model.graph.initializer.extend(kept)
    validate_abi(model)
    onnx.checker.check_model(model, full_check=True)
    manifest = json.loads(a.model.with_name("manifest.json").read_text())
    manifest.update(operators_before=before, operators_after=operator_inventory(model))
    manifest["opsets"] = {i.domain or "ai.onnx": i.version for i in model.opset_import}
    manifest["initializers_by_dtype"] = dict(sorted(Counter(
        onnx.TensorProto.DataType.Name(t.data_type) for t in model.graph.initializer).items()))
    manifest["changes"] = {"baseline_sha256": BASE_SHA256, "fusion_candidates": changes,
                           "original_initializers_unchanged": True}
    if {"vision-conv", "additive-mask"} & set(a.passes):
        manifest["changes"]["removed_unused_initializers"] = unused
    manifest["target_validation"] = {"status": "not_run", "required_backend": "libQnnHtp.so", "cpu_ep_fallback": False}
    a.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".fusion-", dir=a.output) as tmp:
        path = Path(tmp) / "model.onnx"
        onnx.save(model, path)
        manifest["deployment_sha256"] = sha256_file(path)
        manifest["deployment_bytes"] = path.stat().st_size
        path.replace(a.output / "model.onnx")
        path = Path(tmp) / "manifest.json"
        path.write_text(json.dumps(manifest, indent=2) + "\n")
        path.replace(a.output / "manifest.json")
    print(json.dumps({"output": str(a.output), "changes": dict(Counter(c["pass"] for c in changes)),
                      "sha256": manifest["deployment_sha256"], "npu_validated": False}), flush=True)


if __name__ == "__main__":
    main()
