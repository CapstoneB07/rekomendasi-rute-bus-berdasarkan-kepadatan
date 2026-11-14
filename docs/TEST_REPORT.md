# Test Report (2026-11-05)

Pembaruan dari laporan 2026-10-13. Kode: `main` pada commit `6587235`.
Lingkungan: Windows 11, backend lokal dengan data nyata Supabase, MQTT dimatikan.
Mesin uji sedang dibebani worker CV (YOLO) dan Docker (CPU ±95%), jadi angka latensi di bawah
konservatif dan bergerak antar-run.

## Ringkasan
| Suite | Hasil |
|---|---|
| Backend (`pytest`, tanpa gate latensi) | 159 lulus |
| Test API rekomendasi (data nyata Supabase) | 12 lulus (semua lulus, termasuk TC-API-06) |
| Gate latensi offline (`test_latensi_rute.py`) | lulus pada ambang CI 200 ms; lokal 100 ms lulus/gagal bergantian saat CPU penuh (p95 ±124 ms pada run yang gagal) |
| Frontend vitest | 111 lulus (18 file) |
| `tsc --noEmit` | bersih |
| `eslint` | tanpa isu |

## Objective 2: latensi (MEMBAIK, belum stabil di bawah target di mesin berbeban)
Pengukuran `POST /api/rute/rekomendasi` terhadap data nyata, n=40 (8 pasangan halte x 5 ulang), `jam=9`:

| | 2026-10-13 | 2026-11-05 (run bersih) | 2026-11-05 (CPU penuh) |
|---|---|---|---|
| p50 | 1908 ms | ±103-108 ms | 126-339 ms |
| p95 | 5622 ms | ±131-167 ms | 534-754 ms |

Perbaikan datang dari percepatan Dijkstra (#10) dan cache snapshot Monte Carlo bersama (#11).
Pada mesin tidak berbeban p50 sudah mendekati target 100 ms; p95 masih di atasnya.
Gate regresi yang dijalankan CI adalah `test_latensi_rute.py` (graf sintetis, tanpa Supabase),
bukan pengukuran data nyata ini, karena yang kedua bergantung pada jaringan dan beban mesin.

## Objective 1 (ADA)
- Halaman `/operator`: peta rute dan bus, panel kamera dengan bounding box, kontrol waktu simulasi bersama lewat backend.
- Pipeline kamera: ESP32-CAM -> MQTT -> Redis -> `cv/worker/cv_worker.py` (YOLO) -> `live_push.py` mengunggah frame dan bbox ke Supabase (`kamera_live`, bucket `kamera-frames`) -> `GET /api/live/camera`.
- Terverifikasi 2026-11-05: setelah worker dinyalakan, baris `kamera_live` ter-update tiap ±0,3 detik. Sebelum itu panel menampilkan BASI (410) karena worker mati ±25 jam.
- Belum ada tes otomatis end-to-end untuk rantai ini; worker CV dikecualikan dari CI.

## Objective 3 (ADA, belum diuji pada printer fisik di laporan ini)
- Cetak tiket rencana perjalanan dan foto kamera ke printer thermal (`/api/print/*`, port COM Bluetooth; sambungan dipertahankan antar-cetakan dan disambung ulang otomatis bila putus).
- Logika dicakup tes unit (`test_cetak.py`, termasuk sambung ulang). Pencetakan ke printer Bluetooth asli belum diuji.

## Area of improvement
- `sim_time` > 1 hari sekarang ditolak (422); TC-API-06 lulus.
- Tes komponen FE masih terbatas pada logika `lib/` dan beberapa komponen.
- Posisi bus live bergantung pada tab browser yang menjangkau broker TJ (`mqtt.tj.co.id:8084`); pada 2026-11-05 broker tidak terjangkau dari jaringan uji (timeout di semua port yang dicoba).
- Worker CV hanya berjalan di laptop operator (butuh Redis lokal); belum ada pemantauan bila mati selain panel BASI.
