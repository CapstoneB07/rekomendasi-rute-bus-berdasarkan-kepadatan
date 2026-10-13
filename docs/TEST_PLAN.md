# Test Plan

Objective:
1. Dua FE: kiosk end-user, dan FE operator (simulasi bus, kontrol waktu/lokasi, gambar kamera + bounding box).
2. Respon pencarian rute < 100 ms.
3. Rute terpilih dapat dicetak sebagai tiket.

| ID | Objective | Area | Langkah | Hasil diharapkan | Otomasi |
|---|---|---|---|---|---|
| TC-API-01 | - | API | POST rekomendasi, halte asal tak dikenal | 404 | backend/tests/test_api_rekomendasi.py |
| TC-API-02 | - | API | asal == tujuan | 400 | idem |
| TC-API-03 | - | API | jam -1 / 24 | 422 | idem |
| TC-API-04 | - | API | hari_tipe tidak valid | 422 | idem |
| TC-API-05 | - | API | field wajib kurang | 422 | idem |
| TC-API-06 | - | API | sim_time 1e9 (> 1 hari) | 422 | idem |
| TC-API-07 | - | API | struktur respons rute valid | 200, list of dict | idem |
| TC-API-08 | - | API | request identik 2x | respons identik (deterministik) | idem |
| TC-API-09 | - | API | mode live | 200/404, tanpa error | idem |
| TC-API-10 | - | API | GET simulation/halte, shapes, positions, live/positions | 200 | idem |
| TC-PERF-01 | 2 | Performa | 8 pasangan halte x 5 ulang | p50 < 100 ms | idem |
| TC-PERF-02 | 2 | Performa | idem | p95 < 100 ms | idem |
| TC-PERF-03 | 2 | Performa | profil cProfile per tahap | informasi bottleneck | script profil |
| TC-FE-01 | - | FE | `npx vitest run`, `tsc --noEmit`, `eslint` | lulus, tanpa warning | CI/manual |
| TC-OBJ1-01 | 1 | FE operator | buka halaman operator | ada peta + bus simulasi | manual (belum ada) |
| TC-OBJ1-02 | 1 | FE operator | ubah waktu & lokasi simulasi | posisi bus berubah | manual (belum ada) |
| TC-OBJ1-03 | 1 | FE operator | tampil frame kamera + bbox deteksi | gambar + kotak deteksi tampil | manual (belum ada) |
| TC-OBJ3-01 | 3 | Tiket | pilih rute lalu tekan cetak | tiket tercetak (rute, halte, jam, harga) | manual (belum ada) |

Menjalankan: `cd backend && ./venv/Scripts/python.exe -m pytest tests -q` (test API memakai backend/.env dan dilewati tanpa kredensial);
`cd frontend && npx vitest run && npx tsc --noEmit && npx eslint`.
