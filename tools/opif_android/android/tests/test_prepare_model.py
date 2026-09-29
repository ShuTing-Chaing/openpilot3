"""Host-only correctness checks for graph indexing and fail-closed profiling."""
import importlib.util
from pathlib import Path
import tempfile
import sys
import unittest
from unittest import mock

import numpy as np
import onnx
from onnx import helper, numpy_helper, TensorProto
from onnx.reference import ReferenceEvaluator


TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prepare = load_tool("prepare_model")
profile = load_tool("verify_profile")
benchmark = load_tool("compare_benchmark")


class PrepareModelTests(unittest.TestCase):
    def test_cli_defaults_to_verified_routing_and_allows_explicit_baseline(self):
        result = {"deployment_sha256": "0" * 64, "changes": {}}
        for arguments, expected in (([], True), (["--fp16-image-routing"], True),
                                    (["--original-image-routing"], False)):
            with self.subTest(arguments=arguments), mock.patch.object(sys, "argv", ["prepare_model.py", *arguments]), \
                    mock.patch.object(prepare, "prepare", return_value=result) as export, mock.patch("builtins.print"):
                self.assertEqual(prepare.main(), 0)
                self.assertEqual(export.call_args.kwargs["fp16_image_routing"], expected)

    def make_gather_model(self, op, shape, indices, output_shape, **attributes):
        return helper.make_model(helper.make_graph(
            [helper.make_node(op, ["x", "indices"], ["y"], name="gather", **attributes)],
            "test", [helper.make_tensor_value_info("x", TensorProto.FLOAT, shape)],
            [helper.make_tensor_value_info("y", TensorProto.FLOAT, output_shape)],
            [numpy_helper.from_array(np.array(indices, dtype=np.int64), "indices")]),
            opset_imports=[helper.make_opsetid("", 20)])

    def assert_rewrite_exact(self, model, shape):
        data = np.arange(np.prod(shape), dtype=np.float32).reshape(shape)
        expected = ReferenceEvaluator(model).run(None, {"x": data})[0]
        original_initializer = model.graph.initializer[0].SerializeToString()
        changes = prepare.rewrite_static_gathers(model)
        self.assertEqual(len(changes), 1)
        onnx.checker.check_model(model, full_check=True)
        actual = ReferenceEvaluator(model).run(None, {"x": data})[0]
        np.testing.assert_array_equal(actual, expected)
        self.assertEqual(model.graph.initializer[0].SerializeToString(), original_initializer)
        return model

    def test_gathernd_depth_one_preserves_indices_shape_and_values(self):
        model = self.make_gather_model("GatherND", [33, 1, 2, 3],
                                       np.arange(-9, 0).reshape(9, 1), [9, 1, 2, 3], batch_dims=0)
        model = self.assert_rewrite_exact(model, [33, 1, 2, 3])
        self.assertEqual(model.graph.node[0].op_type, "Gather")
        np.testing.assert_array_equal(numpy_helper.to_array(model.graph.initializer[-1]), np.arange(24, 33))

    def test_negative_scalar_gather_preserves_rank(self):
        model = self.make_gather_model("Gather", [1, 288, 4], -1, [1, 4], axis=1)
        self.assert_rewrite_exact(model, [1, 288, 4])
        self.assertEqual(list(model.graph.initializer[-1].dims), [])

    def test_mixed_indices_negative_axis(self):
        model = self.make_gather_model("Gather", [2, 4], [-4, 0, 3, -1], [2, 4], axis=-1)
        self.assert_rewrite_exact(model, [2, 4])

    def test_unknown_shape_and_out_of_bounds_fail(self):
        for shape, indices in (([1, "N", 4], -1), ([1, 3, 4], -4)):
            with self.subTest(shape=shape):
                model = self.make_gather_model("Gather", shape, indices, [1, 4], axis=1)
                with self.assertRaises(ValueError):
                    prepare.rewrite_static_gathers(model)

    def test_strip_annotations_without_decoding_metadata(self):
        model = self.make_gather_model("Gather", [2], [0], [1], axis=0)
        helper.set_model_props(model, {"pickle": "deliberately invalid pickle data"})
        model.graph.node[0].doc_string = "producer stack"
        model.graph.node[0].metadata_props.add(key="stack", value="path")
        prepare.strip_annotations(model)
        self.assertFalse(model.metadata_props)
        self.assertFalse(model.graph.node[0].metadata_props)
        self.assertEqual(model.graph.node[0].doc_string, "")

    def test_source_hash_mismatch_leaves_no_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.onnx"
            source.write_bytes(b"not the pinned model")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                prepare.prepare(source, root / "output")
            self.assertFalse((root / "output").exists())

    def test_abi_rejects_dynamic_or_different_interface(self):
        model = self.make_gather_model("Gather", [2], [0], [1], axis=0)
        with self.assertRaises(ValueError):
            prepare.validate_abi(model)
        model.graph.input[0].type.tensor_type.shape.dim[0].dim_param = "N"
        with self.assertRaisesRegex(ValueError, "static"):
            prepare.tensor_abi(model.graph.input)


class ImageRoutingRewriteTests(unittest.TestCase):
    def make_image_model(self):
        constants = {"one": [1], "zero": [0], "end": [2 ** 63 - 1], "skip": [4],
                     "shape": [1, 2, 16, 16], "cam0": np.int64(0), "cam1": np.int64(1)}
        initializers = [numpy_helper.from_array(np.asarray(value, dtype=np.int64), name)
                        for name, value in constants.items()]
        nodes = [
            helper.make_node("Slice", ["state_img_q", "one", "end", "one", "one"], ["history"], name="shift"),
            helper.make_node("Unsqueeze", ["new_img", "one"], ["current"], name="append_dim"),
            helper.make_node("Concat", ["history", "current"], ["next_state_img_q"], axis=1, name="queue"),
        ]
        values = {"history": [2, 4, 1, 16, 16], "current": [2, 1, 1, 16, 16]}
        for camera in range(2):
            selected, spaced, packed = (f"{name}_{camera}" for name in ("selected", "spaced", "packed"))
            nodes += [
                helper.make_node("Gather", ["next_state_img_q", f"cam{camera}"], [selected],
                                 axis=0, name=f"select_{camera}"),
                helper.make_node("Slice", [selected, "zero", "end", "zero", "skip"], [spaced],
                                 name=f"space_{camera}"),
                helper.make_node("Reshape", [spaced, "shape"], [packed], name=f"pack_{camera}"),
            ]
            values.update({selected: [5, 1, 16, 16], spaced: [2, 1, 16, 16], packed: [1, 2, 16, 16]})
        nodes += [helper.make_node("Concat", ["packed_0", "packed_1"], ["images"], axis=1, name="both"),
                  helper.make_node("Cast", ["images"], ["vision"], to=TensorProto.FLOAT16, name="to_network")]
        values["images"] = [1, 4, 16, 16]
        graph = helper.make_graph(nodes, "image-queue", [
            helper.make_tensor_value_info("new_img", TensorProto.UINT8, [2, 1, 16, 16]),
            helper.make_tensor_value_info("state_img_q", TensorProto.UINT8, [2, 5, 1, 16, 16]),
        ], [helper.make_tensor_value_info("next_state_img_q", TensorProto.UINT8, [2, 5, 1, 16, 16]),
            helper.make_tensor_value_info("vision", TensorProto.FLOAT16, [1, 4, 16, 16])], initializers,
            value_info=[helper.make_tensor_value_info(name, TensorProto.UINT8, shape)
                        for name, shape in values.items()])
        return helper.make_model(graph, opset_imports=[helper.make_opsetid("", 20)])

    def test_all_256_pixel_values_and_recurrent_queue_are_exact(self):
        model = self.make_image_model()
        original = ReferenceEvaluator(onnx.load_model_from_string(model.SerializeToString()))
        before_inputs = prepare.tensor_abi(model.graph.input)
        before_outputs = prepare.tensor_abi(model.graph.output)
        initializers = [value.SerializeToString() for value in model.graph.initializer]
        changes = prepare.rewrite_image_routing_fp16(model)
        onnx.checker.check_model(model, full_check=True)
        converted = ReferenceEvaluator(model)
        self.assertEqual(prepare.tensor_abi(model.graph.input), before_inputs)
        self.assertEqual(prepare.tensor_abi(model.graph.output), before_outputs)
        self.assertEqual([value.SerializeToString() for value in model.graph.initializer], initializers)
        self.assertEqual(len(changes["input_casts"]), 2)
        self.assertEqual(len(changes["output_casts"]), 2)
        pixels = np.arange(256).reshape(1, 1, 1, 16, 16)
        camera_offsets = np.arange(2).reshape(2, 1, 1, 1, 1) * 67
        slot_offsets = np.arange(5).reshape(1, 5, 1, 1, 1) * 31
        source_state = ((pixels + camera_offsets + slot_offsets) % 256).astype(np.uint8)
        converted_state = source_state.copy()
        for frame in range(8):
            image = ((pixels[:, 0] + camera_offsets[:, 0] + frame * 17) % 256).astype(np.uint8)
            expected = original.run(None, {"new_img": image, "state_img_q": source_state})
            actual = converted.run(None, {"new_img": image, "state_img_q": converted_state})
            for expected_output, actual_output in zip(expected, actual):
                np.testing.assert_array_equal(actual_output, expected_output)
                self.assertEqual(actual_output.dtype, expected_output.dtype)
            source_state, converted_state = expected[0], actual[0]

    def test_gathers_use_internal_fp16_queue_without_round_trip(self):
        model = self.make_image_model()
        prepare.rewrite_image_routing_fp16(model)
        gathers = [node for node in model.graph.node if node.op_type == "Gather"]
        self.assertTrue(all(node.input[0] == "openpilot_image_fp16_next_state_img_q" for node in gathers))
        queue_output = next(node for node in model.graph.node if "next_state_img_q" in node.output)
        self.assertEqual(queue_output.op_type, "Cast")
        self.assertEqual(queue_output.input[0], "openpilot_image_fp32_next_state_img_q")
        queue_bridge = next(node for node in model.graph.node if queue_output.input[0] in node.output)
        self.assertEqual(queue_bridge.op_type, "Cast")
        self.assertEqual(queue_bridge.input[0], "openpilot_image_fp16_next_state_img_q")
        self.assertEqual(helper.get_attribute_value(queue_bridge.attribute[0]), TensorProto.FLOAT)
        self.assertEqual(next(node for node in model.graph.node if node.name == "to_network").op_type, "Identity")

    def test_unexpected_uint8_arithmetic_rejected_before_mutation(self):
        model = self.make_image_model()
        next(node for node in model.graph.node if node.name == "both").op_type = "Add"
        before = model.SerializeToString()
        with self.assertRaisesRegex(ValueError, "arithmetic"):
            prepare.rewrite_image_routing_fp16(model)
        self.assertEqual(model.SerializeToString(), before)


class VerifyProfileTests(unittest.TestCase):
    def kernel(self, provider="QNNExecutionProvider"):
        return {"cat": "Node", "name": "QNN_0_kernel_time", "ph": "X", "dur": 15,
                "args": {"provider": provider, "op_name": "QNN"}}

    def test_qnn_with_host_scheduling_and_fences(self):
        result = profile.verify_profile([
            {"cat": "Session", "name": "model_run", "args": {}},
            {"cat": "Node", "name": "QNN_0_fence_before", "args": {}},
            self.kernel(),
        ])
        self.assertEqual(result["kernel_events"], 1)
        self.assertEqual(result["providers"], {"QNNExecutionProvider": 1})

    def test_trace_events_wrapper(self):
        self.assertEqual(profile.verify_profile({"traceEvents": [self.kernel()]})["status"], "qnn_only")

    def test_cpu_gpu_or_unknown_provider_fails(self):
        for provider in ("CPUExecutionProvider", "CUDAExecutionProvider", "NNAPIExecutionProvider", "", None):
            with self.subTest(provider=provider), self.assertRaises(profile.ProfileError):
                profile.verify_profile([self.kernel(), self.kernel(provider)])

    def test_empty_missing_or_unattributed_kernel_fails(self):
        for events in ([], {}, [{"cat": "Session", "name": "model_run"}],
                       [{"cat": "Node", "name": "work_kernel_time", "args": {}}],
                       [{"cat": "Node", "name": "unknown_node_event", "args": {}}]):
            with self.subTest(events=events), self.assertRaises(profile.ProfileError):
                profile.verify_profile(events)

    def test_incomplete_or_malformed_duration_fails(self):
        for field, value in (("dur", None), ("dur", -1), ("dur", float("nan")),
                             ("ph", "B"), ("args", [])):
            kernel = self.kernel()
            kernel[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(profile.ProfileError):
                profile.verify_profile([kernel])


class BenchmarkComparisonTests(unittest.TestCase):
    def test_exact_zero_tolerance(self):
        actual = np.array([0, 2, -4], np.float32)
        result = benchmark.error_stats(actual, actual.copy(), 0, 0)
        self.assertTrue(result["passed"])
        self.assertTrue(result["exact"])
        self.assertEqual(result["max_tolerance_ratio"], 0)

    def test_zero_tolerance_rejects_changed_value(self):
        result = benchmark.error_stats(np.array([1.1]), np.array([1]), 0, 0)
        self.assertFalse(result["passed"])
        self.assertEqual(result["mismatched_elements"], 1)
        self.assertIsNone(result["max_tolerance_ratio"])

    def test_explicit_tolerance_reports_nonexact_values(self):
        result = benchmark.error_stats(np.array([1.1, 100.1]), np.array([1, 100]), .01, .001)
        self.assertFalse(result["passed"])
        self.assertFalse(result["exact"])
        self.assertEqual(result["mismatched_elements"], 1)
        self.assertGreater(result["max_tolerance_ratio"], 1)

    def test_nonfinite_and_invalid_tolerances_fail(self):
        result = benchmark.error_stats(np.array([np.nan]), np.array([0]), .1, .1)
        self.assertFalse(result["passed"])
        self.assertEqual(result["nonfinite_elements"], 1)
        with self.assertRaises(ValueError):
            benchmark.error_stats(np.array([0]), np.array([0]), float("nan"), 0)

    def test_head_slices_cover_exact_original_output(self):
        covered = np.zeros(18452, dtype=np.uint8)
        for start, end in benchmark.HEADS.values():
            covered[start:end] += 1
        np.testing.assert_array_equal(covered, 1)


if __name__ == "__main__":
    unittest.main()
