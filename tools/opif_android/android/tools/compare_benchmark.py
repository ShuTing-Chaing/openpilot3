#!/usr/bin/env python3
"""Compare raw Android benchmark outputs with the original model on host CPU.

Input is N consecutive UINT8[2,6,128,256] frames. The benchmark uses input i % N
for iteration i, zero initial queues, desire=0, LHD, and action_t=[0.4,0.7]. Its
output is one little-endian FLOAT32[18452] vector per iteration, without warmup.
Tolerances must be supplied explicitly; passing establishes only numerical
agreement for this sequence, not QNN provider placement or vehicle safety.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
import onnxruntime as ort

from prepare_model import ROOT, SOURCE_SHA256, sha256_file


FRAME_BYTES = 2 * 6 * 128 * 256
OUTPUT_FLOATS = 18452
# Exact output layout from the source-SHA-bound cinque3 output_metadata.json.
HEADS = {
    "lane_lines": (0, 528), "lane_lines_prob": (528, 536), "road_edges": (536, 800),
    "meta": (800, 855), "desire_pred": (855, 887), "pose": (887, 899),
    "wide_from_device_euler": (899, 905), "road_transform": (905, 917),
    "plan": (917, 1907), "lead": (1907, 2051), "lead_prob": (2051, 2054),
    "desire_state": (2054, 2062), "action": (2062, 2066),
    "hidden_state": (2066, 18450), "pad": (18450, 18452),
}


def error_stats(actual: np.ndarray, expected: np.ndarray, atol: float, rtol: float) -> dict:
    actual, expected = actual.astype(np.float64), expected.astype(np.float64)
    if actual.shape != expected.shape or not actual.size:
        raise ValueError("Comparison arrays must have the same nonempty shape")
    if not np.isfinite([atol, rtol]).all() or min(atol, rtol) < 0:
        raise ValueError("Tolerances must be finite and nonnegative")
    finite = np.isfinite(actual) & np.isfinite(expected)
    if not finite.all():
        return {"passed": False, "elements": actual.size,
                "nonfinite_elements": int((~finite).sum()), "mismatched_elements": None,
                "max_abs": None, "rmse": None, "max_tolerance_ratio": None, "exact": False}
    delta = np.abs(actual - expected)
    tolerance = atol + rtol * np.abs(expected)
    mismatches = int((delta > tolerance).sum())
    ratios = np.zeros_like(delta)
    np.divide(delta, tolerance, out=ratios, where=tolerance > 0)
    unbounded = bool(np.any((tolerance == 0) & (delta != 0)))
    return {"passed": mismatches == 0, "elements": actual.size, "nonfinite_elements": 0,
            "mismatched_elements": mismatches, "max_abs": float(delta.max()),
            "rmse": float(np.sqrt(np.mean(delta ** 2))),
            "max_tolerance_ratio": None if unbounded else float(ratios.max()),
            "exact": bool(np.array_equal(actual, expected))}


def compare(input_path: Path, output_path: Path, source: Path, atol: float, rtol: float) -> dict:
    input_bytes, output_bytes = input_path.stat().st_size, output_path.stat().st_size
    if input_bytes == 0 or input_bytes % FRAME_BYTES:
        raise ValueError(f"Input must contain whole {FRAME_BYTES}-byte packed camera frames")
    if output_bytes == 0 or output_bytes % (OUTPUT_FLOATS * 4):
        raise ValueError(f"Output must contain whole {OUTPUT_FLOATS * 4}-byte prediction frames")
    if sha256_file(source) != SOURCE_SHA256:
        raise ValueError("Source SHA-256 does not match pinned Cinque v3")
    inputs = np.memmap(input_path, dtype=np.uint8, mode="r").reshape(-1, 2, 6, 128, 256)
    outputs = np.memmap(output_path, dtype="<f4", mode="r").reshape(-1, OUTPUT_FLOATS)
    options = ort.SessionOptions()
    options.intra_op_num_threads = 4
    options.log_severity_level = 3
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
    session = ort.InferenceSession(str(source), sess_options=options, providers=["CPUExecutionProvider"])
    names = [value.name for value in session.get_outputs()]
    states = {"state_img_q": np.zeros((2, 5, 6, 128, 256), np.uint8),
              "state_desire_q": np.zeros((132, 1, 8), np.float32),
              "state_feat_q": np.zeros((128, 1, 16384), np.float32)}
    records = []
    expected_outputs = np.empty(outputs.shape, dtype=np.float32)
    for frame in range(len(outputs)):
        feeds = dict(new_img=inputs[frame % len(inputs)], desire=np.zeros(8, np.float32),
                     traffic_convention=np.array([[1, 0]], np.float32),
                     action_t=np.array([[0.4, 0.7]], np.float32), **states)
        reference = dict(zip(names, session.run(None, feeds)))
        expected = reference["outputs"].reshape(-1)
        expected_outputs[frame] = expected
        states = {name: reference["next_" + name] for name in states}
        stats = error_stats(outputs[frame], expected, atol, rtol)
        records.append({"frame": frame, "input_frame": frame % len(inputs), **stats})
        print(json.dumps(records[-1]), flush=True)
    summary = error_stats(outputs, expected_outputs, atol, rtol)
    return {"status": "passed" if summary["passed"] else "failed", "hardware_placement_verified": False,
            "validation_kind": "device_output_vs_offline_source", "source_sha256": SOURCE_SHA256,
            "input_sha256": sha256_file(input_path), "output_sha256": sha256_file(output_path),
            "onnxruntime_version": ort.__version__, "reference_graph_optimization": "disabled",
            "input_frames": len(inputs), "iterations": len(outputs), "atol": atol, "rtol": rtol,
            "controls": {"desire": 0, "traffic_convention": [1, 0], "action_t": [0.4, 0.7]},
            "summary": summary, "frames": records,
            "heads": {name: error_stats(outputs[:, start:end], expected_outputs[:, start:end], atol, rtol)
                      for name, (start, end) in HEADS.items()}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--atol", required=True, type=float)
    parser.add_argument("--rtol", required=True, type=float)
    parser.add_argument("--source", type=Path, default=ROOT / ".cache/cinque3/big_driving_supercombo.onnx")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        if not np.isfinite([args.atol, args.rtol]).all() or min(args.atol, args.rtol) < 0:
            raise ValueError("Tolerances must be finite and nonnegative")
        report = compare(args.input, args.output, args.source, args.atol, args.rtol)
        report_path = args.report or args.output.with_suffix(".comparison.json")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    except (ValueError, OSError) as error:
        print(f"Benchmark comparison failed: {error}", file=sys.stderr)
        return 1
    print(f"Numerical comparison {report['status']}; report: {report_path}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
