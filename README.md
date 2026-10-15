# Bus Density Routing

Simulasi & rekomendasi rute TransJakarta dengan kepadatan (load factor) berbasis GTFS + ridership harian. Backend FastAPI + Supabase, frontend Next.js + MapLibre.

## Struktur

- `backend/` — FastAPI, simulasi GTFS, Dijkstra k-shortest paths, bus selector, Monte Carlo.
- `frontend/` — Next.js + MapLibre (peta, panel rute, kontrol simulasi, halaman operator).
- `cv/` — worker deteksi penumpang (YOLO) yang menerima frame ESP32-CAM lewat MQTT dan mengirim headcount ke tabel Supabase `kepadatan_live`, plus skrip eksperimen dan bobot model. Dependensinya sendiri di `cv/requirements.txt`.

Kontrak data antara `cv/` dan `backend/` (tabel `kepadatan_live` dan `kamera_live`) ada di [`backend/sql/`](backend/sql/). Ubah skema dan worker dalam PR yang sama.

File besar (`*.pt`, `*.mp4`, `*.zip`, `cv/experiments/headcount_sweep_results/**`) disimpan dengan [Git LFS](https://git-lfs.com); jalankan `git lfs install` sebelum clone.

## Dokumentasi Utama

| Dokumen | Isi |
|---|---|
| [`backend/README_SIMULATION.md`](backend/README_SIMULATION.md) | Simulasi GTFS, penurunan ridership → crowding, integrasi Dijkstra & bus selector |
| [`backend/README_MONTECARLO.md`](backend/README_MONTECARLO.md) | Eksperimen Monte Carlo load factor & routing sensitivity |

## Jalankan Tes

```bash
cd backend
./venv/Scripts/python.exe -m pytest tests/ -q
```

Smoke test offline konflik parah (tanpa Supabase), masih dari `backend/`:

```bash
./venv/Scripts/python.exe scripts/smoke_severe_conflict.py
```

## Jalankan Worker CV

Butuh Redis di `localhost:6379` dan kredensial Supabase di `cv/worker/.env` (lihat `cv/worker/.env.example`). Detail alur dan konfigurasi di [`cv/README.md`](cv/README.md).

```bash
cd cv
python -m venv .venv
.venv\Scriptsctivate
pip install -r requirements.txt

cd worker
python mqtt_subscriber.py       # terminal 1
python cv_worker.py             # terminal 2
```

## Catatan Routing (per 2026-09-19)

- Candidate generation: edge-blocking + corridor-blocking (blokir seluruh koridor rute utama) untuk menghasilkan alternatif koridor yang benar-benar berbeda.
- Primary ranking: `0.30·time + 0.20·distance + 0.30·transfer + 0.20·density` (min-max normalization antar kandidat).
- Re-ranking: urutkan berdasarkan `(density_norm, primary_score)` setelah pemilihan bus spesifik.
