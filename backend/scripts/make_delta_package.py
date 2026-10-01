"""Pisahkan paket upload-ready menjadi DELTA (hanya baris yang belum ada di Supabase).

Paket penuh bersifat snapshot: ia memuat ulang baris koridor yang sudah ada
di Supabase. Karena PK-nya sama (mis. shapes.id 1..2001), import langsung akan
kena 23505 duplicate key. Delta hanya berisi baris BARU sehingga bisa di-import
apa adanya lewat dashboard tanpa konflik.

Paket default: C502 (scope 1,2,3,4,5,8,9,12,14). Bisa diarahkan dengan --pkg.
Output: <pkg>/delta/*.csv

PERINGATAN: delta dihitung terhadap keadaan live SAAT INI. Bila user sudah
meng-upload sebagian file, delta itu basi dan akan menabrak. Jalankan ulang
script ini setelah upload parsial (lihat README_IMPORT_ORDER.txt).
"""
from __future__ import annotations
import argparse, csv, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.supabase_client import get_client

DEFAULT_PKG = Path(
    "D:/Projects/Kuliah/Sem67/capstone/Data References/Made CSVs/C502/"
    "supabase_gtfs_routes_1_5_8_9_12_14_upload_ready"
)
# (file, tabel, kolom kunci untuk cek "sudah ada di live")
TABLES = [
    ("koridor.csv", "koridor", "koridor_id"),
    ("halte.csv", "halte", "halte_id"),
    ("gtfs_trips.csv", "gtfs_trips", "trip_id"),
    ("gtfs_frequencies.csv", "gtfs_frequencies", "trip_id"),
    ("gtfs_stop_times.csv", "gtfs_stop_times", None),
    ("koridor_halte.csv", "koridor_halte", "id"),
    ("segmen.csv", "segmen", "segmen_id"),
    ("shapes.csv", "shapes", "id"),
    ("ridership_harian_turunan.csv", "ridership_harian_turunan", None),
]

def read(f: Path):
    with f.open(encoding="utf-8-sig", newline="") as fh:
        r = csv.DictReader(fh)
        return list(r.fieldnames or []), list(r)

def live_keys(sb, table, key):
    out = set(); off = 0
    while True:
        c = sb.table(table).select(key).range(off, off + 999).execute().data
        if not c: break
        for r in c:
            if r.get(key) is not None: out.add(str(r[key]))
        if len(c) < 1000: break
        off += 1000
    return out

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pkg", default=str(DEFAULT_PKG))
    ap.add_argument(
        "--only-koridor",
        default="",
        help="batasi delta ke koridor baru ini saja (mis. 14), agar upload tidak menyentuh koridor lain",
    )
    args = ap.parse_args()
    pkg = Path(args.pkg)
    only = {k.strip() for k in args.only_koridor.split(",") if k.strip()}

    sb = get_client()
    outdir = pkg / "delta"; outdir.mkdir(exist_ok=True)
    # kunci komposit untuk stop_times (trip_id+stop_sequence) & ridership (tanggal+koridor_id)
    st_keys = set(); off = 0
    while True:
        c = sb.table("gtfs_stop_times").select("trip_id,stop_sequence").range(off, off+999).execute().data
        if not c: break
        for r in c: st_keys.add((str(r["trip_id"]), str(r["stop_sequence"])))
        if len(c) < 1000: break
        off += 1000
    rid_keys = set()
    for r in sb.table("ridership_harian_turunan").select("tanggal,koridor_id").limit(1000).execute().data:
        rid_keys.add((str(r["tanggal"]), str(r["koridor_id"])))

    total = 0
    snapshot_total = 0
    for fname, table, key in TABLES:
        header, rows = read(pkg / fname)
        snapshot_total += len(rows)
        if key:
            lk = live_keys(sb, table, key)
            new = [r for r in rows if str(r[key]) not in lk]
        elif table == "gtfs_stop_times":
            new = [r for r in rows if (str(r["trip_id"]), str(r["stop_sequence"])) not in st_keys]
        else:
            new = [r for r in rows if (str(r["tanggal"]), str(r["koridor_id"])) not in rid_keys]

        if only and key in ("koridor_id", "route_id"):
            new = [r for r in new if str(r[key]) in only]
        elif only and table == "ridership_harian_turunan":
            new = [r for r in new if str(r["koridor_id"]) in only]

        with (outdir / fname).open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=header); w.writeheader(); w.writerows(new)
        total += len(new)
        print(f"  {fname:32s} {len(rows):5d} -> {len(new):5d} baris baru")
    print(f"\nTOTAL baris delta: {total}  (paket penuh: {snapshot_total})")
    print(f"Output: {outdir}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
