#!/usr/bin/env python3
"""Prepare the complete, pinned Cinque v3 big graph for strict QNN HTP loading.

This does not quantize, extract the neural network, or move state updates to the
host. Image routing uses lossless FP16 internally by default, with UINT8 I/O.
Eight constant attention masks use a shared FP16 Add bias by default.
QNN compatibility is established only by loading/running on the target.
Install the host dependency with ``python -m pip install onnx==1.22.0``.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile

import numpy as np
import onnx
from onnx import TensorProto, helper, inliner, numpy_helper


ROOT = Path(__file__).resolve().parents[2]
SOURCE_SHA256 = "404a18cfd86d29637d20c697dfde245bb47c666ae016730ab674c65f4d1e1aa4"
MODEL_ID = "cinque-v3-big"
INPUT_ABI = [
    ("new_img", TensorProto.UINT8, [2, 6, 128, 256]),
    ("desire", TensorProto.FLOAT, [8]),
    ("traffic_convention", TensorProto.FLOAT, [1, 2]),
    ("action_t", TensorProto.FLOAT, [1, 2]),
    ("state_img_q", TensorProto.UINT8, [2, 5, 6, 128, 256]),
    ("state_desire_q", TensorProto.FLOAT, [132, 1, 8]),
    ("state_feat_q", TensorProto.FLOAT, [128, 1, 16384]),
]
OUTPUT_ABI = [
    ("outputs", TensorProto.FLOAT, [1, 18452]),
    ("next_state_img_q", TensorProto.UINT8, [2, 5, 6, 128, 256]),
    ("next_state_desire_q", TensorProto.FLOAT, [132, 1, 8]),
    ("next_state_feat_q", TensorProto.FLOAT, [128, 1, 16384]),
]
METADATA = {
    "openpilot.model_id": MODEL_ID,
    "openpilot.source_sha256": SOURCE_SHA256,
    "openpilot.abi_version": "1",
    "openpilot.precision": "fp16-original",
    "openpilot.allow_cpu_fallback": "0",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tensor_abi(values) -> list[dict]:
    result = []
    for value in values:
        if not value.type.HasField("tensor_type"):
            raise ValueError(f"{value.name}: only tensor I/O is supported")
        tensor = value.type.tensor_type
        dims = tensor.shape.dim
        if any(not dim.HasField("dim_value") or dim.dim_value <= 0 for dim in dims):
            raise ValueError(f"{value.name}: shape must be fully static and positive")
        result.append({"name": value.name,
                       "dtype": TensorProto.DataType.Name(tensor.elem_type),
                       "shape": [dim.dim_value for dim in dims]})
    return result


def expected_abi(spec) -> list[dict]:
    return [{"name": name, "dtype": TensorProto.DataType.Name(dtype), "shape": shape}
            for name, dtype, shape in spec]


def validate_abi(model: onnx.ModelProto) -> None:
    for label, values, expected in (("inputs", model.graph.input, INPUT_ABI),
                                    ("outputs", model.graph.output, OUTPUT_ABI)):
        actual = tensor_abi(values)
        if actual != expected_abi(expected):
            raise ValueError(f"Unexpected Cinque v3 {label}: {actual}")


def strip_annotations(message) -> None:
    """Remove producer annotations without decoding pickle or executing metadata."""
    for field, value in list(message.ListFields()):
        if field.name in ("metadata_props", "doc_string"):
            message.ClearField(field.name)
        elif field.type == field.TYPE_MESSAGE:
            if field.is_repeated:
                for child in value:
                    strip_annotations(child)
            else:
                strip_annotations(value)


def rewrite_static_gathers(model: onnx.ModelProto) -> list[dict]:
    """Exact indexing rewrites; never change weights, precision, or queue logic.

    GatherND with batch_dims=0 and index depth 1 is precisely Gather(axis=0)
    after removing the trailing singleton index dimension. QNN's documented
    Gather restriction also requires normalizing constant negative indices.
    """
    initializers = {value.name: value for value in model.graph.initializer}
    shapes = {value.name: [dim.dim_value if dim.HasField("dim_value") else None
                          for dim in value.type.tensor_type.shape.dim]
              for value in [*model.graph.input, *model.graph.value_info, *model.graph.output]
              if value.type.HasField("tensor_type")}
    shapes.update({value.name: list(value.dims) for value in model.graph.initializer})
    names = set(initializers)
    names.update(name for node in model.graph.node for name in [*node.input, *node.output])
    changes = []
    for index, node in enumerate(model.graph.node):
        if node.domain not in ("", "ai.onnx") or node.op_type not in ("Gather", "GatherND"):
            continue
        if len(node.input) != 2 or node.input[1] not in initializers:
            continue
        indices = numpy_helper.to_array(initializers[node.input[1]])
        attrs = {attr.name: helper.get_attribute_value(attr) for attr in node.attribute}
        original_op = node.op_type
        if original_op == "GatherND":
            if attrs.get("batch_dims", 0) != 0 or indices.ndim == 0 or indices.shape[-1] != 1:
                continue
            axis = 0
            indices = indices[..., 0]
        else:
            axis = attrs.get("axis", 0)
            if not np.any(indices < 0):
                continue
        shape = shapes.get(node.input[0])
        if shape is None or not -len(shape) <= axis < len(shape):
            raise ValueError(f"Cannot normalize indices for {node.name}: input rank unknown")
        axis %= len(shape)
        dimension = shape[axis]
        if dimension is None or dimension <= 0:
            raise ValueError(f"Cannot normalize indices for {node.name}: axis size unknown")
        if np.any(indices < -dimension) or np.any(indices >= dimension):
            raise ValueError(f"Out of bounds constant indices in {node.name}")
        indices = np.where(indices < 0, indices + dimension, indices).astype(indices.dtype)
        new_name = f"openpilot_positive_gather_{index}"
        while new_name in names:
            new_name += "_"
        names.add(new_name)
        model.graph.initializer.append(numpy_helper.from_array(indices, name=new_name))
        node.input[1] = new_name
        node.op_type = "Gather"
        del node.attribute[:]
        node.attribute.append(helper.make_attribute("axis", axis))
        changes.append({"node": node.name, "from": original_op, "to": "Gather",
                        "axis": axis, "indices_shape": list(indices.shape)})
    return changes


def rewrite_image_routing_fp16(model: onnx.ModelProto) -> dict:
    """Route integer pixels on HTP-supported FP16 tensors without changing ABI.

    The image queue only copies, slices, reshapes and concatenates UINT8 pixels.
    Every value in 0..255 has an exact FP16 representation, so widening once at
    each graph input and narrowing only the external queue output is lossless.
    HTP supports the output conversion via FP32, rather than FP16 directly.
    Refuse arithmetic or other unexpected UINT8 consumers instead of broadening
    this rewrite beyond the pinned image-routing graph.
    """
    values = {value.name: value for value in [*model.graph.input, *model.graph.value_info,
                                             *model.graph.output]}
    uint8_names = {name for name, value in values.items()
                   if value.type.tensor_type.elem_type == TensorProto.UINT8}
    input_names = [value.name for value in model.graph.input if value.name in uint8_names]
    output_names = [value.name for value in model.graph.output if value.name in uint8_names]
    if set(input_names) != {"new_img", "state_img_q"} or output_names != ["next_state_img_q"]:
        raise ValueError("Image routing rewrite requires the original UINT8 image ABI")
    if any(value.data_type == TensorProto.UINT8 for value in model.graph.initializer):
        raise ValueError("Unexpected UINT8 initializer in the image routing graph")
    allowed = {"Slice", "Unsqueeze", "Squeeze", "Concat", "Gather", "Reshape", "Transpose", "Identity"}
    routing_nodes, boundary_casts, boundary_cast_indices = [], [], set()
    reachable = set(input_names)
    for node_index, node in enumerate(model.graph.node):
        uint8_inputs = [name for name in node.input if name in uint8_names]
        uint8_outputs = [name for name in node.output if name in uint8_names]
        if not uint8_inputs and not uint8_outputs:
            continue
        if node.domain not in ("", "ai.onnx") or not uint8_inputs or any(
                name not in reachable for name in uint8_inputs):
            raise ValueError(f"Unexpected UINT8 image producer in {node.name}")
        if node.op_type == "Cast":
            attrs = {attr.name: helper.get_attribute_value(attr) for attr in node.attribute}
            if len(node.input) != 1 or len(node.output) != 1 or attrs.get("to") != TensorProto.FLOAT16:
                raise ValueError(f"Unexpected image Cast boundary in {node.name}")
            if node.output[0] not in values or values[node.output[0]].type.tensor_type.elem_type != TensorProto.FLOAT16:
                raise ValueError(f"Missing FP16 image Cast output metadata in {node.name}")
            boundary_casts.append(node.name)
            boundary_cast_indices.add(node_index)
        else:
            data_inputs = list(node.input) if node.op_type == "Concat" else list(node.input[:1])
            if (node.op_type not in allowed or set(data_inputs) != set(uint8_inputs)
                    or len(uint8_outputs) != len(node.output)):
                raise ValueError(f"Unsupported UINT8 image arithmetic or routing in {node.name}")
            routing_nodes.append(node.name)
            reachable.update(uint8_outputs)
    if reachable != uint8_names or not boundary_casts:
        raise ValueError("Image routing graph is incomplete or lacks a FP16 network boundary")

    all_names = set(values) | {value.name for value in model.graph.initializer}
    all_names.update(name for node in model.graph.node for name in [node.name, *node.input, *node.output])
    renamed = {name: "openpilot_image_fp16_" + name for name in [*input_names, *output_names]}
    cast_names = {name: "openpilot_cast_" + name + ("_to_fp16" if name in input_names else "_to_uint8")
                  for name in renamed}
    output_bridges = {name: "openpilot_image_fp32_" + name for name in output_names}
    bridge_cast_names = {name: "openpilot_cast_" + name + "_to_fp32" for name in output_names}
    if any(name in all_names for name in [*renamed.values(), *cast_names.values(),
                                        *output_bridges.values(), *bridge_cast_names.values()]):
        raise ValueError("Image routing rewrite tensor or node names collide with the graph")

    # Internal declarations become FP16; external input/output declarations stay
    # UINT8. The new internal input and queue-output tensors need their own info.
    for value in model.graph.value_info:
        if value.name in uint8_names:
            value.name = renamed.get(value.name, value.name)
            value.type.tensor_type.elem_type = TensorProto.FLOAT16
    declared = {value.name for value in model.graph.value_info}
    for name, internal_name in renamed.items():
        if internal_name not in declared:
            internal = copy.deepcopy(values[name])
            internal.name = internal_name
            internal.type.tensor_type.elem_type = TensorProto.FLOAT16
            model.graph.value_info.append(internal)
    for name, bridge_name in output_bridges.items():
        bridge = copy.deepcopy(values[name])
        bridge.name = bridge_name
        bridge.type.tensor_type.elem_type = TensorProto.FLOAT
        model.graph.value_info.append(bridge)

    rewritten_nodes = [helper.make_node("Cast", [name], [renamed[name]], name=cast_names[name],
                                         to=TensorProto.FLOAT16) for name in input_names]
    for node_index, node in enumerate(model.graph.node):
        original_outputs = list(node.output)
        for index, name in enumerate(node.input):
            node.input[index] = renamed.get(name, name)
        for index, name in enumerate(node.output):
            node.output[index] = renamed.get(name, name)
        if node_index in boundary_cast_indices:
            node.op_type = "Identity"
            del node.attribute[:]
        rewritten_nodes.append(node)
        for name in original_outputs:
            if name in output_names:
                rewritten_nodes.append(helper.make_node("Cast", [renamed[name]], [output_bridges[name]],
                                                         name=bridge_cast_names[name], to=TensorProto.FLOAT))
                rewritten_nodes.append(helper.make_node("Cast", [output_bridges[name]], [name],
                                                         name=cast_names[name], to=TensorProto.UINT8))
    del model.graph.node[:]
    model.graph.node.extend(rewritten_nodes)
    return {"routing_dtype": "FLOAT16", "external_dtype": "UINT8", "pixel_range": [0, 255],
            "lossless_integer_pixels": True, "routing_nodes": routing_nodes,
            "input_casts": [cast_names[name] for name in input_names],
            "output_conversion": ["FLOAT16", "FLOAT", "UINT8"],
            "output_casts": [cast for name in output_names for cast in (bridge_cast_names[name], cast_names[name])],
            "redundant_casts_replaced_with_identity": boundary_casts}


def operator_inventory(model: onnx.ModelProto) -> dict[str, int]:
    return dict(sorted(Counter(f"{node.domain or 'ai.onnx'}::{node.op_type}"
                               for node in model.graph.node).items()))


def rewrite_attention_mask_bias(model: onnx.ModelProto) -> dict:
    """Replace only the pinned eight Where(Not(mask), -Inf, score) patterns.

    All masks must be identical constants. Keep all existing initializers and
    neural operations; append one non-weight FP16 bias. Nonfinite masked scores
    and signed zero are IEEE754 caveats, so device equivalence is measured on
    complete recurrent output sequences, not inferred from this graph rewrite.
    Validate every match before changing the graph.
    """
    initializers = {value.name: value for value in model.graph.initializer}
    producers = {name: (index, node) for index, node in enumerate(model.graph.node)
                 for name in node.output}
    infos = {value.name: value for value in
             [*model.graph.input, *model.graph.value_info, *model.graph.output]}
    where_nodes = [(index, node) for index, node in enumerate(model.graph.node)
                   if node.op_type == "Where"]
    expected = ["node_masked_fill" + (f"_{i}" if i else "") for i in range(8)]
    if [node.name for _, node in where_nodes] != expected:
        raise ValueError("Attention rewrite requires exactly the eight pinned Where nodes")
    bias_name = "opif_shared_attention_mask_bias_f16"
    if bias_name in initializers or bias_name in producers or bias_name in infos:
        raise ValueError("Attention bias name already exists")
    uses = Counter(name for node in model.graph.node for name in node.input)
    public_outputs = {value.name for value in model.graph.output}
    reference_mask = None
    removed, replacements, changes = set(), {}, []
    for index, node in where_nodes:
        if node.domain or node.attribute or len(node.input) != 3 or len(node.output) != 1:
            raise ValueError(f"Unexpected Where contract: {node.name}")
        invert_index, invert = producers.get(node.input[0], (None, None))
        if (invert is None or invert.op_type != "Not" or invert.domain or invert.attribute
                or len(invert.input) != 1 or len(invert.output) != 1
                or uses[node.input[0]] != 1 or node.input[0] in public_outputs):
            raise ValueError(f"Attention Not must have one private consumer: {node.name}")
        if invert.input[0] not in initializers or node.input[1] not in initializers:
            raise ValueError(f"Attention mask and fill must be constants: {node.name}")
        mask = numpy_helper.to_array(initializers[invert.input[0]])
        fill = numpy_helper.to_array(initializers[node.input[1]])
        score_info = infos.get(node.input[2])
        if mask.dtype != np.bool_ or mask.shape != (1, 1, 288, 288):
            raise ValueError(f"Unexpected attention mask shape/dtype: {node.name}")
        if fill.dtype != np.float16 or fill.shape != () or not np.isneginf(fill):
            raise ValueError(f"Attention fill must be FP16 scalar -Inf: {node.name}")
        if (score_info is None or not score_info.type.HasField("tensor_type")
                or score_info.type.tensor_type.elem_type != TensorProto.FLOAT16
                or [dim.dim_value for dim in score_info.type.tensor_type.shape.dim] != [1, 8, 288, 288]):
            raise ValueError(f"Unexpected attention score shape/dtype: {node.name}")
        if reference_mask is None:
            reference_mask = mask.copy()
        elif not np.array_equal(mask, reference_mask):
            raise ValueError("Attention masks differ; cannot share a bias")
        removed.add(invert_index)
        replacements[index] = helper.make_node(
            "Add", [node.input[2], bias_name], list(node.output), name=node.name + "_add_bias")
        changes.append({"where": node.name, "removed_not": invert.name,
                        "score": node.input[2], "mask": invert.input[0], "output": node.output[0]})
    bias = np.where(reference_mask, np.float16(0), np.float16(-np.inf)).astype(np.float16)
    nodes = [replacements.get(index, node) for index, node in enumerate(model.graph.node)
             if index not in removed]
    del model.graph.node[:]
    model.graph.node.extend(nodes)
    model.graph.initializer.append(numpy_helper.from_array(bias, name=bias_name))
    return {"mode": "shared_fp16_add_bias", "replaced_where_count": len(changes),
            "removed_not_count": len(removed), "bias_name": bias_name,
            "bias_shape": list(bias.shape), "bias_bytes": bias.nbytes,
            "retained_mask_elements": int(reference_mask.sum()),
            "score_ieee754_caveat": "Masked NaN/+Inf and signed zero require device sequence comparison",
            "changes": changes}


def prepare(source: Path, output: Path, *, fp16_image_routing: bool = True,
            attention_mask_bias: bool = True) -> dict:
    source = source.resolve()
    output = output.resolve()
    if sha256_file(source) != SOURCE_SHA256:
        raise ValueError("Source SHA-256 does not match the pinned Cinque v3 big model")
    if source == output / "model.onnx":
        raise ValueError("Output must not overwrite the source model")
    model = onnx.load(source, load_external_data=False)
    if any(t.data_location == TensorProto.EXTERNAL for t in model.graph.initializer):
        raise ValueError("Pinned source must contain its weights, not unverified external data")
    validate_abi(model)
    onnx.checker.check_model(model)
    before_ops = operator_inventory(model)
    local_functions = [f"{function.domain}::{function.name}" for function in model.functions]
    model = inliner.inline_local_functions(model, convert_version=False)
    if model.functions or any(node.domain not in ("", "ai.onnx") for node in model.graph.node):
        raise ValueError("Unresolved custom operators remain after local function inlining")
    changes = rewrite_static_gathers(model)
    image_routing_changes = rewrite_image_routing_fp16(model) if fp16_image_routing else None
    attention_changes = rewrite_attention_mask_bias(model) if attention_mask_bias else None
    strip_annotations(model)
    metadata = dict(METADATA)
    if attention_changes is not None:
        metadata["openpilot.attention_mask"] = attention_changes["mode"]
    helper.set_model_props(model, metadata)
    # The only tinygrad local function was inlined; remove its unused import.
    used_domains = {node.domain for node in model.graph.node} | {""}
    imports = [item for item in model.opset_import if item.domain in used_domains]
    del model.opset_import[:]
    model.opset_import.extend(imports)
    validate_abi(model)
    onnx.checker.check_model(model, full_check=True)
    output.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1, "model_id": MODEL_ID, "model_file": "model.onnx",
        "source_sha256": SOURCE_SHA256, "precision": "fp16-original",
        "quantized": False, "host_state_updates": False,
        "inputs": tensor_abi(model.graph.input), "outputs": tensor_abi(model.graph.output),
        "metadata": metadata, "onnx_version": onnx.__version__, "ir_version": model.ir_version,
        "opsets": {item.domain or "ai.onnx": item.version for item in model.opset_import},
        "initializers_by_dtype": dict(sorted(Counter(TensorProto.DataType.Name(item.data_type)
                                                       for item in model.graph.initializer).items())),
        "changes": {"inlined_functions": local_functions, "static_gathers": changes,
                    "removed_producer_annotations": True},
        "operators_before": before_ops, "operators_after": operator_inventory(model),
        "target_validation": {
            "status": "not_run", "required_backend": "libQnnHtp.so", "cpu_ep_fallback": False,
            "risks": [
                "Operator names alone do not establish QNN support for these shapes and dtypes.",
                "Validate FP16 MatMul, Gelu and LayerNormalization on the pinned ORT/QAIRT build.",
                "Validate UINT8 image queues and FP32 recurrent queue operations on HTP.",
                "Validate 731 MiB source graph compilation memory and steady-state latency on device.",
                "Compare recurrent outputs against the source graph before using predictions.",
            ],
            "operator_reference": "https://onnxruntime.ai/docs/execution-providers/QNN-ExecutionProvider.html",
        },
    }
    if image_routing_changes is not None:
        manifest["changes"]["fp16_image_routing"] = image_routing_changes
        manifest["target_validation"]["risks"][2] = (
            "Validate UINT8/FP16 image boundary casts, FP16 image routing and FP32 recurrent queue operations on HTP.")
    if attention_changes is not None:
        manifest["changes"]["attention_mask_bias"] = attention_changes
        manifest["target_validation"]["risks"].append(
            "Compare all four recurrent outputs on the same HTP device against --original-attention-mask.")
    # Publish manifest last so a partial export cannot look like a complete package.
    with tempfile.TemporaryDirectory(prefix=".prepare-", dir=output) as temporary:
        temporary = Path(temporary)
        model_path = temporary / "model.onnx"
        onnx.save_model(model, model_path)
        manifest["deployment_sha256"] = sha256_file(model_path)
        manifest["deployment_bytes"] = model_path.stat().st_size
        manifest_path = temporary / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        model_path.replace(output / "model.onnx")
        manifest_path.replace(output / "manifest.json")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / ".cache/cinque3/big_driving_supercombo.onnx")
    parser.add_argument("--output", type=Path, default=ROOT / ".cache/android-models/cinque3")
    routing = parser.add_mutually_exclusive_group()
    routing.add_argument("--fp16-image-routing", action="store_true", dest="fp16_image_routing",
                         help="Use lossless FP16 image routing internally for HTP (default); retain UINT8 I/O")
    routing.add_argument("--original-image-routing", action="store_false", dest="fp16_image_routing",
                         help="Reproduce original UINT8 routing for diagnostics; unsupported by the tested HTP backend")
    parser.set_defaults(fp16_image_routing=True)
    attention = parser.add_mutually_exclusive_group()
    attention.add_argument("--shared-attention-mask-bias", action="store_true", dest="attention_mask_bias",
                           help="Replace eight constant attention Where masks with a shared FP16 bias (default)")
    attention.add_argument("--original-attention-mask", action="store_false", dest="attention_mask_bias",
                           help="Export the original Where masks for same-device A/B comparison")
    parser.set_defaults(attention_mask_bias=True)
    args = parser.parse_args()
    try:
        manifest = prepare(args.source, args.output, fp16_image_routing=args.fp16_image_routing,
                           attention_mask_bias=args.attention_mask_bias)
    except (ValueError, OSError, onnx.checker.ValidationError) as error:
        print(f"Model preparation failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"output": str(args.output), "deployment_sha256": manifest["deployment_sha256"],
                      "changes": manifest["changes"], "target_validation": "not_run"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
