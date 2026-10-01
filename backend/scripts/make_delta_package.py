"""Pisahkan paket C501 menjadi DELTA (hanya baris yang belum ada di Supabase).

Paket penuh bersifat snapshot: ia memuat ulang baris koridor 1-5 yang sudah ada
di Supabase. Karena PK-nya sama (mis. shapes.id 1..2001), import langsung akan
kena 23505 duplicate key. Delta hanya berisi baris BARU sehingga bisa di-import
apa adanya lewat dashboard tanpa konflik.

Output: <pkg>/delta/*.csv
"""
from __future__ import annotations
import csv, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.supabase_client import get_client

PKG = Path("D:/Projects/Kuliah/Sem67/capstone/Data References/Made CSVs/C501/supabase_gtfs_routes_1_5_8_9_12_upload_ready")
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
    sb = get_client()
    outdir = PKG / "delta"; outdir.mkdir(exist_ok=True)
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
    for fname, table, key in TABLES:
        header, rows = read(PKG / fname)
        if key:
            lk = live_keys(sb, table, key)
            new = [r for r in rows if str(r[key]) not in lk]
        elif table == "gtfs_stop_times":
            new = [r for r in rows if (str(r["trip_id"]), str(r["stop_sequence"])) not in st_keys]
        else:
            new = [r for r in rows if (str(r["tanggal"]), str(r["koridor_id"])) not in rid_keys]
        with (outdir / fname).open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=header); w.writeheader(); w.writerows(new)
        total += len(new)
        print(f"  {fname:32s} {len(rows):5d} -> {len(new):5d} baris baru")
    print(f"\nTOTAL baris delta: {total}  (paket penuh: 5574)")
    print(f"Output: {outdir}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
