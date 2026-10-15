# bus-density-cv

Penghitung penumpang bus TransJakarta berbasis computer vision untuk proyek
capstone *bus density routing*. Folder ini bagian dari monorepo yang sama dengan
`backend/` (FastAPI) dan `frontend/` (Next.js), tetapi dependensinya terpisah
(`cv/requirements.txt`: torch, ultralytics, OpenCV) karena berat dan berjalan di
mesin yang berbeda. Sebelumnya folder ini repo tersendiri,
[`kepadatan-bus-cv`](https://github.com/CapstoneB07/kepadatan-bus-cv) (sudah
diarsipkan); riwayat commit-nya ikut dibawa ke sini.

## Alur data

```
ESP32-S3 CAM --(MQTT, JPEG biner)--> HiveMQ --> worker/mqtt_subscriber.py
                                                     |  LPUSH
                                                     v
                                         Redis  cv_task_queue:<bus_id>
                                                     |  BRPOP
                                                     v
                                          worker/cv_worker.py (YOLO)
                                                     |
                                  headcount -> load factor -> label kepadatan
```

- `mqtt_subscriber.py` menerima payload JPEG mentah dari topik MQTT, menyimpan
  salinannya ke `received_images/`, lalu mendorongnya ke antrean Redis.
- `cv_worker.py` mengambil dari antrean, menjalankan YOLO (kelas `person`),
  menyaring deteksi (area dan rasio), lalu menghitung load factor
  `headcount / MAX_CAPACITY` (kapasitas 80) dan label SEPI / SEDANG / PADAT /
  SANGAT PADAT. Latensi tiap tahap dicatat ke `cv_latency_log_binary.csv`.

### Pengiriman ke backend

`worker/live_push.py` meng-upsert `{bus_id, jumlah_penumpang}` ke tabel Supabase
`kepadatan_live` (skema: [`backend/sql/kepadatan_live.sql`](../backend/sql/kepadatan_live.sql)).
Backend memolling baris itu dan memakainya sebagai kepadatan satu bus; bila
pembacaan lebih tua dari TTL backend, bus kembali memakai data simulasi.

- Yang dikirim adalah median `output_headcount` dari 5 frame terakhir
  (`MEDIAN_WINDOW`), paling sering sekali per 3 detik (`PUSH_INTERVAL_SECONDS`).
  Upload berjalan di thread terpisah dan kegagalannya hanya dicatat di log.
- Kredensial dibaca dari `worker/.env` (lihat `worker/.env.example`):
  `SUPABASE_URL` dan `SUPABASE_SERVICE_ROLE_KEY`. Service-role key hanya boleh
  ada di perangkat worker. Tanpa keduanya, upload mati dan worker jalan seperti
  biasa.
- `BUS_ID` di `cv_worker.py` harus sama dengan `LIVE_CV_BUS_ID` di `.env`
  backend (saat ini `Koridor_1_A`).

## Struktur

| Folder | Isi |
| --- | --- |
| `worker/` | `mqtt_subscriber.py`, `cv_worker.py`, bobot `yolo26n.pt`, log latensi |
| `experiments/` | `headcount.py`, `headcount_sweep_test.py` (sweep conf/iou/imgsz), `headcount_video.py`, `dataset_deduplicator.py`, skrip latensi MQTT / INA226, `ground_truth.csv`, `best.pt`, hasil sweep, notebook training |

## Menjalankan

Butuh Python 3.10+, Redis di `localhost:6379`, dan [Git LFS](https://git-lfs.com)
(jalankan `git lfs install` sebelum clone, kalau tidak file `.pt` hanya berisi
teks pointer).

```bash
cd cv
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

cd worker
python mqtt_subscriber.py       # terminal 1
python cv_worker.py             # terminal 2
```

Konfigurasi (broker, topik, `BUS_ID`, `MODEL_PATH`, ambang YOLO) berupa
konstanta di bagian atas tiap file; hanya kredensial Supabase yang lewat `.env`. Path model dan CSV bersifat relatif ke
direktori kerja, jadi jalankan dari dalam `worker/`.

Kedua proses harus memakai nama antrean yang sama: `mqtt_subscriber.py` dan
`cv_worker.py` sama-sama memakai `cv_task_queue:<BUS_ID>` (saat ini
`Koridor_1_A`), jadi bila `BUS_ID` diganti, ubah di kedua file.

Skrip di `experiments/` dijalankan dari dalam folder tersebut. Gambar uji
(`dataset_test/`) tidak ikut di-commit.
