import csv
import itertools
import os
import time
from pathlib import Path
from datetime import datetime

import cv2
import numpy as np
import torch
from ultralytics import YOLO


# ============================================================
# AUTOMATED HEADCOUNT EXPERIMENT
# ============================================================
#
# Tujuan:
# 1. Menguji banyak gambar ESP32-CAM secara otomatis.
# 2. Menguji kombinasi confidence, IoU, imgsz, preprocessing.
# 3. Mencatat headcount, LF, latency, dan ground-truth metrics.
# 4. Membantu memilih konfigurasi sebelum fine-tuning.
#
# Struktur folder contoh:
#
# dataset_test/
#   img_001.jpg
#   img_002.jpg
#   img_003.jpg
#
# ground_truth.csv
#   image,actual_count
#   img_001.jpg,2
#   img_002.jpg,5
#
# PENTING:
# - Test set jangan dipakai untuk training/fine-tuning.
# - "imgsz" = resolusi input model YOLO, BUKAN resolusi sensor ESP32-CAM.
# - Untuk menguji resolusi kamera asli, ambil dataset dengan resolusi
#   sensor yang berbeda lalu jalankan script ini pada folder masing-masing.
# ============================================================


# ============================================================
# 1. KONFIGURASI DATASET
# ============================================================

MODEL_PATH = "yolo26n.pt"

IMAGE_DIR = Path("dataset_test")
GROUND_TRUTH_CSV = Path("ground_truth.csv")

MAX_CAPACITY = 80

# True = membaca actual_count dari ground_truth.csv
# False = tetap menjalankan inference tetapi metrik akurasi tidak dihitung.
USE_GROUND_TRUTH = True


# ============================================================
# 2. PARAMETER YANG AKAN DI-SWEEP
# ============================================================

# Mulai dari kombinasi yang masuk akal.
# Bisa ditambah setelah eksperimen awal.
CONF_VALUES = [0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]

IOU_VALUES = [0.40, 0.50, 0.60, 0.70]

# Ini adalah resolusi/input size YOLO.
IMGSZ_VALUES = [320, 416, 512, 640]

# Mode preprocessing.
#
# "none"     : tanpa CLAHE
# "always"   : CLAHE selalu
# "adaptive" : CLAHE hanya jika brightness/contrast rendah
PREPROCESS_MODES = ["none", "always", "adaptive"]

# Untuk eksperimen awal, ROI dibuat full image.
# Tambahkan ROI lain kalau sudah tahu area kamera yang tidak relevan.
ROI_VALUES = [
    ("full", (0.0, 0.0, 1.0, 1.0)),
]

# Jika True, hanya konfigurasi dengan hasil valid terbaik
# yang dianalisis/ditampilkan lebih lanjut.
# Semua hasil tetap masuk CSV.
SAVE_ANNOTATED_FOR_TOP = True
TOP_CONFIGS_TO_SAVE = 5

# Benchmark inference.
# 1 cukup untuk sweep besar.
# Setelah konfigurasi terbaik ditemukan, bisa dinaikkan menjadi 5 atau 10.
BENCHMARK_RUNS = 1
WARMUP_RUNS = 1

# Batasi jumlah gambar saat eksperimen awal.
# None = semua gambar.
MAX_IMAGES = None

# Ekstensi yang dicari.
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


# ============================================================
# 3. POST-PROCESSING FILTER
# ============================================================

MIN_AREA_RATIO = 0.0005
MAX_AREA_RATIO = 0.70
MIN_ASPECT_RATIO = 0.20


# ============================================================
# 4. OUTPUT
# ============================================================

RESULT_DIR = Path("headcount_sweep_results")
RESULT_DIR.mkdir(parents=True, exist_ok=True)

RESULT_CSV = RESULT_DIR / "all_experiments.csv"
SUMMARY_CSV = RESULT_DIR / "configuration_summary.csv"
TOP_CSV = RESULT_DIR / "top_configurations.csv"
ANNOTATED_DIR = RESULT_DIR / "top_annotated"

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


# ============================================================
# UTILITY
# ============================================================

def timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def synchronize_device():
    if torch.cuda.is_available():
        torch.cuda.synchronize()


def safe_enhance(image):
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    clahe = cv2.createCLAHE(
        clipLimit=1.5,
        tileGridSize=(8, 8)
    )

    cl = clahe.apply(l)
    limg = cv2.merge((cl, a, b))

    return cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)


def get_quality(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    brightness = float(np.mean(gray))
    contrast = float(np.std(gray))
    return brightness, contrast


def apply_roi(image, roi):
    h, w = image.shape[:2]

    rx1, ry1, rx2, ry2 = roi

    x1 = max(0, min(w - 1, int(rx1 * w)))
    y1 = max(0, min(h - 1, int(ry1 * h)))
    x2 = max(x1 + 1, min(w, int(rx2 * w)))
    y2 = max(y1 + 1, min(h, int(ry2 * h)))

    return image[y1:y2, x1:x2]


def preprocess(image, mode, roi):
    processed = apply_roi(image, roi)

    brightness, contrast = get_quality(processed)

    clahe_applied = False

    if mode == "always":
        processed = safe_enhance(processed)
        clahe_applied = True

    elif mode == "adaptive":
        if brightness < 70.0 or contrast < 35.0:
            processed = safe_enhance(processed)
            clahe_applied = True

    return processed, brightness, contrast, clahe_applied


def find_images():
    if not IMAGE_DIR.exists():
        raise FileNotFoundError(
            f"Folder dataset tidak ditemukan: {IMAGE_DIR.resolve()}"
        )

    files = sorted(
        p for p in IMAGE_DIR.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )

    if MAX_IMAGES is not None:
        files = files[:MAX_IMAGES]

    if not files:
        raise FileNotFoundError(
            f"Tidak ada gambar di: {IMAGE_DIR.resolve()}"
        )

    return files


def load_ground_truth():
    gt = {}

    if not USE_GROUND_TRUTH:
        return gt

    if not GROUND_TRUTH_CSV.exists():
        raise FileNotFoundError(
            f"Ground truth CSV tidak ditemukan: "
            f"{GROUND_TRUTH_CSV.resolve()}"
        )

    with open(GROUND_TRUTH_CSV, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        required = {"image", "actual_count"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise ValueError(
                "ground_truth.csv harus memiliki kolom: "
                "image,actual_count"
            )

        for row in reader:
            name = Path(row["image"]).name
            gt[name] = int(row["actual_count"])

    return gt


def counting_metrics(actual, predicted):
    if actual is None:
        return {
            "count_error": "",
            "abs_error": "",
            "count_accuracy_c251": "",
            "count_accuracy_bounded": "",
        }

    error = predicted - actual
    abs_error = abs(error)

    # Pendekatan C-251 yang sedang dipakai:
    # detected / actual * 100
    #
    # Catatan: jika predicted > actual, nilai ini bisa >100%.
    if actual > 0:
        c251_accuracy = (predicted / actual) * 100.0

        # Versi bounded untuk evaluasi praktis:
        # 100% jika tepat, turun sesuai absolute error.
        bounded_accuracy = max(
            0.0,
            100.0 - (abs_error / actual * 100.0)
        )
    else:
        # Untuk actual=0:
        # benar jika prediksi juga 0, selain itu 0%.
        c251_accuracy = 100.0 if predicted == 0 else 0.0
        bounded_accuracy = c251_accuracy

    return {
        "count_error": error,
        "abs_error": abs_error,
        "count_accuracy_c251": c251_accuracy,
        "count_accuracy_bounded": bounded_accuracy,
    }


def config_key(conf, iou, imgsz, preprocess_mode, roi_name):
    return (
        f"conf{conf:.2f}_"
        f"iou{iou:.2f}_"
        f"imgsz{imgsz}_"
        f"prep-{preprocess_mode}_"
        f"roi-{roi_name}"
    )


# ============================================================
# INFERENCE
# ============================================================

def run_one(
    model,
    frame,
    image_path,
    conf,
    iou,
    imgsz,
    preprocess_mode,
    roi_name,
    roi,
    actual_count,
):
    original_h, original_w = frame.shape[:2]

    prep_start = time.perf_counter()

    processed, brightness, contrast, clahe_applied = preprocess(
        frame,
        preprocess_mode,
        roi,
    )

    preprocess_ms = (time.perf_counter() - prep_start) * 1000

    # Warm-up untuk konfigurasi ini.
    for _ in range(WARMUP_RUNS):
        _ = model(
            processed,
            classes=[0],
            conf=conf,
            iou=iou,
            imgsz=imgsz,
            verbose=False,
        )

    synchronize_device()

    timings = []
    results = None

    for _ in range(BENCHMARK_RUNS):
        synchronize_device()
        start = time.perf_counter()

        results = model(
            processed,
            classes=[0],
            conf=conf,
            iou=iou,
            imgsz=imgsz,
            verbose=False,
        )

        synchronize_device()

        timings.append(
            (time.perf_counter() - start) * 1000
        )

    inference_ms = float(np.mean(timings))

    # -------------------------
    # POSTPROCESSING
    # -------------------------

    post_start = time.perf_counter()

    boxes = results[0].boxes
    raw_detections = len(boxes)

    valid_headcount = 0
    low_area_rejected = 0
    high_area_rejected = 0
    aspect_rejected = 0

    processed_h, processed_w = processed.shape[:2]
    total_pixels = processed_h * processed_w

    detection_records = []

    for box in boxes:
        x1, y1, x2, y2 = map(
            int,
            box.xyxy[0].cpu().numpy()
        )

        score = float(box.conf[0].cpu().numpy())

        bw = max(0, x2 - x1)
        bh = max(0, y2 - y1)

        if bw <= 0 or bh <= 0:
            aspect_rejected += 1
            continue

        area = bw * bh

        if area < total_pixels * MIN_AREA_RATIO:
            low_area_rejected += 1
            continue

        if area > total_pixels * MAX_AREA_RATIO:
            high_area_rejected += 1
            continue

        aspect = bh / float(bw)

        if aspect < MIN_ASPECT_RATIO:
            aspect_rejected += 1
            continue

        valid_headcount += 1

        detection_records.append({
            "box": (x1, y1, x2, y2),
            "conf": score,
        })

    postprocess_ms = (
        time.perf_counter() - post_start
    ) * 1000

    lf = valid_headcount / MAX_CAPACITY

    metrics = counting_metrics(
        actual_count,
        valid_headcount,
    )

    return {
        "image": str(image_path),
        "image_name": image_path.name,
        "image_width": original_w,
        "image_height": original_h,

        "conf": conf,
        "iou": iou,
        "imgsz": imgsz,
        "preprocess": preprocess_mode,
        "roi": roi_name,

        "brightness": brightness,
        "contrast": contrast,
        "clahe_applied": clahe_applied,

        "raw_detections": raw_detections,
        "valid_headcount": valid_headcount,

        "actual_count": (
            "" if actual_count is None else actual_count
        ),

        "count_error": metrics["count_error"],
        "abs_error": metrics["abs_error"],
        "count_accuracy_c251": metrics["count_accuracy_c251"],
        "count_accuracy_bounded": metrics[
            "count_accuracy_bounded"
        ],

        "lf": lf,

        "low_area_rejected": low_area_rejected,
        "high_area_rejected": high_area_rejected,
        "aspect_rejected": aspect_rejected,

        "preprocess_ms": preprocess_ms,
        "inference_ms": inference_ms,
        "postprocess_ms": postprocess_ms,
        "pipeline_cv_ms": (
            preprocess_ms
            + inference_ms
            + postprocess_ms
        ),

        "device": DEVICE,
        "model": MODEL_PATH,

        "_detections": detection_records,
    }


# ============================================================
# CSV
# ============================================================

CSV_FIELDS = [
    "timestamp",
    "image",
    "image_name",
    "image_width",
    "image_height",
    "conf",
    "iou",
    "imgsz",
    "preprocess",
    "roi",
    "brightness",
    "contrast",
    "clahe_applied",
    "raw_detections",
    "valid_headcount",
    "actual_count",
    "count_error",
    "abs_error",
    "count_accuracy_c251",
    "count_accuracy_bounded",
    "lf",
    "low_area_rejected",
    "high_area_rejected",
    "aspect_rejected",
    "preprocess_ms",
    "inference_ms",
    "postprocess_ms",
    "pipeline_cv_ms",
    "device",
    "model",
]


def write_result(writer, result):
    row = {
        key: result.get(key, "")
        for key in CSV_FIELDS
    }
    row["timestamp"] = timestamp()
    writer.writerow(row)


# ============================================================
# ANNOTATION
# ============================================================

def save_annotation(frame, result, output_path):
    image = frame.copy()

    for detection in result["_detections"]:
        x1, y1, x2, y2 = detection["box"]
        score = detection["conf"]

        cv2.rectangle(
            image,
            (x1, y1),
            (x2, y2),
            (255, 0, 0),
            2,
        )

        cv2.putText(
            image,
            f"person {score:.2f}",
            (x1, max(18, y1 - 5)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (255, 0, 0),
            1,
        )

    actual = result["actual_count"]
    predicted = result["valid_headcount"]

    if actual != "":
        title = f"GT: {actual} | YOLO: {predicted}"
    else:
        title = f"YOLO: {predicted}"

    cv2.putText(
        image,
        title,
        (10, 25),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (0, 255, 0),
        2,
    )

    cv2.putText(
        image,
        (
            f"conf={result['conf']:.2f} "
            f"iou={result['iou']:.2f} "
            f"imgsz={result['imgsz']} "
            f"prep={result['preprocess']}"
        ),
        (10, 50),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.42,
        (0, 255, 0),
        1,
    )

    cv2.imwrite(str(output_path), image)


# ============================================================
# SUMMARY
# ============================================================

def build_summary(rows):
    groups = {}

    for row in rows:
        key = (
            row["conf"],
            row["iou"],
            row["imgsz"],
            row["preprocess"],
            row["roi"],
        )

        groups.setdefault(key, []).append(row)

    summaries = []

    for key, group in groups.items():
        conf, iou, imgsz, prep, roi = key

        errors = [
            float(r["abs_error"])
            for r in group
            if r["abs_error"] != ""
        ]

        bounded = [
            float(r["count_accuracy_bounded"])
            for r in group
            if r["count_accuracy_bounded"] != ""
        ]

        c251 = [
            float(r["count_accuracy_c251"])
            for r in group
            if r["count_accuracy_c251"] != ""
        ]

        latency = [
            float(r["pipeline_cv_ms"])
            for r in group
        ]

        exact = [
            1
            for r in group
            if r["actual_count"] != ""
            and int(r["actual_count"]) == int(r["valid_headcount"])
        ]

        summary = {
            "conf": conf,
            "iou": iou,
            "imgsz": imgsz,
            "preprocess": prep,
            "roi": roi,
            "images": len(group),

            "mean_abs_error": (
                np.mean(errors) if errors else ""
            ),

            "mean_count_accuracy_bounded": (
                np.mean(bounded) if bounded else ""
            ),

            "mean_count_accuracy_c251": (
                np.mean(c251) if c251 else ""
            ),

            "exact_count_rate": (
                np.mean(exact) * 100.0
                if group and errors
                else ""
            ),

            "mean_pipeline_cv_ms": np.mean(latency),

            "mean_inference_ms": np.mean([
                float(r["inference_ms"])
                for r in group
            ]),
        }

        summaries.append(summary)

    # Jika ada ground truth, ranking utama berdasarkan bounded accuracy,
    # lalu absolute error, lalu latency.
    if USE_GROUND_TRUTH:
        summaries.sort(
            key=lambda x: (
                -float(x["mean_count_accuracy_bounded"])
                if x["mean_count_accuracy_bounded"] != ""
                else 999999,
                float(x["mean_abs_error"])
                if x["mean_abs_error"] != ""
                else 999999,
                float(x["mean_pipeline_cv_ms"]),
            )
        )
    else:
        summaries.sort(
            key=lambda x: float(x["mean_pipeline_cv_ms"])
        )

    return summaries


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 70)
    print("AUTOMATED HEADCOUNT EXPERIMENT")
    print("=" * 70)

    print(f"Model       : {MODEL_PATH}")
    print(f"Dataset     : {IMAGE_DIR.resolve()}")
    print(f"Device      : {DEVICE}")
    print(f"Confidence  : {CONF_VALUES}")
    print(f"IoU         : {IOU_VALUES}")
    print(f"Image sizes : {IMGSZ_VALUES}")
    print(f"Preprocess  : {PREPROCESS_MODES}")
    print(f"Groundtruth : {USE_GROUND_TRUTH}")
    print("=" * 70)

    images = find_images()
    ground_truth = load_ground_truth()

    print(f"[INFO] Jumlah gambar: {len(images)}")

    if USE_GROUND_TRUTH:
        missing_gt = [
            p.name for p in images
            if p.name not in ground_truth
        ]

        if missing_gt:
            raise ValueError(
                "Ada gambar yang belum memiliki ground truth:\n"
                + "\n".join(missing_gt[:20])
                + (
                    "\n..."
                    if len(missing_gt) > 20
                    else ""
                )
            )

    model = YOLO(MODEL_PATH)

    configs = list(itertools.product(
        CONF_VALUES,
        IOU_VALUES,
        IMGSZ_VALUES,
        PREPROCESS_MODES,
        ROI_VALUES,
    ))

    print(f"[INFO] Total konfigurasi: {len(configs)}")
    print(
        f"[INFO] Total inference kira-kira: "
        f"{len(images) * len(configs)}"
    )

    if RESULT_CSV.exists():
        RESULT_CSV.unlink()

    all_rows = []

    with open(
        RESULT_CSV,
        "w",
        newline="",
        encoding="utf-8",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=CSV_FIELDS,
        )
        writer.writeheader()

        for image_index, image_path in enumerate(images, start=1):
            print()
            print(
                f"[IMAGE {image_index}/{len(images)}] "
                f"{image_path.name}"
            )

            frame = cv2.imread(str(image_path))

            if frame is None:
                print(
                    f"[WARNING] Gagal membaca: "
                    f"{image_path}"
                )
                continue

            actual = (
                ground_truth.get(image_path.name)
                if USE_GROUND_TRUTH
                else None
            )

            for config_index, (
                conf,
                iou,
                imgsz,
                prep,
                roi_data,
            ) in enumerate(configs, start=1):

                roi_name, roi = roi_data

                result = run_one(
                    model=model,
                    frame=frame,
                    image_path=image_path,
                    conf=conf,
                    iou=iou,
                    imgsz=imgsz,
                    preprocess_mode=prep,
                    roi_name=roi_name,
                    roi=roi,
                    actual_count=actual,
                )

                all_rows.append(result)
                write_result(writer, result)
                f.flush()

                print(
                    f"  [{config_index}/{len(configs)}] "
                    f"conf={conf:.2f} "
                    f"iou={iou:.2f} "
                    f"imgsz={imgsz} "
                    f"prep={prep:<8} "
                    f"GT={actual if actual is not None else '-':>3} "
                    f"YOLO={result['valid_headcount']:>3} "
                    f"err={result['abs_error'] if result['abs_error'] != '' else '-':>3} "
                    f"lat={result['pipeline_cv_ms']:.1f}ms"
                )

    print()
    print("[INFO] Membuat summary...")

    summaries = build_summary(all_rows)

    with open(
        SUMMARY_CSV,
        "w",
        newline="",
        encoding="utf-8",
    ) as f:
        fields = [
            "conf",
            "iou",
            "imgsz",
            "preprocess",
            "roi",
            "images",
            "mean_abs_error",
            "mean_count_accuracy_bounded",
            "mean_count_accuracy_c251",
            "exact_count_rate",
            "mean_pipeline_cv_ms",
            "mean_inference_ms",
        ]

        writer = csv.DictWriter(
            f,
            fieldnames=fields,
        )
        writer.writeheader()

        for summary in summaries:
            writer.writerow(summary)

    top = summaries[:TOP_CONFIGS_TO_SAVE]

    with open(
        TOP_CSV,
        "w",
        newline="",
        encoding="utf-8",
    ) as f:
        fields = list(top[0].keys()) if top else []
        if fields:
            writer = csv.DictWriter(
                f,
                fieldnames=fields,
            )
            writer.writeheader()

            for row in top:
                writer.writerow(row)

    # --------------------------------------------------------
    # Simpan gambar untuk konfigurasi terbaik
    # --------------------------------------------------------

    if SAVE_ANNOTATED_FOR_TOP and top:
        ANNOTATED_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        top_keys = {
            (
                float(x["conf"]),
                float(x["iou"]),
                int(x["imgsz"]),
                x["preprocess"],
                x["roi"],
            )
            for x in top
        }

        # Hanya annotate hasil konfigurasi top.
        for result in all_rows:
            key = (
                float(result["conf"]),
                float(result["iou"]),
                int(result["imgsz"]),
                result["preprocess"],
                result["roi"],
            )

            if key not in top_keys:
                continue

            image_path = Path(result["image"])
            frame = cv2.imread(str(image_path))

            if frame is None:
                continue

            name = (
                f"{image_path.stem}_"
                f"conf{result['conf']:.2f}_"
                f"iou{result['iou']:.2f}_"
                f"imgsz{result['imgsz']}_"
                f"{result['preprocess']}.jpg"
            )

            save_annotation(
                frame,
                result,
                ANNOTATED_DIR / name,
            )

    # --------------------------------------------------------
    # PRINT TOP RESULTS
    # --------------------------------------------------------

    print()
    print("=" * 100)
    print("TOP CONFIGURATIONS")
    print("=" * 100)

    for index, row in enumerate(top, start=1):
        print(
            f"{index}. "
            f"conf={row['conf']:.2f} | "
            f"iou={row['iou']:.2f} | "
            f"imgsz={row['imgsz']} | "
            f"prep={row['preprocess']} | "
            f"MAE={row['mean_abs_error']:.3f} | "
            f"Accuracy={row['mean_count_accuracy_bounded']:.2f}% | "
            f"Exact={row['exact_count_rate']:.2f}% | "
            f"Latency={row['mean_pipeline_cv_ms']:.2f} ms"
        )

    print()
    print("=" * 100)
    print("OUTPUT")
    print("=" * 100)
    print(f"All experiments : {RESULT_CSV}")
    print(f"Summary         : {SUMMARY_CSV}")
    print(f"Top configs     : {TOP_CSV}")
    print(f"Annotations     : {ANNOTATED_DIR}")
    print("=" * 100)


if __name__ == "__main__":
    main()