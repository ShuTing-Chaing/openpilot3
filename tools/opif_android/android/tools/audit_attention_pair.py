#!/usr/bin/env python3
"""Audit two real OPIF exports and stage a shared-weight Android offline pair."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import onnx
from prepare_model import sha256_file, validate_abi

BASELINE_SHA = "86890bf95af82adbcc85f20f3a60acda3bffc852224bfb00afdbb81ee2f4a677"
BIAS = "opif_shared_attention_mask_bias_f16"


def digest(value):
    return hashlib.sha256(value.SerializeToString(deterministic=True)).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if sha256_file(a.baseline) != BASELINE_SHA:
        raise ValueError("Baseline does not reproduce the installed OPIF graph")
    if a.output.exists():
        raise ValueError("Use a new evidence directory")
    before = onnx.load(a.baseline)
    after = onnx.load(a.candidate)
    for model in (before, after):
        validate_abi(model)
        onnx.checker.check_model(model, full_check=True)
    assert [digest(v) for v in [*before.graph.input, *before.graph.output]] == [
        digest(v) for v in [*after.graph.input, *after.graph.output]]
    weights = {v.name: digest(v) for v in before.graph.initializer}
    candidate_weights = {v.name: digest(v) for v in after.graph.initializer}
    assert all(candidate_weights.get(k) == v for k, v in weights.items())
    assert set(candidate_weights) - set(weights) == {BIAS}
    old_nodes = {n.name: digest(n) for n in before.graph.node}
    new_nodes = {n.name: digest(n) for n in after.graph.node}
    removed = {n.name for n in before.graph.node if n.op_type in ("Where", "Not")}
    assert len(removed) == 16
    assert all(new_nodes.get(k) == v for k, v in old_nodes.items() if k not in removed)
    assert len(set(new_nodes) - set(old_nodes)) == 8
    counts_before = Counter(n.op_type for n in before.graph.node)
    counts_after = Counter(n.op_type for n in after.graph.node)
    assert counts_before["Where"] == counts_before["Not"] == 8
    assert counts_after["Where"] == counts_after["Not"] == 0
    assert counts_after["Add"] == counts_before["Add"] + 8
    assert all(counts_after[k] == v for k, v in counts_before.items() if k not in ("Where", "Not", "Add"))
    report = {"structural_audit_passed": True, "baseline_sha256": BASELINE_SHA,
              "candidate_sha256": sha256_file(a.candidate), "onnx_version": onnx.__version__,
              "original_initializers_byte_identical": len(weights), "public_abi_byte_identical": True,
              "unchanged_other_nodes": len(old_nodes) - len(removed),
              "operators_before": dict(counts_before), "operators_after": dict(counts_after),
              "device_comparison_completed": False, "latency_measured": False}
    a.output.mkdir(parents=True)
    onnx.save_model(before, a.output / "baseline.onnx", save_as_external_data=True,
                    all_tensors_to_one_file=True, location="weights.bin", size_threshold=1024)
    external = {v.name: v for v in before.graph.initializer}
    for tensor in after.graph.initializer:
        if tensor.name in external:
            tensor.CopyFrom(external[tensor.name])
    onnx.save_model(after, a.output / "candidate.onnx")
    del before, after
    # Inspect actual serialized/reloaded artifacts, including the external bytes.
    for name in ("baseline.onnx", "candidate.onnx"):
        model = onnx.load(a.output / name)
        actual = {}
        for tensor in model.graph.initializer:
            normalized = onnx.TensorProto()
            normalized.CopyFrom(tensor)
            normalized.ClearField("data_location")
            normalized.ClearField("external_data")
            actual[tensor.name] = digest(normalized)
        assert all(actual.get(k) == v for k, v in weights.items())
        onnx.checker.check_model(str(a.output / name))
        del model
    report["device_files_sha256"] = {name: sha256_file(a.output / name)
                                      for name in ("baseline.onnx", "candidate.onnx", "weights.bin")}
    (a.output / "graph-audit.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
