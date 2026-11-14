"""Adapter checkpoint RF-DETR native ke antarmuka sweep headcount.

Paket rfdetr diimpor hanya ketika model RF-DETR dipilih.
"""

import argparse
import logging
import math
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import torch

LOG = logging.getLogger("headcount")
VARIANTS = {
    "nano": "RFDETRNano", "small": "RFDETRSmall", "medium": "RFDETRMedium",
    "large": "RFDETRLarge", "base": "RFDETRBase",
}


def read_checkpoint(path):
    with torch.serialization.safe_globals([argparse.Namespace]):
        checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    if not isinstance(checkpoint, Mapping):
        raise ValueError("Checkpoint RF-DETR harus berupa dictionary")
    state = checkpoint.get("model")
    if not isinstance(state, Mapping) or "class_embed.weight" not in state:
        raise ValueError("Checkpoint tidak berisi state_dict RF-DETR detection")
    if not any("backbone.0.encoder.encoder.embeddings" in key for key in state):
        raise ValueError("Checkpoint tidak memiliki backbone DINO RF-DETR yang didukung")
    return checkpoint, state


def checkpoint_variant(state):
    """Kenali varian standar dari bentuk bobot, tanpa menebak dari nama file."""
    prefix = "backbone.0.encoder.encoder.embeddings."
    patch = state[prefix + "patch_embeddings.projection.weight"]
    positions = state[prefix + "position_embeddings"]
    layers = {int(key.split(".")[3]) for key in state if key.startswith("transformer.decoder.layers.")}
    signature = (patch.shape[-1], len(layers), patch.shape[0])
    if signature == (16, 2, 384):
        return "nano"
    if signature == (16, 3, 384):
        return "small"
    if signature == (16, 4, 384):
        grid = math.isqrt(positions.shape[1] - 1)
        if grid == 36:
            return "medium"
        if grid == 44:
            return "large"
    if signature == (14, 3, 384):
        return "base"
    raise ValueError("Varian RF-DETR tidak dapat dipastikan. Isi --rfdetr-variant sesuai model training.")


class RFDETRAdapter:
    task = "detect"

    def __init__(self, path, variant="auto", device="cpu"):
        path = Path(path).expanduser().resolve()
        checkpoint, state = read_checkpoint(path)
        self.variant = checkpoint_variant(state) if variant == "auto" else variant
        if self.variant not in VARIANTS:
            raise ValueError(f"Varian RF-DETR tidak didukung: {self.variant}")
        try:
            import rfdetr
        except ImportError as exc:
            raise SystemExit(
                "RF-DETR memerlukan dependency opsional. Jalankan: "
                "python -m pip install -r cv/script/requirements-rfdetr.txt"
            ) from exc

        args = checkpoint.get("args", {})
        if isinstance(args, argparse.Namespace):
            args = vars(args)
        config = checkpoint.get("model_config") or {}
        prefix = "backbone.0.encoder.encoder.embeddings."
        grid = math.isqrt(state[prefix + "position_embeddings"].shape[1] - 1)
        if grid * grid != state[prefix + "position_embeddings"].shape[1] - 1:
            raise ValueError("Bentuk positional embedding RF-DETR tidak dikenali")
        count = int(state["class_embed.weight"].shape[0] - 1)
        if count < 1:
            raise ValueError("Checkpoint tidak memiliki kelas objek")
        self.device = str(torch.device(device))
        kwargs = dict(pretrain_weights=str(path), num_classes=count, device=self.device,
                      positional_encoding_size=grid)
        # Metadata modern mengalahkan default varian jika training mengubah arsitektur.
        for name in ("resolution", "patch_size", "num_windows", "dec_layers", "num_queries",
                     "num_select", "group_detr", "hidden_dim", "encoder", "out_feature_indexes",
                     "projector_scale"):
            if name in config:
                kwargs[name] = config[name]
            elif name in args:
                kwargs[name] = args[name]
        self.model = getattr(rfdetr, VARIANTS[self.variant])(**kwargs)
        model_config = self.model.model_config
        self.size_multiple = model_config.patch_size * model_config.num_windows
        names = config.get("class_names") or args.get("class_names")
        if isinstance(names, Mapping):
            self.names = {int(key): str(value) for key, value in names.items()}
        elif isinstance(names, list) and len(names) == count:
            self.names = dict(enumerate(names))
        else:
            # Checkpoint lama bisa memakai ID 1 untuk kelas tunggal. Tanpa metadata,
            # jangan menebak slot foreground/background atau memakai label COCO bawaan.
            self.names = {index: f"class_{index}" for index in range(count + 1)}
            LOG.warning("RF-DETR tanpa nama kelas: pilih ID orang dengan --model-class-id; tersedia %s", list(self.names))
        LOG.info("RF-DETR variant=%s | classes=%d | input multiple=%d", self.variant, count, self.size_multiple)

    def sweep_sizes(self, sizes, strict=False):
        if strict and any(size <= 0 or size % self.size_multiple for size in sizes):
            raise ValueError(f"--imgsz RF-DETR harus kelipatan {self.size_multiple}")
        actual = list(dict.fromkeys(math.ceil(size / self.size_multiple) * self.size_multiple for size in sizes))
        if actual != sizes:
            LOG.info("Ukuran RF-DETR disesuaikan ke kelipatan patch/window: %s -> %s", sizes, actual)
        return actual

    def predict(self, image, conf=0.25, imgsz=640, classes=None, device=None, verbose=False):
        if device is not None and str(torch.device(device)) != self.device:
            raise ValueError(f"RF-DETR dimuat pada {self.device}, tetapi inferensi meminta {device}")
        self.sweep_sizes([imgsz], strict=True)
        # API RF-DETR menerima RGB, sedangkan cv2.imread/preprocess menghasilkan BGR.
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        detections = self.model.predict(rgb, threshold=conf, shape=(imgsz, imgsz))
        selected = np.ones(len(detections.xyxy), dtype=bool)
        if classes is not None:
            selected = np.isin(detections.class_id, classes)
        boxes = [
            SimpleNamespace(xyxy=torch.as_tensor(np.asarray(xyxy)[None, :]),
                            conf=torch.as_tensor([confidence]))
            for xyxy, confidence in zip(detections.xyxy[selected], detections.confidence[selected])
        ]
        return [SimpleNamespace(boxes=boxes)]
