# Bus Density Routing

Simulasi & rekomendasi rute TransJakarta dengan kepadatan (load factor) berbasis GTFS + ridership harian. Backend FastAPI + Supabase, frontend Next.js + MapLibre.

## Struktur

- `backend/` — FastAPI, simulasi GTFS, Dijkstra k-shortest paths, bus selector, Monte Carlo.
- `frontend/` — Next.js + MapLibre (peta, panel rute, kontrol simulasi).
- `script/` — skrip pelatihan/pendeteksian penumpang (YOLO).

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

Smoke test offline konflik parah (tanpa Supabase):

```bash
./venv/Scripts/python.exe scripts/smoke_severe_conflict.py
```

## Catatan Routing (per 2026-09-19)

- Candidate generation: edge-blocking + corridor-blocking (blokir seluruh koridor rute utama) untuk menghasilkan alternatif koridor yang benar-benar berbeda.
- Primary ranking: `0.30·time + 0.20·distance + 0.30·transfer + 0.20·density` (min-max normalization antar kandidat).
- Re-ranking: urutkan berdasarkan `(density_norm, primary_score)` setelah pemilihan bus spesifik.
