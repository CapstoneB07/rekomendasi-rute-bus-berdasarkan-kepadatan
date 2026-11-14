"""Pengujian offline pemilihan model, output, dan pipeline sweep."""

import contextlib
import csv
import io
import itertools
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import torch

import headcount_sweep_test as sweep


class FakeModel:
    names = {0: "person"}
    task = "detect"

    def __init__(self):
        self.calls = []

    def predict(self, image, **kwargs):
        self.calls.append(kwargs)
        box = types.SimpleNamespace(xyxy=torch.tensor([[2., 2., 10., 14.]]), conf=torch.tensor([0.9]))
        return [types.SimpleNamespace(boxes=[box])]

    def sweep_sizes(self, sizes, strict=False):
        return sizes


class SweepTests(unittest.TestCase):
    def test_output_name_and_existing_output_option(self):
        self.assertEqual(sweep.parse_args([]).output, sweep.DEFAULT_OUTPUT_DIR)
        self.assertEqual(sweep.parse_args(["--name", "rtdetr_01"]).output,
                         sweep.OUTPUTS_DIR / "sweeps" / "rtdetr_01")
        self.assertEqual(sweep.parse_args(["--output", "custom"]).output, Path("custom"))
        self.assertEqual(sweep.parse_args(["--output", "custom", "--name", "run_01"]).output,
                         Path("custom/run_01"))
        for name in ("", " ", ".", "..", "../escape", "a/b", "a\\b", "C:\\run", "run."):
            with self.subTest(name=name), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                sweep.parse_args(["--name", name])

    def test_sweep_sizes_and_unused_iou(self):
        for model_type, expected in (("yolo", 336), ("rtdetr", 84), ("rfdetr", 84)):
            with self.subTest(model_type=model_type):
                parameters = sweep.sweep_parameters(True, model_type)
                self.assertEqual(len(list(itertools.product(*parameters))), expected)
                if model_type in {"rtdetr", "rfdetr"}:
                    self.assertEqual(parameters[1], [None])
        for model_type in ("yolo", "rtdetr", "rfdetr"):
            self.assertEqual(len(list(itertools.product(*sweep.sweep_parameters(False, model_type)))), 12)

    def test_detect_omits_iou_only_for_rtdetr(self):
        for iou in (None, 0.5):
            model = FakeModel()
            sweep.detect(model, np.zeros((16, 16, 3), dtype=np.uint8), 0.25, iou, 320, 0, "cpu", 1)
            self.assertEqual("iou" in model.calls[0], iou is not None)
            self.assertEqual(model.calls[0]["classes"], [0])

    def test_model_loading_and_auto_architecture_detection(self):
        fake_ultralytics = types.ModuleType("ultralytics")
        rtdetr_core = type("RTDETRDetectionModel", (), {})
        yolo_core = type("DetectionModel", (), {})

        class YOLO:
            task = "detect"
            use_rtdetr_core = False

            def __init__(self, path):
                self.model = rtdetr_core() if self.use_rtdetr_core else yolo_core()

        class RTDETR:
            task = "detect"
            use_yolo_core = False

            def __init__(self, path):
                self.model = yolo_core() if self.use_yolo_core else rtdetr_core()

        fake_ultralytics.YOLO, fake_ultralytics.RTDETR = YOLO, RTDETR
        with patch.dict(sys.modules, {"ultralytics": fake_ultralytics}):
            self.assertEqual(sweep.load_model("arbitrary.pt")[1], "yolo")
            YOLO.use_rtdetr_core = True
            model, detected = sweep.load_model("best.pt")
            self.assertEqual(detected, "rtdetr")
            self.assertIsInstance(model, RTDETR)
            self.assertEqual(sweep.load_model("best.pt", "rtdetr")[1], "rtdetr")
            with self.assertRaises(ValueError):
                sweep.load_model("best.pt", "yolo")
            RTDETR.use_yolo_core = True
            with self.assertRaises(ValueError):
                sweep.load_model("yolo.pt", "rtdetr")

    def test_state_dict_checkpoint_has_actionable_error(self):
        fake_ultralytics = types.ModuleType("ultralytics")

        def incompatible_model(path):
            raise AttributeError("'collections.OrderedDict' object has no attribute 'float'")

        fake_ultralytics.YOLO = incompatible_model
        fake_ultralytics.RTDETR = incompatible_model
        with patch.dict(sys.modules, {"ultralytics": fake_ultralytics}):
            with self.assertRaisesRegex(ValueError, "state_dict.*Ultralytics"):
                sweep.load_model("weights_rt-detr.pt", "yolo")

    def test_both_models_write_csv_and_annotations_to_named_folder(self):
        for model_type in ("yolo", "rtdetr", "rfdetr"):
            with self.subTest(model_type=model_type), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                data = root / "dataset"
                (data / "valid/images").mkdir(parents=True)
                (data / "valid/labels").mkdir()
                (data / "data.yaml").write_text("val: valid/images\nnames: [person]\n", encoding="utf-8")
                cv2.imwrite(str(data / "valid/images/sample.jpg"), np.zeros((16, 16, 3), dtype=np.uint8))
                (data / "valid/labels/sample.txt").write_text("0 0.5 0.5 0.5 0.75\n", encoding="utf-8")
                model = FakeModel()
                with patch.object(sweep, "load_model", return_value=(model, model_type)), \
                        patch.object(sweep.torch.cuda, "is_available", return_value=False), \
                        contextlib.redirect_stdout(io.StringIO()):
                    sweep.main(["--data", str(data), "--output", str(root / "runs"),
                                "--name", model_type + "_01", "--top-k", "1"])
                output = root / "runs" / (model_type + "_01")
                with (output / "all_experiments.csv").open(encoding="utf-8-sig", newline="") as file:
                    rows = list(csv.DictReader(file))
                self.assertEqual(len(rows), 12)
                self.assertTrue(all(row["model_type"] == model_type for row in rows))
                self.assertTrue(all(row["valid_headcount"] == "1" for row in rows))
                self.assertTrue(all(row["iou"] == ("0.5" if model_type == "yolo" else "") for row in rows))
                for name in ("configuration_summary.csv", "top_configurations.csv"):
                    self.assertTrue((output / name).is_file())
                self.assertTrue((output / "top_annotated/rank_01/sample.jpg").is_file())


class RFDETRTests(unittest.TestCase):
    def setUp(self):
        import rfdetr_adapter
        self.adapter_module = rfdetr_adapter
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "renamed_checkpoint.pt"
        prefix = "backbone.0.encoder.encoder.embeddings."
        self.state = {
            prefix + "patch_embeddings.projection.weight": torch.zeros(384, 3, 16, 16),
            prefix + "position_embeddings": torch.zeros(1, 577, 384),
            "class_embed.weight": torch.zeros(2, 256),
            "transformer.decoder.layers.0.weight": torch.zeros(1),
            "transformer.decoder.layers.1.weight": torch.zeros(1),
        }
        torch.save({"model": self.state, "args": {"class_names": ["person"]}}, self.path)

        class FakeRFDETR:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.model_config = types.SimpleNamespace(patch_size=16, num_windows=2)

            def predict(self, image, **kwargs):
                self.last_image, self.last_kwargs = image, kwargs
                return types.SimpleNamespace(
                    xyxy=np.asarray([[2., 2., 10., 14.], [1., 1., 3., 3.]]),
                    confidence=np.asarray([0.9, 0.8]), class_id=np.asarray([0, 1]),
                )

        self.fake = types.ModuleType("rfdetr")
        for name in rfdetr_adapter.VARIANTS.values():
            setattr(self.fake, name, FakeRFDETR)

    def test_native_checkpoint_variant_color_filter_and_box_conversion(self):
        with patch.dict(sys.modules, {"rfdetr": self.fake}):
            adapter = self.adapter_module.RFDETRAdapter(self.path)
        self.assertEqual(adapter.variant, "nano")
        self.assertEqual(adapter.names, {0: "person"})
        self.assertEqual(adapter.model.kwargs["num_classes"], 1)
        image = np.full((16, 16, 3), [1, 2, 3], dtype=np.uint8)
        result, _ = sweep.detect(adapter, image, 0.25, None, 320, 0, "cpu", 1)
        self.assertEqual(adapter.model.last_image[0, 0].tolist(), [3, 2, 1])
        self.assertEqual(adapter.model.last_kwargs, {"threshold": 0.25, "shape": (320, 320)})
        boxes, _, raw = sweep.filtered_boxes(result, image.shape, 0.0005, 0.7, 0.2)
        self.assertEqual(raw, 1)
        self.assertEqual(len(boxes), 1)

    def test_input_sizes_are_recorded_at_their_actual_multiple(self):
        with patch.dict(sys.modules, {"rfdetr": self.fake}):
            adapter = self.adapter_module.RFDETRAdapter(self.path)
        self.assertEqual(adapter.sweep_sizes([321, 416]), [352, 416])
        with self.assertRaises(ValueError):
            adapter.sweep_sizes([321], strict=True)

    def test_explicit_rfdetr_does_not_require_ultralytics(self):
        with patch.dict(sys.modules, {"rfdetr": self.fake, "ultralytics": None}):
            model, detected = sweep.load_model(str(self.path), "rfdetr")
        self.assertEqual(detected, "rfdetr")
        self.assertEqual(model.variant, "nano")

    def test_missing_class_names_requires_explicit_model_class(self):
        torch.save({"model": self.state, "args": {"class_names": None}}, self.path)
        with patch.dict(sys.modules, {"rfdetr": self.fake}):
            model, _ = sweep.load_model(str(self.path), "rfdetr")
        self.assertEqual(set(model.names), {0, 1})
        with self.assertRaises(ValueError):
            sweep.person_class(model.names, None, "model.names")
        self.assertEqual(sweep.person_class(model.names, 1, "model.names"), 1)

    def test_auto_loader_dispatches_native_state_dict(self):
        fake_ultralytics = types.ModuleType("ultralytics")

        def incompatible(path):
            raise AttributeError("'collections.OrderedDict' object has no attribute 'float'")

        fake_ultralytics.YOLO = fake_ultralytics.RTDETR = incompatible
        with patch.dict(sys.modules, {"ultralytics": fake_ultralytics, "rfdetr": self.fake}):
            model, detected = sweep.load_model(str(self.path))
        self.assertEqual(detected, "rfdetr")
        self.assertEqual(model.variant, "nano")


if __name__ == "__main__":
    unittest.main()
