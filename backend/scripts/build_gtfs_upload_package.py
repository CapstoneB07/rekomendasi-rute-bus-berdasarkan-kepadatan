"""Bangun paket CSV upload-ready Supabase dari Transitland GTFS feed + ridership.

Sumber:
  - Data References/Real Reference/transitland feed/f-transjakarta~id-latest/
    (routes/trips/frequencies/stop_times/stops/shapes/calendar .txt)
  - Data References/Real Reference/BRT Pengambilan Koridor Dimodelkan.xlsx
    (ridership harian BRT per koridor, semua koridor 1-14)
  - Data References/Real Reference/Pelanggan Transjakarta Per Jenis Layanan *.xlsx
    (verifikasi silang total bulanan)

Menghasilkan (default: Data References/Made CSVs/supabase_gtfs_<scope>_upload_ready/):
    koridor.csv, halte.csv, koridor_halte.csv, segmen.csv, shapes.csv,
    gtfs_trips.csv, gtfs_frequencies.csv, gtfs_stop_times.csv,
    ridership_harian_turunan.csv, README_IMPORT_ORDER.txt, summary_counts.csv

Aturan seleksi trip (direkonstruksi dari paket 1-5 yang sudah terbukti):
  - hanya route_id yang diminta (mis. "1".."5","8","9","12"),
  - hanya pola mainline "-R##" (nama rute polos),
  - buang pola loop "-P##"/"-L##" dan varian "via ...",
  - satu trip per direction_id (pilih trip yang trip_short_name-nya paling
    pendek / paling cocok dengan route_long_name).

Jalankan dari backend/:
    ./venv/Scripts/python.exe scripts/build_gtfs_upload_package.py \
        --koridor 1,2,3,4,5,8,9,12 --out "<dir>"
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CAPACITY_BUS = 80
CREATED_AT = "2026-05-23 07:58:29.910087+00"
SEGMEN_CREATED_AT = "2026-05-23 08:01:30.668452+00"
HALTE_CREATED_AT = "2026-05-23 08:00:19.947238+00"

DEFAULT_FEED = (
    "D:/Projects/Kuliah/Sem67/capstone/Data References/Real Reference/"
    "transitland feed/f-transjakarta~id-latest"
)
DEFAULT_RIDERSHIP_XLSX = (
    "D:/Projects/Kuliah/Sem67/capstone/Data References/Real Reference/"
    "BRT Pengambilan Koridor Dimodelkan.xlsx"
)


# --------------------------------------------------------------------------
# GTFS parsing
# --------------------------------------------------------------------------
def read_gtfs(path: Path, name: str) -> list[dict]:
    with (path / f"{name}.txt").open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def hhmmss_to_seconds(value: str) -> int:
    h, m, s = (int(x) for x in value.split(":"))
    return h * 3600 + m * 60 + s


def seconds_to_hhmmss(total: int) -> str:
    total = int(total) % 86400
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def select_trips(trips: list[dict], routes: dict[str, dict], koridor: set[str],
                 overrides: dict[str, list[str]] | None = None) -> dict[str, list[dict]]:
    """Pilih pola mainline per koridor, satu trip per direction_id.

    Prioritas: nama polos ("-R##" tanpa "via") > "-R## via ..." > lainnya.
    `overrides` (koridor -> daftar trip_id) menimpa heuristik; pakai ini untuk
    mereproduksi paket C251 yang trip-nya dikurasi manual.
    """
    by_kor: dict[str, list[dict]] = defaultdict(list)
    for t in trips:
        rid = str(t["route_id"])
        if rid in koridor:
            by_kor[rid].append(t)

    overrides = overrides or {}
    chosen: dict[str, list[dict]] = {}
    for rid, cand in by_kor.items():
        if rid in overrides:
            want = overrides[rid]
            chosen[rid] = [t for t in cand if t["trip_id"] in want]
            continue
        long_name = (routes.get(rid, {}).get("route_long_name") or "").strip().lower()
        plain = [t for t in cand if re.match(r"^\d+-R\d+$", t["trip_id"]) and " via " not in t["trip_short_name"].lower()]
        if not plain:
            plain = [t for t in cand if re.match(r"^\d+-[RLP]\d+$", t["trip_id"])]
        if not plain:
            plain = cand
        best: dict[str, dict] = {}
        for t in plain:
            d = str(t["direction_id"])
            short = (t["trip_short_name"] or "").strip().lower()
            # Skor: cocok persis dengan route_long_name, lalu paling pendek.
            score = (0 if short == long_name else 1, len(short))
            if d not in best or score < best[d][0]:
                best[d] = (score, t)
        chosen[rid] = [v[1] for v in sorted(best.values(), key=lambda x: str(x[1]["direction_id"]))]
    return chosen


def build_corridor_halte(
    chosen: dict[str, list[dict]], stop_times: dict[str, list[dict]]
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Urutan halte per koridor (union semua trip terpilih, urut kemunculan).

    Catatan: `load_graph_data()` memakai `koridor_halte` HANYA sebagai himpunan
    (`halte_to_koridor[halte_id].add(koridor_id)`), jadi urutan dan duplikat
    tidak mempengaruhi routing. Edge graf dibangun dari `segmen`, bukan dari
    tabel ini.
    """
    urutan: dict[str, list[str]] = {}
    shape_of: dict[str, str] = {}
    for rid, trips in chosen.items():
        seen: list[str] = []
        for t in trips:
            for r in stop_times.get(t["trip_id"], []):
                if r["stop_id"] not in seen:
                    seen.append(r["stop_id"])
        urutan[rid] = seen
        for t in trips:
            shape_of[t["trip_id"]] = t["shape_id"]
    return urutan, shape_of


# --------------------------------------------------------------------------
# Ridership
# --------------------------------------------------------------------------
def read_ridership_daily(path: Path) -> dict[tuple[str, str], int]:
    """Ambil blok harian kiri dari BRT Pengambilan Koridor Dimodelkan.xlsx."""
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    out: dict[tuple[str, str], int] = {}
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i < 4:
            continue
        jenis, grup, tanggal, jumlah = row[0], row[1], row[2], row[3]
        if jenis is None or grup is None or tanggal is None:
            continue
        if str(jenis).strip().upper() != "BRT":
            continue
        tanggal_str = tanggal.date().isoformat() if hasattr(tanggal, "date") else str(tanggal)[:10]
        out[(tanggal_str, str(grup).strip())] = int(jumlah or 0)
    wb.close()
    return out


def build_ridership_rows(
    daily: dict[tuple[str, str], int], koridor: set[str]
) -> list[dict]:
    import datetime

    rows = []
    for (tanggal, kid) in sorted(daily, key=lambda k: (k[1], k[0])):
        if kid not in koridor:
            continue
        d = datetime.date.fromisoformat(tanggal)
        rows.append(
            {
                "tanggal": tanggal,
                "koridor_id": kid,
                "grup_rute": kid,
                "hari_tipe": "weekend" if d.weekday() >= 5 else "weekday",
                "jumlah_pelanggan_total": daily[(tanggal, kid)],
                "jumlah_cabang": 1,
                "jumlah_pelanggan_pemodelan": float(daily[(tanggal, kid)]),
                "sumber": "BRT Pengambilan Koridor Dimodelkan.xlsx",
            }
        )
    return rows


# --------------------------------------------------------------------------
# Writers
# --------------------------------------------------------------------------
def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def haversine(a: dict, b: dict) -> float:
    from math import asin, cos, radians, sin, sqrt

    lat1, lon1, lat2, lon2 = map(
        radians, (float(a["stop_lat"]), float(a["stop_lon"]), float(b["stop_lat"]), float(b["stop_lon"]))
    )
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371000 * asin(sqrt(h))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--koridor", default="1,2,3,4,5,8,9,12")
    ap.add_argument("--feed", default=DEFAULT_FEED)
    ap.add_argument("--ridership-xlsx", default=DEFAULT_RIDERSHIP_XLSX)
    ap.add_argument("--out", required=True)
    ap.add_argument(
        "--trips-json",
        default="",
        help='Override pilihan trip, mis. \'{"1":["1-R07","1-R08"],"8":["8-P25","8-P26"]}\'',
    )
    args = ap.parse_args()

    koridor = {k.strip() for k in args.koridor.split(",") if k.strip()}
    feed = Path(args.feed)
    out = Path(args.out)

    routes = {r["route_id"]: r for r in read_gtfs(feed, "routes")}
    trips = read_gtfs(feed, "trips")
    frequencies = read_gtfs(feed, "frequencies")
    stops = {s["stop_id"]: s for s in read_gtfs(feed, "stops")}
    shapes = read_gtfs(feed, "shapes")

    stop_times: dict[str, list[dict]] = defaultdict(list)
    for r in read_gtfs(feed, "stop_times"):
        stop_times[r["trip_id"]].append(r)
    for t in stop_times:
        stop_times[t].sort(key=lambda x: int(x["stop_sequence"]))

    chosen = select_trips(trips, routes, koridor, json.loads(args.trips_json) if args.trips_json else None)
    urutan, _ = build_corridor_halte(chosen, stop_times)

    missing = sorted(k for k in koridor if k not in chosen)
    if missing:
        print(f"FATAL: koridor {missing} tidak punya trip di feed", file=sys.stderr)
        return 2

    freq_by_trip = {f["trip_id"]: f for f in frequencies}

    # --- koridor.csv
    write_csv(
        out / "koridor.csv",
        ["koridor_id", "nama_pendek", "nama_panjang", "created_at"],
        [
            {
                "koridor_id": int(k) if k.isdigit() else k,
                "nama_pendek": k,
                "nama_panjang": routes[k]["route_long_name"],
                "created_at": CREATED_AT,
            }
            for k in sorted(koridor, key=lambda x: (len(x), x))
        ],
    )

    # --- halte.csv (only stops used by the selected corridors)
    used = {sid for seq in urutan.values() for sid in seq}
    write_csv(
        out / "halte.csv",
        ["halte_id", "nama", "lat", "lng", "created_at"],
        [
            {
                "halte_id": sid,
                "nama": stops[sid]["stop_name"],
                "lat": stops[sid]["stop_lat"],
                "lng": stops[sid]["stop_lon"],
                "created_at": HALTE_CREATED_AT,
            }
            for sid in sorted(used)
            if sid in stops
        ],
    )

    # --- koridor_halte.csv (duplikat halte transfer dipertahankan)
    kh_rows, kh_id = [], 0
    for k in sorted(koridor, key=lambda x: (len(x), x)):
        for idx, sid in enumerate(urutan[k]):
            kh_id += 1
            kh_rows.append(
                {"id": kh_id, "koridor_id": int(k) if k.isdigit() else k,
                 "halte_id": sid, "urutan": idx, "created_at": CREATED_AT}
            )
    write_csv(out / "koridor_halte.csv", ["id", "koridor_id", "halte_id", "urutan", "created_at"], kh_rows)

    # --- gtfs_trips / frequencies / stop_times
    trip_rows, freq_rows, st_rows = [], [], []
    for k in sorted(koridor, key=lambda x: (len(x), x)):
        for t in chosen[k]:
            trip_rows.append(
                {
                    "trip_id": t["trip_id"], "route_id": int(k) if k.isdigit() else k,
                    "service_id": t["service_id"], "trip_headsign": t["trip_headsign"],
                    "trip_short_name": t["trip_short_name"], "direction_id": t["direction_id"],
                    "block_id": t.get("block_id", ""), "shape_id": t["shape_id"],
                    "wheelchair_accessible": "", "bikes_allowed": "",
                }
            )
            f = freq_by_trip.get(t["trip_id"], {})
            freq_rows.append(
                {
                    "trip_id": t["trip_id"],
                    "start_time": f.get("start_time", "00:00:00"),
                    "end_time": f.get("end_time", "23:59:59"),
                    "headway_secs": f.get("headway_secs", ""),
                    "exact_times": f.get("exact_times", 0),
                }
            )
            for r in stop_times[t["trip_id"]]:
                st_rows.append(
                    {
                        "trip_id": r["trip_id"], "stop_sequence": r["stop_sequence"],
                        "stop_id": r["stop_id"], "arrival_time": r["arrival_time"],
                        "departure_time": r["departure_time"],
                        "stop_headsign": r.get("stop_headsign", ""),
                        "pickup_type": 0.0, "drop_off_type": 0.0,
                        "continuous_pickup": "", "continuous_drop_off": "",
                        "shape_dist_traveled": r.get("shape_dist_traveled") or 0.0,
                        "timepoint": 0.0,
                    }
                )
    write_csv(out / "gtfs_trips.csv",
              ["trip_id", "route_id", "service_id", "trip_headsign", "trip_short_name",
               "direction_id", "block_id", "shape_id", "wheelchair_accessible", "bikes_allowed"],
              trip_rows)
    write_csv(out / "gtfs_frequencies.csv",
              ["trip_id", "start_time", "end_time", "headway_secs", "exact_times"], freq_rows)
    write_csv(out / "gtfs_stop_times.csv",
              ["trip_id", "stop_sequence", "stop_id", "arrival_time", "departure_time",
               "stop_headsign", "pickup_type", "drop_off_type", "continuous_pickup",
               "continuous_drop_off", "shape_dist_traveled", "timepoint"], st_rows)

    # --- segmen.csv (per koridor, dari urutan halte)
    seg_rows, seg_id = [], 0
    for k in sorted(koridor, key=lambda x: (len(x), x)):
        seq = urutan[k]
        for idx in range(len(seq) - 1):
            a, b = seq[idx], seq[idx + 1]
            if a not in stops or b not in stops:
                continue
            # estimasi waktu tempuh dari trip representatif bila tersedia
            seg_id += 1
            dist = haversine(stops[a], stops[b])
            seg_rows.append(
                {
                    "segmen_id": f"{k}_{a}_{b}", "koridor_id": int(k) if k.isdigit() else k,
                    "halte_asal": a, "halte_tujuan": b, "urutan": idx,
                    "waktu_tempuh_detik": int(max(30, dist / 6.0)),  # ~21.6 km/jam
                    "created_at": SEGMEN_CREATED_AT,
                }
            )
    write_csv(out / "segmen.csv",
              ["segmen_id", "koridor_id", "halte_asal", "halte_tujuan", "urutan",
               "waktu_tempuh_detik", "created_at"], seg_rows)

    # --- shapes.csv
    want_shape = {t["shape_id"] for k in koridor for t in chosen[k]}
    sh_rows, sh_id = [], 0
    for r in shapes:
        if r["shape_id"] not in want_shape:
            continue
        sh_id += 1
        kor = next((k for k in koridor if any(t["shape_id"] == r["shape_id"] for t in chosen[k])), "")
        sh_rows.append(
            {"id": sh_id, "koridor_id": int(kor) if str(kor).isdigit() else kor,
             "shape_id": r["shape_id"], "lat": r["shape_pt_lat"], "lng": r["shape_pt_lon"],
             "urutan": r["shape_pt_sequence"]}
        )
    write_csv(out / "shapes.csv", ["id", "koridor_id", "shape_id", "lat", "lng", "urutan"], sh_rows)

    # --- ridership_harian_turunan.csv
    daily = read_ridership_daily(Path(args.ridership_xlsx))
    rid_rows = build_ridership_rows(daily, koridor)
    write_csv(out / "ridership_harian_turunan.csv",
              ["tanggal", "koridor_id", "grup_rute", "hari_tipe", "jumlah_pelanggan_total",
               "jumlah_cabang", "jumlah_pelanggan_pemodelan", "sumber"], rid_rows)

    # --- summary + README
    summary = {
        "koridor": sorted(koridor, key=lambda x: (len(x), x)),
        "rows": {
            "koridor.csv": len(koridor), "halte.csv": len(used),
            "koridor_halte.csv": len(kh_rows), "segmen.csv": len(seg_rows),
            "shapes.csv": len(sh_rows), "gtfs_trips.csv": len(trip_rows),
            "gtfs_frequencies.csv": len(freq_rows), "gtfs_stop_times.csv": len(st_rows),
            "ridership_harian_turunan.csv": len(rid_rows),
        },
        "trips_per_koridor": {k: [t["trip_id"] for t in chosen[k]] for k in sorted(koridor, key=lambda x: (len(x), x))},
    }
    (out / "summary_counts.csv").write_text(
        "\n".join(f"{k},{v}" for k, v in summary["rows"].items()) + "\n", encoding="utf-8"
    )
    (out / "manifest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    (out / "README_IMPORT_ORDER.txt").write_text(
        f"""CSV upload-ready Supabase — koridor {sorted(koridor, key=lambda x: (len(x), x))}.
Sumber GTFS: transitland feed (f-transjakarta~id-latest, 2026-07-24).
Sumber ridership: BRT Pengambilan Koridor Dimodelkan.xlsx (BRT harian, 2026-02, 28 hari).

Scope: hanya trip mainline polos (pola "-R##", tanpa "via"), satu per direction_id.
Pola loop "-P##"/"-L##" dan varian "via ..." dibuang.

Upload order:
1. koridor.csv
2. halte.csv
3. gtfs_trips.csv
4. gtfs_frequencies.csv
5. gtfs_stop_times.csv
6. koridor_halte.csv
7. segmen.csv
8. shapes.csv
9. ridership_harian_turunan.csv   <-- PENTING: upsert, jangan hapus data koridor 1-5 yang sudah ada.

Catatan:
- ridership_harian_turunan.csv memuat koridor {sorted(koridor, key=lambda x: (len(x), x))} x 28 hari (2026-02-01..2026-02-28).
  Bila koridor 1-5 sudah ada di Supabase, lakukan UPSERT per (tanggal, koridor_id), bukan DELETE.
- jadwal, kepadatan_bus, kepadatan_historis adalah legacy/fallback dan tidak diregenerasi di sini.

Validasi SQL:
SELECT t.route_id, COUNT(DISTINCT st.trip_id) AS trips, COUNT(*) AS stop_time_rows
FROM gtfs_stop_times st JOIN gtfs_trips t ON t.trip_id = st.trip_id
GROUP BY t.route_id ORDER BY t.route_id;

SELECT koridor_id, COUNT(*) AS hari, MIN(tanggal), MAX(tanggal)
FROM ridership_harian_turunan GROUP BY koridor_id ORDER BY koridor_id;
""",
        encoding="utf-8",
    )

    print(f"OK -> {out}")
    for k, v in summary["rows"].items():
        print(f"   {k:32s} {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
