"""Evaluasi headcount YOLO26 (dan YOLO Ultralytics lain) pada dataset YOLO detection.

Contoh:
    python script/headcount_sweep_test.py --split val
    python script/headcount_sweep_test.py --data script/datasets/dataset_full --model script/models/weights.pt --split val

Dataset standar:
    dataset/data.yaml
    dataset/test/images/xxx.jpg
    dataset/test/labels/xxx.txt  # tiap baris: class_id x_center y_center width height

Perhatian: sweep hyperparameter harus menggunakan validation set, bukan test set final.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import logging
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import torch
import yaml

from cv_paths import DATASETS_DIR, MODELS_DIR, OUTPUTS_DIR

LOG = logging.getLogger("headcount")
EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
FULL_CONF = [0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]
FULL_IOU = [0.40, 0.50, 0.60, 0.70]
FULL_IMGSZ = [320, 416, 512, 640]
FULL_PREPROCESS = ["none", "always", "adaptive"]
DETAIL_FIELDS = [
    "timestamp", "image", "label", "conf", "iou", "imgsz", "preprocess",
    "image_width", "image_height", "brightness", "contrast", "clahe_applied",
    "actual_count", "raw_detections", "valid_headcount", "count_error", "abs_error",
    "count_accuracy_c251", "count_accuracy_bounded", "lf", "low_area_rejected",
    "high_area_rejected", "aspect_rejected", "preprocess_ms", "inference_ms",
    "postprocess_ms", "pipeline_cv_ms", "device", "model", "gt_class_id",
    "model_class_id",
]
SUMMARY_FIELDS = [
    "conf", "iou", "imgsz", "preprocess", "images", "mae", "rmse", "exact_count_rate",
    "mean_count_accuracy_c251", "mean_count_accuracy_bounded", "mean_pipeline_cv_ms",
    "mean_inference_ms", "mean_preprocess_ms", "mean_postprocess_ms",
]


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Headcount sweep untuk anotasi YOLO detection (YOLO26-compatible)")
    p.add_argument("--data", type=Path, default=DATASETS_DIR / "dataset_full" / "data.yaml",
                   help="data.yaml atau folder root dataset YOLO")
    p.add_argument("--model", default=str(MODELS_DIR / "yolo26n.pt"), help=".pt pretrained atau best.pt fine-tuned")
    p.add_argument("--split", choices=("train", "val", "valid", "test"), default="val",
                   help="Gunakan val untuk tuning; test hanya untuk evaluasi final")
    p.add_argument("--gt-class-id", type=int, default=None,
                   help="Class ID orang pada data.yaml; auto-detect dari names jika tidak diisi")
    p.add_argument("--model-class-id", type=int, default=None,
                   help="Class ID orang pada model; auto-detect dari model.names")
    p.add_argument("--max-images", type=int, default=None)
    p.add_argument("--capacity", type=int, default=80)
    p.add_argument("--output", type=Path, default=OUTPUTS_DIR / "sweeps" / "current")
    p.add_argument("--full-sweep", action="store_true",
                   help="Sweep asli: 7 conf x 4 IoU x 4 imgsz x 3 preprocessing = 336 konfigurasi")
    p.add_argument("--benchmark-runs", type=int, default=1)
    p.add_argument("--warmup-runs", type=int, default=1)
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--no-annotations", action="store_true")
    p.add_argument("--strict-labels", action="store_true",
                   help="Gagal jika ada label .txt hilang (YOLO biasanya menganggapnya negatif/0 objek)")
    p.add_argument("--min-area-ratio", type=float, default=0.0005)
    p.add_argument("--max-area-ratio", type=float, default=0.70)
    p.add_argument("--min-aspect-ratio", type=float, default=0.20)
    return p.parse_args(argv)


def class_map(names):
    if isinstance(names, list):
        return {i: str(v) for i, v in enumerate(names)}
    if isinstance(names, dict):
        return {int(k): str(v) for k, v in names.items()}
    raise ValueError("names pada data.yaml/model harus list atau dict")


def person_class(names, explicit, source):
    items = class_map(names)
    if explicit is not None:
        if explicit not in items:
            raise ValueError(f"Class ID {explicit} tidak terdaftar di {source}: {items}")
        return explicit
    for wanted in ("person", "people", "passenger", "penumpang", "orang", "human"):
        matches = [i for i, name in items.items() if name.strip().casefold() == wanted]
        if len(matches) == 1:
            return matches[0]
    if len(items) == 1:
        only_id = next(iter(items))
        LOG.warning("%s satu kelas (%s); diasumsikan mewakili orang", source, items[only_id])
        return only_id
    raise ValueError(f"Tidak dapat mengidentifikasi kelas orang pada {source}: {items}. "
                     "Set --gt-class-id / --model-class-id secara eksplisit.")


def dataset_info(data_path, split):
    data_path = data_path.expanduser().resolve()
    yaml_path = data_path if data_path.is_file() else data_path / "data.yaml"
    if not yaml_path.is_file():
        raise FileNotFoundError(f"data.yaml tidak ditemukan: {yaml_path}")
    cfg = yaml.safe_load(yaml_path.read_text(encoding="utf-8-sig"))
    if not isinstance(cfg, dict) or "names" not in cfg:
        raise ValueError(f"data.yaml harus memiliki field 'names': {yaml_path}")
    root = yaml_path.parent
    if cfg.get("path"):
        cfgroot = Path(str(cfg["path"]))
        root = (cfgroot if cfgroot.is_absolute() else root / cfgroot).resolve()
    split_key = "val" if split == "valid" else split
    location = cfg.get(split_key) or (cfg.get("valid") if split_key == "val" else None)
    candidates = []
    if isinstance(location, str):
        loc = Path(location)
        if not loc.is_absolute():
            candidates.extend([(root / loc).resolve(), (yaml_path.parent / loc).resolve()])
        else:
            candidates.append(loc)
    # Roboflow export dan format YOLO standar menggunakan kedua pola ini.
    dirs = ("valid", "val") if split_key == "val" else (split_key,)
    for directory in dirs:
        candidates.extend([root / directory / "images", yaml_path.parent / directory / "images"])
    images_dir = next((p for p in candidates if p.is_dir()), None)
    if images_dir is None:
        raise FileNotFoundError(f"Tidak menemukan folder gambar split '{split_key}'. Coba: {candidates}")
    images_dir = images_dir.resolve()
    if images_dir.name != "images":
        raise ValueError(f"Folder split harus menunjuk ke direktori 'images', diperoleh: {images_dir}")
    labels_dir = images_dir.parent / "labels"
    if not labels_dir.is_dir():
        raise FileNotFoundError(f"Folder label YOLO tidak ditemukan: {labels_dir}")
    return cfg, images_dir, labels_dir


def read_yolo_count(label_path, target_class, strict=False):
    """Jumlah object kelas target dari YOLO detection TXT, termasuk file kosong -> 0.

    Format hanya klasifikasi bbox: cls xc yc w h (normalized). Tidak untuk segmentasi.
    """
    if not label_path.exists():
        if strict:
            raise FileNotFoundError(f"Label tidak ditemukan: {label_path}")
        LOG.warning("Label tidak ditemukan; diasumsikan 0 objek: %s", label_path)
        return 0
    count = 0
    for line_no, raw in enumerate(label_path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not raw.strip():
            continue
        parts = raw.split()
        if len(parts) != 5:
            raise ValueError(f"Label YOLO detection harus 5 kolom: {label_path}:{line_no}")
        try:
            values = [float(v) for v in parts]
            cls = values[0]
            if not cls.is_integer() or cls < 0:
                raise ValueError("class ID bukan integer non-negatif")
            if any(not np.isfinite(v) for v in values):
                raise ValueError("nilai non-finite")
            if any(not 0 <= v <= 1 for v in values[1:]):
                raise ValueError("koordinat bukan nilai 0..1")
            if values[3] <= 0 or values[4] <= 0:
                raise ValueError("lebar atau tinggi bounding box 0")
            if int(cls) == target_class:
                count += 1
        except ValueError as e:
            raise ValueError(f"Label invalid di {label_path}:{line_no}: {raw!r} ({e})") from e
    return count


def counting_metrics(actual, predicted):
    err = predicted - actual
    ae = abs(err)
    # Definisi pada persamaan Bab 4.8: (1 - |pred - GT| / GT) * 100%.
    # Ketika GT=0, metrik secara matematis undefined; gunakan konvensi operasional 100/0.
    accuracy = 100.0 if (actual == 0 and predicted == 0) else (0.0 if actual == 0 else
                 (1.0 - ae / actual) * 100.0)
    return err, ae, accuracy, max(0.0, accuracy)


def enhance(image):
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    cl = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8)).apply(l)
    return cv2.cvtColor(cv2.merge((cl, a, b)), cv2.COLOR_LAB2BGR)


def preprocess(image, mode):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    brightness, contrast = float(np.mean(gray)), float(np.std(gray))
    applied = mode == "always" or (mode == "adaptive" and (brightness < 70 or contrast < 35))
    return enhance(image) if applied else image, brightness, contrast, applied


def sync_cuda(device):
    if str(device).startswith("cuda"):
        torch.cuda.synchronize()


def detect(model, image, conf, iou, imgsz, class_id, device, benchmark_runs):
    # Pengukuran wall-clock termasuk overhead Ultralytics, bukan hanya forward pass network.
    result = None
    timings = []
    for _ in range(benchmark_runs):
        sync_cuda(device)
        start = time.perf_counter()
        result = model.predict(image, conf=conf, iou=iou, imgsz=imgsz,
                               classes=[class_id], device=device, verbose=False)[0]
        sync_cuda(device)
        timings.append((time.perf_counter() - start) * 1000)
    return result, float(np.mean(timings))


def filtered_boxes(result, shape, min_area, max_area, min_aspect):
    h, w = shape[:2]
    boxes = []
    rejected = {"low_area_rejected": 0, "high_area_rejected": 0, "aspect_rejected": 0}
    if result.boxes is None:
        return boxes, rejected, 0
    raw = len(result.boxes)
    for box in result.boxes:
        x1, y1, x2, y2 = map(float, box.xyxy[0].detach().cpu().tolist())
        score = float(box.conf[0].item())
        bw, bh = x2 - x1, y2 - y1
        if bw <= 0 or bh <= 0 or bh / bw < min_aspect:
            rejected["aspect_rejected"] += 1
            continue
        ratio = bw * bh / (w * h)
        if ratio < min_area:
            rejected["low_area_rejected"] += 1
            continue
        if ratio > max_area:
            rejected["high_area_rejected"] += 1
            continue
        boxes.append((int(x1), int(y1), int(x2), int(y2), score))
    return boxes, rejected, raw


def one_inference(model, frame, img_path, label, actual, conf, iou, imgsz, mode,
                  gt_class, model_class, args, device):
    start = time.perf_counter()
    processed, brightness, contrast, clahe = preprocess(frame, mode)
    pre_ms = (time.perf_counter() - start) * 1000
    result, infer_ms = detect(model, processed, conf, iou, imgsz, model_class, device, args.benchmark_runs)
    start = time.perf_counter()
    boxes, rejected, raw = filtered_boxes(result, processed.shape, args.min_area_ratio,
                                         args.max_area_ratio, args.min_aspect_ratio)
    post_ms = (time.perf_counter() - start) * 1000
    count = len(boxes)
    err, ae, acc, bounded = counting_metrics(actual, count)
    row = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "image": str(img_path), "label": str(label), "conf": conf, "iou": iou,
        "imgsz": imgsz, "preprocess": mode, "image_width": frame.shape[1],
        "image_height": frame.shape[0], "brightness": brightness, "contrast": contrast,
        "clahe_applied": clahe, "actual_count": actual, "raw_detections": raw,
        "valid_headcount": count, "count_error": err, "abs_error": ae,
        "count_accuracy_c251": acc, "count_accuracy_bounded": bounded,
        "lf": count / args.capacity, **rejected, "preprocess_ms": pre_ms,
        "inference_ms": infer_ms, "postprocess_ms": post_ms,
        "pipeline_cv_ms": pre_ms + infer_ms + post_ms, "device": device,
        "model": args.model, "gt_class_id": gt_class, "model_class_id": model_class,
    }
    return row, boxes, processed


def config_tuple(row):
    return (float(row["conf"]), float(row["iou"]), int(row["imgsz"]), row["preprocess"])


def summarize(rows):
    grouped = defaultdict(list)
    for r in rows:
        grouped[config_tuple(r)].append(r)
    summary = []
    for (conf, iou, imgsz, prep), group in grouped.items():
        arr = lambda k: np.asarray([float(r[k]) for r in group])
        ae = arr("abs_error")
        summary.append({
            "conf": conf, "iou": iou, "imgsz": imgsz, "preprocess": prep,
            "images": len(group), "mae": float(np.mean(ae)),
            "rmse": float(np.sqrt(np.mean(arr("count_error") ** 2))),
            "exact_count_rate": float(np.mean(ae == 0) * 100),
            "mean_count_accuracy_c251": float(np.mean(arr("count_accuracy_c251"))),
            "mean_count_accuracy_bounded": float(np.mean(arr("count_accuracy_bounded"))),
            "mean_pipeline_cv_ms": float(np.mean(arr("pipeline_cv_ms"))),
            "mean_inference_ms": float(np.mean(arr("inference_ms"))),
            "mean_preprocess_ms": float(np.mean(arr("preprocess_ms"))),
            "mean_postprocess_ms": float(np.mean(arr("postprocess_ms"))),
        })
    # MAE utama: tidak bias akibat clamp accuracy 0% dan GT=0.
    summary.sort(key=lambda s: (s["mae"], -s["exact_count_rate"], s["mean_pipeline_cv_ms"]))
    return summary


def save_csv(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{k: row.get(k, "") for k in fields} for row in rows])


def save_annotation(image, boxes, row, path):
    canvas = image.copy()  # bbox koordinat relatif pada image ter-preprocess
    for x1, y1, x2, y2, score in boxes:
        cv2.rectangle(canvas, (x1, y1), (x2, y2), (255, 0, 0), 2)
        cv2.putText(canvas, f"person {score:.2f}", (x1, max(y1 - 5, 15)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 0, 0), 1)
    cv2.putText(canvas, f"GT: {row['actual_count']} | Prediction: {row['valid_headcount']}",
                (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    cv2.imwrite(str(path), canvas)


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.capacity <= 0 or args.benchmark_runs < 1 or args.warmup_runs < 0 or args.top_k < 0:
        raise ValueError("capacity, benchmark-runs harus positif; warmup-runs/top-k >= 0")
    cfg, image_dir, label_dir = dataset_info(args.data, args.split)
    gt_class = person_class(cfg["names"], args.gt_class_id, "data.yaml")
    images = sorted(p for p in image_dir.rglob("*") if p.suffix.lower() in EXTENSIONS and p.is_file())
    if args.max_images is not None:
        images = images[:args.max_images]
    if not images:
        raise ValueError(f"Tidak ada gambar di {image_dir}")
    pairs = [(p, label_dir / p.relative_to(image_dir).with_suffix(".txt")) for p in images]
    missing = [lbl for _, lbl in pairs if not lbl.is_file()]
    if missing:
        if args.strict_labels:
            raise FileNotFoundError(f"Ada {len(missing)} label tidak ditemukan, contoh: {missing[:3]}")
        LOG.warning("Ada %d gambar tanpa label .txt; YOLO menganggapnya gambar negatif (0 objek).", len(missing))
    # Dibaca sekali di awal agar error label diketahui sebelum proses inferensi panjang.
    counts = {p: read_yolo_count(lbl, gt_class, strict=args.strict_labels) for p, lbl in pairs}

    try:
        from ultralytics import YOLO
    except ImportError as e:
        raise SystemExit("Paket ultralytics belum terpasang. Jalankan: pip install ultralytics") from e

    model = YOLO(args.model)
    model_class = person_class(model.names, args.model_class_id, "model.names")
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    if args.full_sweep:
        confs, ious, sizes, preps = FULL_CONF, FULL_IOU, FULL_IMGSZ, FULL_PREPROCESS
    else:
        confs, ious, sizes, preps = [0.15, 0.25, 0.40], [0.50], [416, 640], ["none", "adaptive"]
    configs = list(itertools.product(confs, ious, sizes, preps))
    LOG.info("Dataset: %s | images=%d | GT person class=%d | model person class=%d",
             image_dir, len(pairs), gt_class, model_class)
    LOG.info("Model: %s | device: %s | configs: %d | estimated predictions: %d",
             args.model, device, len(configs), len(configs) * len(pairs) * args.benchmark_runs)
    LOG.info("IoU sweep mungkin tidak berpengaruh pada model YOLO26 end-to-end yang NMS-free; "
             "bandingkan output untuk memverifikasi.")
    if args.split in {"test"} and len(configs) > 1:
        LOG.warning("Sweep pada test set menghasilkan pemilihan hyperparameter yang bias. "
                    "Gunakan --split val untuk tuning, lalu test sekali dengan konfigurasi terpilih.")

    args.output.mkdir(parents=True, exist_ok=True)
    rows = []
    details_file = args.output / "all_experiments.csv"
    with details_file.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=DETAIL_FIELDS)
        writer.writeheader()
        # Warmup sekali per imgsz, lebih masuk akal daripada tiap gambar dan kombinasi.
        seed = cv2.imread(str(pairs[0][0]))
        if seed is None:
            raise ValueError(f"Gambar pertama gagal dibaca: {pairs[0][0]}")
        for size in sizes:
            for _ in range(args.warmup_runs):
                model.predict(seed, imgsz=size, classes=[model_class], device=device, verbose=False)
        for ix, (image, label) in enumerate(pairs, 1):
            frame = cv2.imread(str(image))
            if frame is None:
                LOG.warning("Gagal membaca gambar, dilewati: %s", image)
                continue
            actual = counts[image]
            for conf, iou, imgsz, mode in configs:
                row, _, _ = one_inference(model, frame, image, label, actual, conf, iou,
                                          imgsz, mode, gt_class, model_class, args, device)
                writer.writerow(row)
                rows.append(row)
            f.flush()
            LOG.info("[%d/%d] %s | GT=%d | %d configs", ix, len(pairs), image.name, actual, len(configs))
    if not rows:
        raise RuntimeError("Tidak ada hasil inferensi; cek gambar dataset")
    summary = summarize(rows)
    save_csv(args.output / "configuration_summary.csv", summary, SUMMARY_FIELDS)
    top = summary[:args.top_k]
    save_csv(args.output / "top_configurations.csv", top, SUMMARY_FIELDS)
    if not args.no_annotations and top:
        output_images = args.output / "top_annotated"
        output_images.mkdir(parents=True, exist_ok=True)
        # Simpan hanya konfigurasi teratas; lakukan inferensi ulang agar tidak menyimpan
        # jutaan box di RAM selama full-sweep.
        for rank, config in enumerate(top, 1):
            folder = output_images / f"rank_{rank:02d}"
            folder.mkdir(exist_ok=True)
            for image, label in pairs:
                frame = cv2.imread(str(image))
                if frame is None:
                    continue
                row, boxes, processed = one_inference(
                    model, frame, image, label, counts[image], config["conf"], config["iou"],
                    config["imgsz"], config["preprocess"], gt_class, model_class, args, device)
                # Filename disambiguates nested dataset paths.
                rel = image.relative_to(image_dir)
                out = folder / rel.with_suffix(".jpg")
                out.parent.mkdir(parents=True, exist_ok=True)
                save_annotation(processed, boxes, row, out)
    print("\n=== TOP CONFIGURATIONS (ranking MAE -> exact -> latency) ===")
    for i, r in enumerate(top, 1):
        print(f"{i}. conf={r['conf']:.2f}, iou={r['iou']:.2f}, imgsz={r['imgsz']}, "
              f"pre={r['preprocess']}, MAE={r['mae']:.3f}, "
              f"exact={r['exact_count_rate']:.1f}%, latency={r['mean_pipeline_cv_ms']:.1f} ms")
    print(f"\nOutput: {args.output.resolve()}")
    print("CATATAN: mAP/precision/recall deteksi bounding-box belum dihitung dalam script ini. "
          "Gunakan model.val(data='...', split='test') untuk itu.")


if __name__ == "__main__":
    main()
