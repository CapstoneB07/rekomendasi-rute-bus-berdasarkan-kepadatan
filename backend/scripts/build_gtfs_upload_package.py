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


def read_branch_counts(path: Path) -> dict[str, int]:
    """Jumlah cabang per koridor dari blok KANAN xlsx (kolom N..Q).

    Ini WAJIB: `jumlah_pelanggan_pemodelan = jumlah_pelanggan_total / cabang`.
    Tanpa pembagian ini koridor multi-cabang (2, 3, 4, 5, 7, 9, 13) akan
    dilaporkan 2-4x lipat, dan nilainya bertabrakan dengan data yang sudah ada
    di Supabase untuk koridor 1-5.

    Kolom: N='Koridor' (mis. "BRT 3 (3 cabang)"), O='Cabang', ...
    """
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    out: dict[str, int] = {}
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i < 4:
            continue
        label, cabang = row[13], row[14]
        if label is None or cabang is None:
            continue
        match = re.search(r"BRT\s*(\d+)", str(label))
        if not match:
            continue
        try:
            out[match.group(1)] = int(cabang)
        except (TypeError, ValueError):
            continue
    wb.close()
    return out


def build_ridership_rows(
    daily: dict[tuple[str, str], int],
    koridor: set[str],
    branch_counts: dict[str, int],
) -> list[dict]:
    """Baris ridership_harian_turunan SESUAI SKEMA SUPABASE LIVE.

    Skema live (diverifikasi lewat PostgREST 2026-10-01):
      ridership_id, jenis_layanan, koridor_id, tanggal, hari_tipe,
      jumlah_pelanggan_total, jumlah_cabang_pemodelan,
      jumlah_pelanggan_pemodelan, sumber, catatan

    Catatan: `grup_rute` dan `jumlah_cabang` TIDAK ADA di tabel live — jangan
    dipakai (paket lama memakai header itu dan akan gagal saat import).
    """
    import datetime

    rows = []
    for (tanggal, kid) in sorted(daily, key=lambda k: (int(k[1]) if k[1].isdigit() else 999, k[0])):
        if kid not in koridor:
            continue
        total = daily[(tanggal, kid)]
        cabang = branch_counts.get(kid, 1)
        d = datetime.date.fromisoformat(tanggal)
        rows.append(
            {
                "ridership_id": f"RID-{tanggal.replace('-', '')}-{kid}",
                "jenis_layanan": "BRT",
                "koridor_id": kid,
                "tanggal": tanggal,
                "hari_tipe": "weekend" if d.weekday() >= 5 else "weekday",
                "jumlah_pelanggan_total": total,
                "jumlah_cabang_pemodelan": cabang,
                "jumlah_pelanggan_pemodelan": total / cabang,
                "sumber": "BRT Pengambilan Koridor Dimodelkan.xlsx",
                "catatan": (
                    "jumlah_pelanggan_pemodelan = jumlah_pelanggan_total / "
                    "jumlah_cabang_pemodelan"
                ),
            }
        )
    return rows


RIDERSHIP_FIELDS = [
    "ridership_id", "jenis_layanan", "koridor_id", "tanggal", "hari_tipe",
    "jumlah_pelanggan_total", "jumlah_cabang_pemodelan",
    "jumlah_pelanggan_pemodelan", "sumber", "catatan",
]


# --------------------------------------------------------------------------
# Waktu tempuh segmen
# --------------------------------------------------------------------------
def fetch_live_rows(client, table: str) -> list[dict]:
    """Ambil semua baris live (paged) untuk dipakai ulang apa adanya."""
    rows: list[dict] = []
    offset = 0
    while True:
        chunk = client.table(table).select("*").range(offset, offset + 999).execute().data
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < 1000:
            break
        offset += 1000
    return rows


def live_max_ids(client=None) -> dict[str, int]:
    """max(id) live untuk tabel ber-PK `id`, supaya id paket tidak menabrak.

    `koridor_halte.id` dan `shapes.id` adalah PK biasa tanpa default, jadi nilai
    eksplisit dari CSV dipakai apa adanya. Bila paket memakai id mulai dari 1,
    ia akan menimpa baris koridor 1-5 (atau ditolak 23505). Offset = max(id) live.

    Tanpa Supabase (offline), dipakai nilai aman dari paket live terakhir.
    """
    fallback = {"koridor_halte": 176, "shapes": 2001}
    if client is None:
        return fallback
    out = dict(fallback)
    for table in fallback:
        try:
            rows = (
                client.table(table).select("id").order("id", desc=True).limit(1).execute().data
            )
            if rows:
                out[table] = int(rows[0]["id"])
        except Exception as e:
            print(
                f"WARNING: gagal ambil max(id) {table} ({e!r}); pakai fallback "
                f"{fallback[table]} — PASTIKAN tidak menabrak data live",
                file=sys.stderr,
            )
    return out


def build_segment_times_per_trip(
    chosen: dict[str, list[dict]], stop_times: dict[str, list[dict]]
) -> dict[tuple[str, str, str], int]:
    """(koridor, asal, tujuan) -> waktu tempuh, meniru cakupan `segmen` live.

    `segmen` live memuat 171 baris untuk koridor 1-5, sedangkan dedupe union
    urutan halte hanya menghasilkan 166 (kor 3: 27 vs 26, kor 4: 36 vs 34,
    kor 5: 34 vs 32). Jadi live memakai **pasangan per trip**, bukan union
    dedupe. Fungsi ini mengikuti live supaya himpunan segmen_id identik.

    Bila satu pasangan muncul di >1 trip, dipakai nilai pertama (deterministik
    karena urutan trip stabil).
    """
    out: dict[tuple[str, str, str], int] = {}
    for rid, trips in chosen.items():
        for t in trips:
            rows = stop_times.get(t["trip_id"], [])
            for i in range(len(rows) - 1):
                a, b = rows[i], rows[i + 1]
                key = (rid, a["stop_id"], b["stop_id"])
                if key in out:
                    continue
                try:
                    delta = hhmmss_to_seconds(b["arrival_time"]) - hhmmss_to_seconds(
                        a["departure_time"]
                    )
                except (ValueError, KeyError):
                    continue
                if delta > 0:
                    out[key] = int(delta)
    return out


def build_segment_times_feed(
    chosen: dict[str, list[dict]], stop_times: dict[str, list[dict]]
) -> dict[tuple[str, str, str], int]:
    """(koridor, asal, tujuan) -> waktu tempuh dari jadwal GTFS nyata.

    Definisi: `arrival(B) - departure(A)` = waktu dalam kendaraan yang dialami
    penumpang (dwell di A tidak dihitung). Ini memakai waktu terjadiwal yang
    sebenarnya, bukan taksiran jarak/kecepatan.
    """
    out: dict[tuple[str, str, str], int] = {}
    for rid, trips in chosen.items():
        for t in trips:
            rows = stop_times.get(t["trip_id"], [])
            for i in range(len(rows) - 1):
                a, b = rows[i], rows[i + 1]
                key = (rid, a["stop_id"], b["stop_id"])
                if key in out:
                    continue
                try:
                    delta = hhmmss_to_seconds(b["arrival_time"]) - hhmmss_to_seconds(
                        a["departure_time"]
                    )
                except (ValueError, KeyError):
                    continue
                if delta > 0:
                    out[key] = int(delta)
    return out


def build_segment_times_per_koridor(
    chosen: dict[str, list[dict]], stop_times: dict[str, list[dict]]
) -> dict[str, int]:
    """Waktu tempuh KONSTAN per koridor — pendekatan paket C251.

    C251 memakai satu angka per koridor (kor 1 ~216 s, kor 3 ~331 s). Direplikasi
    di sini supaya perbandingan A/B terhadap paket lama tetap mungkin, tapi
    BUKAN default: nilai konstan menghapus variasi antar-segmen.
    """
    out: dict[str, int] = {}
    for rid, trips in chosen.items():
        deltas: list[int] = []
        for t in trips:
            rows = stop_times.get(t["trip_id"], [])
            for i in range(len(rows) - 1):
                try:
                    d = hhmmss_to_seconds(rows[i + 1]["arrival_time"]) - hhmmss_to_seconds(
                        rows[i]["departure_time"]
                    )
                except (ValueError, KeyError):
                    continue
                if d > 0:
                    deltas.append(d)
        if deltas:
            out[rid] = int(round(sum(deltas) / len(deltas)))
    return out



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
    ap.add_argument(
        "--waktu-tempuh",
        choices=["feed", "per_koridor"],
        default="feed",
        help=(
            "feed (default) = arrival(B)-departure(A) dari jadwal GTFS nyata; "
            "per_koridor = satu angka konstan per koridor (gaya paket C251, "
            "tanpa variasi antar-segmen)."
        ),
    )
    ap.add_argument(
        "--offline-ids",
        action="store_true",
        help="pakai max(id) fallback tanpa query Supabase (untuk build offline)",
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

    # --- offset id untuk tabel ber-PK `id` (koridor_halte, shapes)
    # Tanpa ini, id paket (mulai dari 1) menabrak id live koridor 1-5.
    id_offsets = {"koridor_halte": 0, "shapes": 0}
    live_rows: dict[str, list[dict]] | None = None
    if not args.offline_ids:
        try:
            from services.supabase_client import get_client

            client = get_client()
            id_offsets = live_max_ids(client)
            live_rows = {
                t: fetch_live_rows(client, t)
                for t in ("segmen", "koridor_halte", "shapes")
            }
        except Exception as e:
            print(
                f"WARNING: tidak bisa konek Supabase ({e!r}); "
                f"pakai fallback id & tanpa reuse baris live. "
                f"Jalankan dengan --offline-ids bila memang offline.",
                file=sys.stderr,
            )
            id_offsets = live_max_ids(None)
    else:
        id_offsets = live_max_ids(None)
    print(
        f"id offset: koridor_halte>{id_offsets['koridor_halte']} "
        f"shapes>{id_offsets['shapes']} | reuse baris live: "
        f"{'ya' if live_rows else 'tidak'}"
    )

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

    # --- waktu tempuh segmen (dihitung awal: dipakai halte.csv & segmen.csv)
    times_per_trip = build_segment_times_per_trip(chosen, stop_times)
    times_per_kor = build_segment_times_per_koridor(chosen, stop_times)

    # --- halte.csv
    # Himpunan halte harus mencakup SEMUA endpoint segmen, termasuk baris live
    # yang dipakai ulang (mis. koridor 4 memakai G00197 yang tidak ada di trip
    # pilihan kita). Tanpa ini `build_graph` gagal KeyError.
    used = {sid for seq in urutan.values() for sid in seq}
    used |= {a for (_k, a, _b) in times_per_trip} | {b for (_k, _a, b) in times_per_trip}
    if live_rows is not None:
        for r in live_rows.get("segmen", []):
            if str(r["koridor_id"]) in koridor:
                used.add(str(r["halte_asal"]))
                used.add(str(r["halte_tujuan"]))
    missing_stops = sorted(s for s in used if s not in stops)
    if missing_stops:
        print(
            f"WARNING: {len(missing_stops)} halte dipakai segmen tapi tidak ada di "
            f"feed stops.txt: {missing_stops[:5]}",
            file=sys.stderr,
        )
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

    # --- koridor_halte.csv
    # Sama seperti segmen: baris koridor yang sudah ada dipakai APA ADANYA dari
    # live (paket C251 punya baris halte-transfer yang tidak bisa direproduksi),
    # supaya graf koridor 1-5 tidak berubah. Hanya koridor baru yang diturunkan.
    kh_rows, kh_id, kh_seen = [], id_offsets["koridor_halte"], set()
    if live_rows is not None:
        for r in live_rows.get("koridor_halte", []):
            kid = str(r["koridor_id"])
            if kid not in koridor:
                continue
            key = (kid, str(r["halte_id"]))
            if key in kh_seen:
                continue
            kh_seen.add(key)
            kh_rows.append(
                {"id": r["id"], "koridor_id": r["koridor_id"], "halte_id": r["halte_id"],
                 "urutan": r["urutan"], "created_at": r.get("created_at") or CREATED_AT}
            )
    for k in sorted(koridor, key=lambda x: (len(x), x)):
        if any(str(r["koridor_id"]) == k for r in kh_rows):
            continue
        for idx, sid in enumerate(urutan[k]):
            key = (k, sid)
            if key in kh_seen:
                continue
            kh_seen.add(key)
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
                        # Kolom ini NULL di Supabase live (bigint). Jangan tulis
                        # 0.0 — dashboard CSV importer menolak "0.0" untuk bigint.
                        "pickup_type": "", "drop_off_type": "",
                        "continuous_pickup": "", "continuous_drop_off": "",
                        "shape_dist_traveled": "",
                        "timepoint": "",
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

    # --- segmen.csv
    # Koridor yang SUDAH ada di Supabase dipertahankan APA ADANYA dari live.
    # Alasannya: `segmen` koridor 4 & 5 dikurasi manual di paket C251 dan tidak
    # bisa direproduksi dari feed (sudah diuji: tidak ada subset trip yang
    # menghasilkan himpunan yang sama). Menulis ulang baris koridor 1-5 berisiko
    # merusak graf yang sudah bekerja. Jadi: live rows dipakai ulang, dan hanya
    # koridor BARU yang diturunkan dari feed.
    seg_rows = []
    live_segmen_ids: set[str] = set()
    if live_rows is not None:
        for r in live_rows.get("segmen", []):
            sid = str(r["segmen_id"])
            kid = str(r["koridor_id"])
            if kid in koridor:
                seg_rows.append(
                    {
                        "segmen_id": sid, "koridor_id": r["koridor_id"],
                        "halte_asal": r["halte_asal"], "halte_tujuan": r["halte_tujuan"],
                        "urutan": r["urutan"], "waktu_tempuh_detik": r["waktu_tempuh_detik"],
                        "created_at": r.get("created_at") or SEGMEN_CREATED_AT,
                    }
                )
                live_segmen_ids.add(sid)

    new_koridor = [k for k in sorted(koridor, key=lambda x: (len(x), x))
                   if not any(str(r["koridor_id"]) == k for r in seg_rows)]
    for k in new_koridor:
        idx_of = {h: i for i, h in enumerate(urutan[k])}
        for (kk, a, b), waktu in times_per_trip.items():
            if kk != k:
                continue
            if f"{k}_{a}_{b}" in live_segmen_ids:
                continue
            waktu_final = times_per_kor.get(k, waktu) if args.waktu_tempuh == "per_koridor" else waktu
            seg_rows.append(
                {
                    "segmen_id": f"{k}_{a}_{b}", "koridor_id": int(k) if k.isdigit() else k,
                    "halte_asal": a, "halte_tujuan": b,
                    "urutan": idx_of.get(a, 0),
                    "waktu_tempuh_detik": int(waktu_final),
                    "created_at": SEGMEN_CREATED_AT,
                }
            )
    write_csv(out / "segmen.csv",
              ["segmen_id", "koridor_id", "halte_asal", "halte_tujuan", "urutan",
               "waktu_tempuh_detik", "created_at"], seg_rows)

    # --- shapes.csv
    # Baris koridor yang sudah ada dipakai APA ADANYA dari live (id-nya sudah
    # benar dan tidak menabrak); hanya koridor baru yang id-nya di-offset.
    want_shape = {t["shape_id"] for k in koridor for t in chosen[k]}
    shape_koridor = {t["shape_id"]: k for k in koridor for t in chosen[k]}
    sh_rows, sh_id = [], id_offsets["shapes"]
    live_shape_koridor: set[str] = set()
    if live_rows is not None:
        for r in live_rows.get("shapes", []):
            kid = str(r["koridor_id"])
            if kid not in koridor:
                continue
            sh_rows.append(
                {"id": r["id"], "koridor_id": r["koridor_id"], "shape_id": r["shape_id"],
                 "lat": r["lat"], "lng": r["lng"], "urutan": r["urutan"]}
            )
            live_shape_koridor.add(kid)
    for r in shapes:
        sid = r["shape_id"]
        if sid not in want_shape:
            continue
        kor = shape_koridor.get(sid, "")
        if str(kor) in live_shape_koridor:
            continue
        sh_id += 1
        sh_rows.append(
            {"id": sh_id, "koridor_id": int(kor) if str(kor).isdigit() else kor,
             "shape_id": sid, "lat": r["shape_pt_lat"], "lng": r["shape_pt_lon"],
             "urutan": r["shape_pt_sequence"]}
        )
    write_csv(out / "shapes.csv", ["id", "koridor_id", "shape_id", "lat", "lng", "urutan"], sh_rows)

    # --- ridership_harian_turunan.csv (skema Supabase LIVE)
    daily = read_ridership_daily(Path(args.ridership_xlsx))
    branch_counts = read_branch_counts(Path(args.ridership_xlsx))
    missing_branch = sorted(k for k in koridor if k not in branch_counts)
    if missing_branch:
        print(
            f"WARNING: cabang tidak ditemukan untuk koridor {missing_branch}; "
            f"dipakai 1 (periksa blok kanan xlsx)",
            file=sys.stderr,
        )
    rid_rows = build_ridership_rows(daily, koridor, branch_counts)
    write_csv(out / "ridership_harian_turunan.csv", RIDERSHIP_FIELDS, rid_rows)

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

Waktu tempuh segmen: mode "{args.waktu_tempuh}"
  - feed         = arrival(B) - departure(A) dari jadwal GTFS nyata (waktu dalam
                   kendaraan, dwell tidak dihitung). Punya variasi antar-segmen.
  - per_koridor  = satu angka konstan per koridor (pendekatan paket C251).
  Nilai feed berasal dari jadwal, jadi ini waktu TERJADWAL, bukan pengukuran.

Ridership: skema mengikuti tabel LIVE `ridership_harian_turunan`
(ridership_id, jenis_layanan, koridor_id, tanggal, hari_tipe,
 jumlah_pelanggan_total, jumlah_cabang_pemodelan, jumlah_pelanggan_pemodelan,
 sumber, catatan).
`jumlah_pelanggan_pemodelan = jumlah_pelanggan_total / jumlah_cabang_pemodelan`.
Jumlah cabang diambil dari blok kanan xlsx (BRT 1=1, 2=2, 3=3, 5=2, 9=4, dst).
Koridor 1-5 sudah diverifikasi IDENTIK dengan baris yang ada di Supabase.

Upload order:
1. koridor.csv
2. halte.csv
3. gtfs_trips.csv
4. gtfs_frequencies.csv
5. gtfs_stop_times.csv
6. koridor_halte.csv
7. segmen.csv
8. shapes.csv
9. ridership_harian_turunan.csv

PENTING soal primary key:
- `shapes.id` dan `koridor_halte.id` adalah PK biasa TANPA default/identity.
  Paket ini memakai ulang baris live apa adanya untuk koridor yang sudah ada
  (id-nya identik & isinya identik -> re-upload idempoten), dan meng-offset id
  koridor baru mulai dari max(id) live + 1 (shapes >= 2002, koridor_halte >= 177).
  JANGAN menurunkan id koridor baru tanpa offset: akan menabrak data koridor 1-5.
- Tabel ini juga TIDAK punya unique constraint pada (koridor_id, halte_id), jadi
  baris duplikat akan diterima diam-diam. Paket sudah di-dedupe.

Soal koridor yang sudah ada (1-5):
- `segmen`, `koridor_halte`, dan `shapes` untuk koridor 1-5 dipakai APA ADANYA
  dari Supabase. Alasannya: segmen koridor 4 & 5 dikurasi manual di paket C251
  dan tidak bisa direproduksi dari feed (sudah diuji: tidak ada subset trip yang
  menghasilkan himpunan segmen yang sama). Menulis ulang akan mengubah graf yang
  sudah bekerja.
- `halte.csv` mencakup SEMUA endpoint segmen (termasuk halte seperti G00197 yang
  hanya muncul di baris live). Tanpa itu `build_graph` gagal KeyError.
- `ridership_harian_turunan.csv` untuk koridor 1-5 sudah diverifikasi IDENTIK
  dengan baris live (140/140 baris) -> UPSERT aman, jangan DELETE.

Validasi WAJIB sebelum upload:
  ./venv/Scripts/python.exe scripts/validate_upload_package_live.py --pkg "<dir ini>" --live
  -> harus "HASIL: OK", 0 error. Mengecek: nama kolom, tipe, tabrakan PK
     (id sama tapi isi beda), konsistensi cakupan koridor, dan nilai ridership.
  ./venv/Scripts/python.exe scripts/validate_upload_package.py --pkg "<dir ini>"
  -> validasi topologi graf offline (node/edge/kandidat).

Build ulang paket (butuh Supabase untuk max(id) & reuse baris live):
  ./venv/Scripts/python.exe scripts/build_gtfs_upload_package.py --koridor 1,2,3,4,5,8,9,12 --out "<dir>"
  (tambahkan --trips-json untuk pin pilihan trip; --offline-ids untuk build offline)

Validasi SQL setelah upload:
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
