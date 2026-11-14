import torch
from ultralytics import YOLO
import time
from pathlib import Path

print("PyTorch:", torch.__version__)
print("CUDA tersedia:", torch.cuda.is_available())

BASE_DIR = Path(__file__).resolve().parent.parent

model_path = BASE_DIR / "models" / "weights.pt"

image_path = (
    BASE_DIR
    / "datasets"
    / "dataset_full"
    / "test"
    / "images"
    / "20260925_151159_768_frame_000025_jpg.rf.ba08a87b8008059c2cfbe81b1076a510.jpg"
)

print("Model ditemukan:", model_path.is_file())
print("Gambar ditemukan:", image_path.is_file())

model = YOLO(str(model_path))
results = model.predict(source=str(image_path), imgsz=640)

# Warm-up
for _ in range(5):
    model.predict(str(image_path), imgsz=640, device="cpu", verbose=False)

# Benchmark CPU
times = []

for _ in range(30):
    start = time.perf_counter()
    model.predict(str(image_path), imgsz=640, device="cpu", verbose=False)
    times.append((time.perf_counter() - start) * 1000)

print(f"Rata-rata CPU: {sum(times)/len(times):.2f} ms")
print(f"FPS: {1000/(sum(times)/len(times)):.2f}")