#!/usr/bin/env python3
"""Offline host reference check of the complete prepared recurrent ONNX graph.

CPU execution here is an explicit development-time numerical reference, never a
fallback in the Android server. Compare against the original model with graph
optimizations disabled: inlining an Identity function permits additional ORT
FP16 fusions, so previously cached optimized references can differ. The ten-frame
input sequence matches script/validate_cinque3_onnx.py. This is not an NPU test.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

import numpy as np
import onnxruntime as ort

from prepare_model import ROOT, METADATA, SOURCE_SHA256, sha256_file


DESIRES = [0, 1, 1, 0, 2, 2, 0, 3, 3, 0]


def validate(model: Path, source: Path, resources: Path, frames: int,
             atol: float, rtol: float, optimized: bool = False) -> dict:
    if not 1 <= frames <= len(DESIRES):
        raise ValueError(f"frames must be between 1 and {len(DESIRES)}")
    if sha256_file(source) != SOURCE_SHA256:
        raise ValueError("Source hash does not match pinned Cinque v3")
    base = np.stack([np.fromfile(resources / f"{name}.bin", dtype=np.uint8).reshape(2, 6, 128, 256)[1]
                     for name in ("img", "big_img")])
    options = ort.SessionOptions()
    options.intra_op_num_threads = 4
    options.log_severity_level = 3
    options.graph_optimization_level = (ort.GraphOptimizationLevel.ORT_ENABLE_ALL if optimized
                                        else ort.GraphOptimizationLevel.ORT_DISABLE_ALL)
    session = ort.InferenceSession(str(model), sess_options=options, providers=["CPUExecutionProvider"])
    reference = ort.InferenceSession(str(source), sess_options=options, providers=["CPUExecutionProvider"])
    metadata = session.get_modelmeta().custom_metadata_map
    if any(metadata.get(key) != value for key, value in METADATA.items()):
        raise ValueError("Prepared model metadata does not match the deployment contract")
    states = {"state_img_q": np.zeros((2, 5, 6, 128, 256), np.uint8),
              "state_desire_q": np.zeros((132, 1, 8), np.float32),
              "state_feat_q": np.zeros((128, 1, 16384), np.float32)}
    reference_states = {name: value.copy() for name, value in states.items()}
    previous = 0
    records = []
    names = [value.name for value in session.get_outputs()]
    reference_names = [value.name for value in reference.get_outputs()]
    for frame, desire in enumerate(DESIRES[:frames]):
        current = np.bitwise_xor(base, np.uint8(frame * 7))
        pulse = np.zeros(8, np.float32)
        if desire and desire != previous:
            pulse[desire] = 1
        previous = desire
        feeds = dict(new_img=current, desire=pulse,
                     traffic_convention=np.array([[1, 0]], np.float32),
                     action_t=np.array([[0.4, 0.7]], np.float32), **states)
        started = time.perf_counter()
        result = dict(zip(names, session.run(None, feeds)))
        elapsed = time.perf_counter() - started
        source_result = dict(zip(reference_names, reference.run(None, dict(feeds, **reference_states))))
        actual = result["outputs"]
        expected = source_result["outputs"]
        if actual.shape != expected.shape or not np.isfinite(actual).all() or not np.isfinite(expected).all():
            raise ValueError(f"Frame {frame}: invalid or nonfinite outputs")
        np.testing.assert_allclose(actual, expected, atol=atol, rtol=rtol,
                                   err_msg=f"Frame {frame}: prepared model differs from source reference")
        next_expected = {
            "state_img_q": np.concatenate((states["state_img_q"][:, 1:], current[:, None]), axis=1),
            "state_desire_q": np.concatenate((states["state_desire_q"][1:], pulse.reshape(1, 1, 8))),
            "state_feat_q": np.concatenate((states["state_feat_q"][1:], actual[:, 2066:18450].reshape(1, 1, 16384))),
        }
        for name, expected_state in next_expected.items():
            np.testing.assert_array_equal(result["next_" + name], expected_state,
                                          err_msg=f"Frame {frame}: {name} queue update changed")
            np.testing.assert_allclose(result["next_" + name], source_result["next_" + name],
                                       atol=atol, rtol=rtol,
                                       err_msg=f"Frame {frame}: {name} differs from source")
        states = {name: result["next_" + name] for name in states}
        reference_states = {name: source_result["next_" + name] for name in reference_states}
        delta = actual.astype(np.float64) - expected.astype(np.float64)
        tolerance = atol + rtol * np.abs(expected.astype(np.float64))
        ratios = np.zeros_like(delta)
        np.divide(np.abs(delta), tolerance, out=ratios, where=tolerance > 0)
        ratios[(tolerance == 0) & (delta != 0)] = np.inf
        record = {"frame": frame, "max_abs": float(np.abs(delta).max()),
                  "rmse": float(np.sqrt(np.mean(delta ** 2))), "host_seconds": elapsed,
                  "queues_exact": True, "outputs_exact": bool(np.array_equal(actual, expected)),
                  "max_tolerance_ratio": float(ratios.max())}
        records.append(record)
        print(json.dumps(record), flush=True)
    return {"status": "passed", "validation_kind": "offline_cpu_reference",
            "npu_validated": False, "onnxruntime_version": ort.__version__,
            "graph_optimization": "all" if optimized else "disabled", "deployment_sha256": sha256_file(model),
            "source_sha256": SOURCE_SHA256,
            "frames": frames, "atol": atol, "rtol": rtol, "comparisons": records}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=ROOT / ".cache/android-models/cinque3/model.onnx")
    parser.add_argument("--source", type=Path, default=ROOT / ".cache/cinque3/big_driving_supercombo.onnx")
    parser.add_argument("--resources", type=Path, default=ROOT / "OpenPilotInference/Resources")
    parser.add_argument("--frames", type=int, default=10)
    parser.add_argument("--atol", type=float, default=0.0)
    parser.add_argument("--rtol", type=float, default=0.0)
    parser.add_argument("--compare-optimized", action="store_true",
                        help="Also record ORT FP16 fusion differences at atol=0.05, rtol=0.005")
    parser.add_argument("--report", type=Path, default=ROOT / ".cache/android-models/cinque3/validation.json")
    args = parser.parse_args()
    try:
        if not np.isfinite([args.atol, args.rtol]).all() or min(args.atol, args.rtol) < 0:
            raise ValueError("Tolerances must be finite and nonnegative")
        report = validate(args.model, args.source, args.resources, args.frames, args.atol, args.rtol)
        if args.compare_optimized:
            report["optimized_comparison"] = validate(args.model, args.source, args.resources,
                                                       args.frames, 0.05, 0.005, optimized=True)
            report["optimized_comparison"]["interpretation"] = (
                "Inlining the Contiguous Identity function enables additional ORT FP16 fusions. "
                "Optimized arithmetic can differ despite exact unoptimized graph semantics. "
                "These tolerances match the existing Cinque conversion comparison; "
                "passing is not a device NPU accuracy or safety acceptance test.")
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    except (ValueError, OSError, AssertionError) as error:
        print(f"Offline model validation failed: {error}", file=sys.stderr)
        return 1
    print(f"Passed {args.frames} recurrent frames; report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
