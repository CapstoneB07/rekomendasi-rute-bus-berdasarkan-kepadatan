import csv
import os
import time
from collections import deque
from datetime import datetime
from statistics import median

import cv2
import numpy as np
import redis
import torch
from ultralytics import YOLO

# ============================================================
# CONFIGURATION
# ============================================================
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0

# Worker ini memproses satu queue bus.
BUS_ID = "Koridor_1_A"
REDIS_QUEUE_NAME = f"cv_task_queue:{BUS_ID}"

MODEL_PATH = "yolo26n.pt"
MAX_CAPACITY = 80

YOLO_CLASSES = [0]
YOLO_CONF = 0.20
YOLO_IOU = 0.60
YOLO_IMGSZ = 640

# Preprocessing
ENABLE_ADAPTIVE_CLAHE = False
CLAHE_CLIP_LIMIT = 1.5
CLAHE_TILE_GRID = (8, 8)
BRIGHTNESS_THRESHOLD = 70.0
CONTRAST_THRESHOLD = 35.0

# ROI
ENABLE_ROI = False
ROI = (0.0, 0.0, 1.0, 1.0)

# Temporal filter
ENABLE_TEMPORAL_FILTER = False
TEMPORAL_WINDOW = 3

# Warm-up
ENABLE_WARMUP = True
WARMUP_RUNS = 3

# Logging
ENABLE_CSV_LOG = True
CSV_LOG_FILE = "cv_latency_log_binary.csv"
SUMMARY_EVERY = 10

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB
)
model = YOLO(MODEL_PATH)

temporal_history = {}
recent_total_ms = deque(maxlen=SUMMARY_EVERY)
recent_inference_ms = deque(maxlen=SUMMARY_EVERY)
processed_frames = 0


def get_current_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def is_cuda_available():
    return torch.cuda.is_available()


def synchronize_device():
    if is_cuda_available():
        torch.cuda.synchronize()


def safe_enhance(image):
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
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float(np.mean(gray)), float(np.std(gray))


def apply_roi(image):
    h, w = image.shape[:2]
    rx1, ry1, rx2, ry2 = ROI
    x1 = max(0, min(w - 1, int(rx1 * w)))
    y1 = max(0, min(h - 1, int(ry1 * h)))
    x2 = max(x1 + 1, min(w, int(rx2 * w)))
    y2 = max(y1 + 1, min(h, int(ry2 * h)))
    return image[y1:y2, x1:x2]


def preprocess_frame(frame):
    current_frame = apply_roi(frame) if ENABLE_ROI else frame
    brightness = None
    contrast = None
    clahe_applied = False

    if ENABLE_ADAPTIVE_CLAHE:
        brightness, contrast = get_image_quality(current_frame)
        if (
            brightness < BRIGHTNESS_THRESHOLD
            or contrast < CONTRAST_THRESHOLD
        ):
            current_frame = safe_enhance(current_frame)
            clahe_applied = True
    else:
        current_frame = safe_enhance(current_frame)
        clahe_applied = True

    return current_frame, brightness, contrast, clahe_applied


def classify_density(lf):
    if lf < 0.50:
        return "SEPI"
    if lf < 0.80:
        return "SEDANG"
    if lf < 1.00:
        return "PADAT"
    return "SANGAT PADAT"


def update_temporal_count(bus_id, raw_count):
    if not ENABLE_TEMPORAL_FILTER:
        return raw_count

    if bus_id not in temporal_history:
        temporal_history[bus_id] = deque(maxlen=TEMPORAL_WINDOW)

    history = temporal_history[bus_id]
    history.append(raw_count)
    return int(round(median(history)))


def ensure_csv_header():
    if not ENABLE_CSV_LOG:
        return
    if os.path.exists(CSV_LOG_FILE) and os.path.getsize(CSV_LOG_FILE) > 0:
        return

    with open(CSV_LOG_FILE, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([
            "timestamp_received",
            "timestamp_finished",
            "bus_id",
            "image_bytes_kb",
            "raw_detections",
            "valid_headcount",
            "output_headcount",
            "lf",
            "status",
            "brightness",
            "contrast",
            "clahe_applied",
            "jpeg_decode_ms",
            "preprocess_ms",
            "inference_ms",
            "postprocess_ms",
            "total_processing_ms",
            "device"
        ])


def log_to_csv(row):
    if not ENABLE_CSV_LOG:
        return
    with open(CSV_LOG_FILE, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(row)


def warmup_model():
    if not ENABLE_WARMUP:
        return

    print(
        f"[{get_current_timestamp()}] [INFO] "
        f"Warm-up inference {WARMUP_RUNS}x..."
    )

    dummy = np.zeros(
        (YOLO_IMGSZ, YOLO_IMGSZ, 3),
        dtype=np.uint8
    )

    for _ in range(WARMUP_RUNS):
        _ = model(
            dummy,
            classes=YOLO_CLASSES,
            conf=YOLO_CONF,
            iou=YOLO_IOU,
            imgsz=YOLO_IMGSZ,
            verbose=False
        )

    synchronize_device()
    print(f"[{get_current_timestamp()}] [INFO] Warm-up selesai.")


ensure_csv_header()
warmup_model()

device_text = "CUDA" if is_cuda_available() else "CPU"

print(f"[{get_current_timestamp()}] [INFO] CV Worker Service berjalan.")
print(
    f"[{get_current_timestamp()}] [INFO] "
    f"BUS={BUS_ID} | QUEUE={REDIS_QUEUE_NAME}"
)
print(
    f"[{get_current_timestamp()}] [INFO] "
    f"Device={device_text} | Model={MODEL_PATH} | "
    f"imgsz={YOLO_IMGSZ} | conf={YOLO_CONF} | iou={YOLO_IOU}"
)
print(
    f"[{get_current_timestamp()}] [INFO] "
    f"Adaptive CLAHE={ENABLE_ADAPTIVE_CLAHE} | "
    f"ROI={ENABLE_ROI} | Temporal={ENABLE_TEMPORAL_FILTER}"
)
print(
    f"[{get_current_timestamp()}] [INFO] "
    f"Menunggu RAW JPEG binary dari Redis..."
)


try:
    while True:
        try:
            queue_item = redis_client.brpop(
                REDIS_QUEUE_NAME,
                timeout=1
            )

            if not queue_item:
                continue

            total_start = time.perf_counter()
            ts_received = get_current_timestamp()

            # ==================================================
            # RAW BINARY PAYLOAD
            # ==================================================
            # Tidak ada decode UTF-8, JSON parsing, atau Base64.
            image_bytes = queue_item[1]

            if not image_bytes:
                print(
                    f"[{get_current_timestamp()}] "
                    f"[WARNING] Payload JPEG kosong."
                )
                continue

            image_size_kb = len(image_bytes) / 1024.0

            # ==================================================
            # 1. JPEG DECODE
            # ==================================================
            t0 = time.perf_counter()

            np_arr = np.frombuffer(
                image_bytes,
                dtype=np.uint8
            )

            frame = cv2.imdecode(
                np_arr,
                cv2.IMREAD_COLOR
            )

            jpeg_decode_ms = (time.perf_counter() - t0) * 1000

            if frame is None:
                print(
                    f"[{get_current_timestamp()}] "
                    f"[WARNING] Gagal decode JPEG binary "
                    f"({image_size_kb:.2f} KB)."
                )
                continue

            original_height, original_width = frame.shape[:2]

            # ==================================================
            # 2. PREPROCESSING
            # ==================================================
            t0 = time.perf_counter()
            (
                enhanced_frame,
                brightness,
                contrast,
                clahe_applied
            ) = preprocess_frame(frame)
            preprocess_ms = (time.perf_counter() - t0) * 1000

            # ==================================================
            # 3. YOLO26n INFERENCE
            # ==================================================
            synchronize_device()
            t0 = time.perf_counter()

            results = model(
                enhanced_frame,
                classes=YOLO_CLASSES,
                conf=YOLO_CONF,
                iou=YOLO_IOU,
                imgsz=YOLO_IMGSZ,
                verbose=False
            )

            synchronize_device()
            inference_ms = (time.perf_counter() - t0) * 1000

            # ==================================================
            # 4. POST-PROCESSING
            # ==================================================
            t0 = time.perf_counter()

            valid_headcount = 0
            low_area_rejected = 0
            high_area_rejected = 0
            aspect_rejected = 0

            processing_height, processing_width = enhanced_frame.shape[:2]
            total_pixels = processing_height * processing_width
            raw_detections = len(results[0].boxes)

            for box in results[0].boxes:
                x1, y1, x2, y2 = map(
                    int,
                    box.xyxy[0].cpu().numpy()
                )

                box_width = max(0, x2 - x1)
                box_height = max(0, y2 - y1)

                if box_width <= 0 or box_height <= 0:
                    aspect_rejected += 1
                    continue

                box_area = box_width * box_height

                if box_area < total_pixels * 0.0005:
                    low_area_rejected += 1
                    continue

                if box_area > total_pixels * 0.7:
                    high_area_rejected += 1
                    continue

                aspect_ratio = box_height / float(box_width)

                if aspect_ratio < 0.2:
                    aspect_rejected += 1
                    continue

                valid_headcount += 1

            postprocess_ms = (time.perf_counter() - t0) * 1000

            # ==================================================
            # 5. TEMPORAL STABILIZATION
            # ==================================================
            output_headcount = update_temporal_count(
                BUS_ID,
                valid_headcount
            )

            # ==================================================
            # 6. LOAD FACTOR
            # ==================================================
            lf = output_headcount / MAX_CAPACITY
            status_text = classify_density(lf)

            # ==================================================
            # 7. TIMING
            # ==================================================
            total_processing_ms = (
                time.perf_counter() - total_start
            ) * 1000

            ts_finished = get_current_timestamp()
            recent_total_ms.append(total_processing_ms)
            recent_inference_ms.append(inference_ms)
            processed_frames += 1

            db_payload = {
                "bus_id": BUS_ID,
                "jumlah_penumpang": output_headcount,
                "kepadatan": round(lf, 2)
            }

            print(
                f"\n[{ts_received}] [CV WORKER] "
                f"Memproses JPEG binary | "
                f"size={image_size_kb:.2f} KB"
            )

            print(
                f"[{ts_finished}] [IMAGE] "
                f"input={original_width}x{original_height} | "
                f"CLAHE={clahe_applied}"
            )

            if brightness is not None:
                print(
                    f"[{ts_finished}] [QUALITY] "
                    f"brightness={brightness:.2f} | "
                    f"contrast={contrast:.2f}"
                )

            print(
                f"[{ts_finished}] [DETECTION] "
                f"raw={raw_detections} | "
                f"valid={valid_headcount} | "
                f"output={output_headcount}"
            )

            print(
                f"[{ts_finished}] [FILTER] "
                f"low_area={low_area_rejected} | "
                f"high_area={high_area_rejected} | "
                f"aspect={aspect_rejected}"
            )

            print(
                f"[{ts_finished}] [HEADCOUNT] "
                f"{output_headcount}/{MAX_CAPACITY} | "
                f"LF={lf:.2f} | Status={status_text}"
            )

            print(
                f"[{ts_finished}] [TIMING] "
                f"JPEG={jpeg_decode_ms:.2f} ms | "
                f"Preprocess={preprocess_ms:.2f} ms | "
                f"Inference={inference_ms:.2f} ms | "
                f"Postprocess={postprocess_ms:.2f} ms | "
                f"TOTAL={total_processing_ms:.2f} ms"
            )

            print(
                f"[{ts_finished}] [SIMULASI DB] "
                f"{db_payload}"
            )

            log_to_csv([
                ts_received,
                ts_finished,
                BUS_ID,
                round(image_size_kb, 4),
                raw_detections,
                valid_headcount,
                output_headcount,
                round(lf, 4),
                status_text,
                None if brightness is None else round(brightness, 4),
                None if contrast is None else round(contrast, 4),
                clahe_applied,
                round(jpeg_decode_ms, 4),
                round(preprocess_ms, 4),
                round(inference_ms, 4),
                round(postprocess_ms, 4),
                round(total_processing_ms, 4),
                device_text
            ])

            if processed_frames % SUMMARY_EVERY == 0:
                avg_total = sum(recent_total_ms) / len(recent_total_ms)
                avg_inference = sum(recent_inference_ms) / len(recent_inference_ms)
                print(
                    f"[{get_current_timestamp()}] [SUMMARY] "
                    f"Frame={processed_frames} | "
                    f"Avg TOTAL={avg_total:.2f} ms | "
                    f"Avg Inference={avg_inference:.2f} ms"
                )

        except Exception as e:
            print(
                f"[{get_current_timestamp()}] "
                f"[CV WORKER ERROR] {e}"
            )

except KeyboardInterrupt:
    print(
        f"\n[{get_current_timestamp()}] "
        f"[INFO] Mematikan CV Worker Service"
    )
