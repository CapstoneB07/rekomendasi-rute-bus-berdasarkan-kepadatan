# Test Report (2026-10-13)

Lingkungan: Windows 11, backend lokal dengan data nyata Supabase (289 halte, 308 segmen, 2149 trip instance simulasi), MQTT dimatikan.

## Ringkasan
| Suite | Hasil |
|---|---|
| Backend test lama | 76 lulus |
| Frontend vitest | 31 lulus |
| `tsc --noEmit` | bersih |
| `eslint` | 1 warning (`supabase` tak terpakai di `utils/supabase/middleware.ts:14`) |
| Test API baru | 11 lulus, 3 gagal (API-06, PERF-01, PERF-02) |

## Objective 2: latensi (GAGAL)
n=40 request, 8 pasangan halte acak (seed 42), `jam=9`:
- p50 = **1908 ms**, p95 = **5622 ms** (target < 100 ms, selisih ~19x sampai ~56x).
- Per pasangan (sekali panggil, in-process): 648 ms sampai 2876 ms.

Profil 3 request (9,16 s total, 3,05 s per request):
| Tahap | Waktu | Porsi |
|---|---|---|
| `dijkstra` + alias halte (`_metrics_if_valid_path` 310k panggilan, 3,96 s tottime) | 6,50 s | 71% |
| `build_recommendation_crowding_snapshot` (Monte Carlo Poisson per request, 117k draw) | 2,41 s | 26% |
| `build_graph` | 0,21 s | 2% |
| `select_bus_per_segmen` | 0,04 s | <1% |

## Objective 1 (BELUM ADA)
- Hanya ada FE kiosk. Tidak ada halaman operator/simulasi.
- Tidak ada endpoint/penyimpanan frame kamera maupun bounding box; backend hanya membaca `jumlah_penumpang` dari `kepadatan_live`.
- Pipeline kamera ada di repo terpisah `bus-density-cv` (ESP32-CAM -> MQTT -> Redis -> `worker/cv_worker.py`, YOLO). Worker sudah menyimpan JPEG ke `received_images/` dan punya bbox (`box.xyxy`, cv_worker.py:349), tetapi `live_push.py` hanya meng-upsert `{bus_id, jumlah_penumpang}`; frame dan bbox tidak sampai ke Supabase/backend.

## Objective 3 (BELUM ADA)
- Tidak ada fitur cetak/tiket (tak ada `window.print`, CSS print, atau komponen tiket).

## Area of improvement lain
- `sim_time` tidak dibatasi atas (1e9 diterima, TC-API-06).
- `print` debug di jalur request `rekomendasi` dan audit `gtfs_spatial_audit` bervolume besar saat startup.
- Endpoint `rekomendasi` sinkron (`def`), berjalan di threadpool; tidak ada cache.
- Tidak ada test komponen FE; hanya logika `lib/`.
- CI hanya deploy backend, tidak menjalankan test.
- README transjakarta-app menyebut `script/` yang tidak ada (modul ada di repo `bus-density-cv`).
- `next.err`/`next.out` ter-track di git dan berubah tiap run.
