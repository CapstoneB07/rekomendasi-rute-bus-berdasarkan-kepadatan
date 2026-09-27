import csv
import os
import time
from datetime import datetime

import cv2
import numpy as np
import torch
from ultralytics import YOLO


# ============================================================
# KONFIGURASI TEST
# ============================================================

MODEL_PATH = "yolo26n.pt"
BUS_ID = "Koridor_1_A"
IMAGE_PATH = r"20260925_152025_083_frame_000050.jpg"

# Sesuai Bab 4.2 C-251
MAX_CAPACITY = 80

# ------------------------------------------------------------
# YOLO
# ------------------------------------------------------------
YOLO_CLASSES = [0]      # COCO class 0 = person
YOLO_CONF = 0.20
YOLO_IOU = 0.60
YOLO_IMGSZ = 640

# ------------------------------------------------------------
# PREPROCESSING
# ------------------------------------------------------------
# False = baseline: CLAHE selalu diterapkan
# True  = CLAHE hanya diterapkan ketika gambar cukup gelap
#         atau contrast-nya rendah.
ENABLE_ADAPTIVE_CLAHE = True

CLAHE_CLIP_LIMIT = 1.5
CLAHE_TILE_GRID = (8, 8)

BRIGHTNESS_THRESHOLD = 70.0
CONTRAST_THRESHOLD = 35.0

# ------------------------------------------------------------
# ROI
# ------------------------------------------------------------
# Matikan dulu untuk baseline.
ENABLE_ROI = False

# Format: (x1, y1, x2, y2), ternormalisasi 0.0 - 1.0
# Contoh:
# ROI = (0.05, 0.10, 0.95, 0.95)
ROI = (0.0, 0.0, 1.0, 1.0)

# ------------------------------------------------------------
# POST-PROCESSING
# ------------------------------------------------------------
MIN_AREA_RATIO = 0.0005
MAX_AREA_RATIO = 0.70
MIN_ASPECT_RATIO = 0.20

# ------------------------------------------------------------
# BENCHMARK
# ------------------------------------------------------------
# Untuk gambar statis, inference dapat dijalankan beberapa kali
# supaya rata-rata latency lebih representatif.
BENCHMARK_RUNS = 5

# Warm-up tidak dimasukkan ke benchmark.
ENABLE_WARMUP = True
WARMUP_RUNS = 3

# ------------------------------------------------------------
# OUTPUT
# ------------------------------------------------------------
SHOW_RESULT = True
SAVE_RESULT = True
OUTPUT_IMAGE_PATH = "headcount_result.jpg"

SAVE_CSV = True
CSV_LOG_FILE = "headcount_test_log.csv"


# ============================================================
# UTILITY
# ============================================================

def timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def cuda_available():
    return torch.cuda.is_available()


def synchronize_device():
    """
    CUDA bersifat asynchronous.
    Synchronize dibutuhkan agar pengukuran inference tidak berhenti
    sebelum operasi GPU benar-benar selesai.
    """
    if cuda_available():
        torch.cuda.synchronize()


def safe_enhance(image):
    """
    CLAHE pada channel luminance (L) di ruang warna LAB.
    """
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    clahe = cv2.createCLAHE(
        clipLimit=CLAHE_CLIP_LIMIT,
        tileGridSize=CLAHE_TILE_GRID
    )

    cl = clahe.apply(l)
    limg = cv2.merge((cl, a, b))

    return cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)


def get_image_quality(image):
    """
    Menghasilkan brightness dan contrast sederhana.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    brightness = float(np.mean(gray))
    contrast = float(np.std(gray))

    return brightness, contrast


def apply_roi(image):
    """
    Crop ROI berdasarkan koordinat ternormalisasi.
    """
    h, w = image.shape[:2]

    rx1, ry1, rx2, ry2 = ROI

    x1 = max(0, min(w - 1, int(rx1 * w)))
    y1 = max(0, min(h - 1, int(ry1 * h)))
    x2 = max(x1 + 1, min(w, int(rx2 * w)))
    y2 = max(y1 + 1, min(h, int(ry2 * h)))

    return image[y1:y2, x1:x2]


def preprocess(image):
    """
    Pipeline preprocessing.

    Return:
        processed_image
        brightness
        contrast
        clahe_applied
    """
    processed = image

    if ENABLE_ROI:
        processed = apply_roi(processed)

    brightness, contrast = get_image_quality(processed)

    if ENABLE_ADAPTIVE_CLAHE:
        should_enhance = (
            brightness < BRIGHTNESS_THRESHOLD
            or contrast < CONTRAST_THRESHOLD
        )

        if should_enhance:
            processed = safe_enhance(processed)
            clahe_applied = True
        else:
            clahe_applied = False

    else:
        processed = safe_enhance(processed)
        clahe_applied = True

    return processed, brightness, contrast, clahe_applied


def classify_density(lf):
    if lf < 0.50:
        return "SEPI", (0, 255, 0)

    if lf < 0.80:
        return "SEDANG", (0, 255, 255)

    if lf < 1.00:
        return "PADAT", (0, 165, 255)

    return "SANGAT PADAT", (0, 0, 255)


def ensure_csv_header():
    if not SAVE_CSV:
        return

    if os.path.exists(CSV_LOG_FILE) and os.path.getsize(CSV_LOG_FILE) > 0:
        return

    with open(CSV_LOG_FILE, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)

        writer.writerow([
            "timestamp",
            "bus_id",
            "image_path",
            "image_width",
            "image_height",
            "processing_width",
            "processing_height",
            "raw_detections",
            "valid_headcount",
            "lf",
            "status",
            "brightness",
            "contrast",
            "clahe_applied",
            "avg_utf8_ms",
            "avg_preprocess_ms",
            "avg_inference_ms",
            "avg_postprocess_ms",
            "avg_total_ms",
            "min_inference_ms",
            "max_inference_ms",
            "device",
            "model"
        ])


def save_csv(row):
    if not SAVE_CSV:
        return

    with open(CSV_LOG_FILE, "a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(row)


def warmup(model, image):
    if not ENABLE_WARMUP:
        return

    print(
        f"[{timestamp()}] [INFO] "
        f"Warm-up inference: {WARMUP_RUNS}x"
    )

    for _ in range(WARMUP_RUNS):
        _ = model(
            image,
            classes=YOLO_CLASSES,
            conf=YOLO_CONF,
            iou=YOLO_IOU,
            imgsz=YOLO_IMGSZ,
            verbose=False
        )

    synchronize_device()

    print(
        f"[{timestamp()}] [INFO] Warm-up selesai."
    )


def run_inference_benchmark(model, image):
    """
    Menjalankan inference beberapa kali.

    Return:
        representative_results
        timings
    """
    timings = []
    representative_results = None

    for run_index in range(BENCHMARK_RUNS):
        synchronize_device()

        start = time.perf_counter()

        results = model(
            image,
            classes=YOLO_CLASSES,
            conf=YOLO_CONF,
            iou=YOLO_IOU,
            imgsz=YOLO_IMGSZ,
            verbose=False
        )

        synchronize_device()

        elapsed_ms = (time.perf_counter() - start) * 1000

        timings.append(elapsed_ms)

        # Simpan hasil run terakhir sebagai hasil deteksi.
        representative_results = results

        print(
            f"[BENCHMARK] Run {run_index + 1}/{BENCHMARK_RUNS}: "
            f"{elapsed_ms:.2f} ms"
        )

    return representative_results, timings


# ============================================================
# LOAD MODEL & IMAGE
# ============================================================

device_text = "CUDA" if cuda_available() else "CPU"

print(
    f"[{timestamp()}] [INFO] "
    f"Memulai pengujian headcount."
)
print(
    f"[{timestamp()}] [INFO] "
    f"Bus={BUS_ID} | Model={MODEL_PATH} | Device={device_text}"
)
print(
    f"[{timestamp()}] [INFO] "
    f"imgsz={YOLO_IMGSZ} | conf={YOLO_CONF} | iou={YOLO_IOU}"
)
print(
    f"[{timestamp()}] [INFO] "
    f"Adaptive CLAHE={ENABLE_ADAPTIVE_CLAHE} | "
    f"ROI={ENABLE_ROI}"
)

model = YOLO(MODEL_PATH)

# ------------------------------------------------------------
# IMAGE LOAD
# ------------------------------------------------------------
load_start = time.perf_counter()

frame = cv2.imread(IMAGE_PATH)

image_load_ms = (time.perf_counter() - load_start) * 1000

if frame is None:
    print(
        f"[{timestamp()}] [ERROR] "
        f"Gambar tidak ditemukan: {IMAGE_PATH}"
    )
    raise SystemExit(1)

original_height, original_width = frame.shape[:2]

print(
    f"[{timestamp()}] [INFO] "
    f"Image={original_width}x{original_height} | "
    f"Load={image_load_ms:.2f} ms"
)


# ============================================================
# PREPROCESSING
# ============================================================

preprocess_start = time.perf_counter()

processed_frame, brightness, contrast, clahe_applied = preprocess(frame)

preprocess_ms = (time.perf_counter() - preprocess_start) * 1000

processing_height, processing_width = processed_frame.shape[:2]

print(
    f"[{timestamp()}] [IMAGE] "
    f"Brightness={brightness:.2f} | "
    f"Contrast={contrast:.2f} | "
    f"CLAHE={clahe_applied}"
)

print(
    f"[{timestamp()}] [IMAGE] "
    f"Input={original_width}x{original_height} | "
    f"Processing={processing_width}x{processing_height} | "
    f"Preprocess={preprocess_ms:.2f} ms"
)


# ============================================================
# WARM-UP
# ============================================================

warmup(model, processed_frame)


# ============================================================
# INFERENCE BENCHMARK
# ============================================================

results, inference_timings = run_inference_benchmark(
    model,
    processed_frame
)

avg_inference_ms = float(np.mean(inference_timings))
min_inference_ms = float(np.min(inference_timings))
max_inference_ms = float(np.max(inference_timings))


# ============================================================
# POST-PROCESSING
# ============================================================

postprocess_start = time.perf_counter()

valid_headcount = 0
low_area_rejected = 0
high_area_rejected = 0
aspect_rejected = 0

annotated_frame = frame.copy()

total_pixels = (
    processing_height
    * processing_width
)

boxes = results[0].boxes
raw_detections = len(boxes)

for box in boxes:

    x1, y1, x2, y2 = map(
        int,
        box.xyxy[0].cpu().numpy()
    )

    conf_score = float(
        box.conf[0].cpu().numpy()
    )

    box_width = max(0, x2 - x1)
    box_height = max(0, y2 - y1)

    if box_width <= 0 or box_height <= 0:
        aspect_rejected += 1
        continue

    box_area = box_width * box_height

    # --------------------------------------------------------
    # AREA FILTER
    # --------------------------------------------------------
    if box_area < (total_pixels * MIN_AREA_RATIO):
        low_area_rejected += 1
        continue

    if box_area > (total_pixels * MAX_AREA_RATIO):
        high_area_rejected += 1
        continue

    # --------------------------------------------------------
    # ASPECT RATIO FILTER
    # --------------------------------------------------------
    aspect_ratio = box_height / float(box_width)

    if aspect_ratio < MIN_ASPECT_RATIO:
        aspect_rejected += 1
        continue

    valid_headcount += 1

    # --------------------------------------------------------
    # VISUALIZATION
    # --------------------------------------------------------
    # Warna biru OpenCV = BGR (255, 0, 0)
    box_color = (255, 0, 0)

    cv2.rectangle(
        annotated_frame,
        (x1, y1),
        (x2, y2),
        box_color,
        2
    )

    cv2.putText(
        annotated_frame,
        f"person {conf_score:.2f}",
        (x1, max(20, y1 - 5)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        box_color,
        2
    )

postprocess_ms = (
    time.perf_counter() - postprocess_start
) * 1000


# ============================================================
# LOAD FACTOR
# ============================================================

lf = valid_headcount / MAX_CAPACITY

status_text, status_color = classify_density(lf)

# Total processing di sini tidak memasukkan image file load
# agar lebih cocok digunakan sebagai ukuran pipeline CV.
avg_total_ms = (
    preprocess_ms
    + avg_inference_ms
    + postprocess_ms
)


# ============================================================
# OVERLAY HASIL
# ============================================================

cv2.putText(
    annotated_frame,
    f"Total: {valid_headcount}/{MAX_CAPACITY} "
    f"(LF: {lf:.2f})",
    (20, 40),
    cv2.FONT_HERSHEY_SIMPLEX,
    0.8,
    status_color,
    2
)

cv2.putText(
    annotated_frame,
    f"Status: {status_text}",
    (20, 80),
    cv2.FONT_HERSHEY_SIMPLEX,
    0.8,
    status_color,
    2
)

cv2.putText(
    annotated_frame,
    f"Avg Inference: {avg_inference_ms:.1f} ms",
    (20, 120),
    cv2.FONT_HERSHEY_SIMPLEX,
    0.6,
    status_color,
    2
)

cv2.putText(
    annotated_frame,
    f"Pipeline CV: {avg_total_ms:.1f} ms",
    (20, 150),
    cv2.FONT_HERSHEY_SIMPLEX,
    0.6,
    status_color,
    2
)


# ============================================================
# OUTPUT
# ============================================================

if SAVE_RESULT:
    cv2.imwrite(
        OUTPUT_IMAGE_PATH,
        annotated_frame
    )

    print(
        f"[{timestamp()}] [INFO] "
        f"Hasil disimpan ke: {OUTPUT_IMAGE_PATH}"
    )

print("\n" + "=" * 60)
print("HASIL PENGUJIAN HEADCOUNT")
print("=" * 60)

print(f"Image                  : {IMAGE_PATH}")
print(f"Resolution             : {original_width}x{original_height}")
print(f"Model                  : {MODEL_PATH}")
print(f"Device                 : {device_text}")
print(f"Raw detections         : {raw_detections}")
print(f"Valid headcount        : {valid_headcount}")
print(f"Max capacity           : {MAX_CAPACITY}")
print(f"Load Factor            : {lf:.2f} ({lf * 100:.1f}%)")
print(f"Status                 : {status_text}")

print("-" * 60)
print("FILTER")
print(f"Rejected low area      : {low_area_rejected}")
print(f"Rejected high area     : {high_area_rejected}")
print(f"Rejected aspect ratio  : {aspect_rejected}")

print("-" * 60)
print("LATENCY")
print(f"Image load             : {image_load_ms:.2f} ms")
print(f"Preprocessing          : {preprocess_ms:.2f} ms")
print(f"Inference avg          : {avg_inference_ms:.2f} ms")
print(f"Inference min          : {min_inference_ms:.2f} ms")
print(f"Inference max          : {max_inference_ms:.2f} ms")
print(f"Post-processing        : {postprocess_ms:.2f} ms")
print(f"Pipeline CV avg        : {avg_total_ms:.2f} ms")
print("=" * 60)


# ============================================================
# CSV
# ============================================================

ensure_csv_header()

save_csv([
    timestamp(),
    BUS_ID,
    IMAGE_PATH,
    original_width,
    original_height,
    processing_width,
    processing_height,
    raw_detections,
    valid_headcount,
    round(lf, 4),
    status_text,
    round(brightness, 4),
    round(contrast, 4),
    clahe_applied,
    "",
    round(preprocess_ms, 4),
    round(avg_inference_ms, 4),
    round(postprocess_ms, 4),
    round(avg_total_ms, 4),
    round(min_inference_ms, 4),
    round(max_inference_ms, 4),
    device_text,
    MODEL_PATH
])


# ============================================================
# DISPLAY
# ============================================================

if SHOW_RESULT:
    window_name = "Hasil Deteksi Headcount"

    cv2.imshow(window_name, annotated_frame)

    print(
        f"[{timestamp()}] [INFO] "
        f"Tekan tombol apa saja pada window untuk menutup."
    )

    cv2.waitKey(0)
    cv2.destroyAllWindows()
