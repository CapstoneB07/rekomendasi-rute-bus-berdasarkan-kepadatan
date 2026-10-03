"""Generate `kepadatan_bus` untuk koridor baru dari simulasi GTFS.

Latar: `kepadatan_bus` (dan `jadwal`) hanya berisi koridor 1-5. Tanpa data ini,
`build_graph` jatuh ke `KEPADATAN_FALLBACK = 0.5` untuk koridor 8/9/12, sehingga
"kepadatan" di koridor baru adalah konstanta -> setiap skenario B/C di sana
adalah artefak, bukan temuan.

Script ini memakai `load_simulation_context()` (sumber yang sama dgn produksi)
untuk menghasilkan baris `kepadatan_bus` per (bus_id, koridor_id, jam, hari_tipe),
lalu menulis CSV yang bisa di-import. Koridor 1-5 TIDAK disentuh.

Jalankan dari backend/:
    SCOPED_KORIDOR="1,2,3,4,5,8,9,12" ./venv/Scripts/python.exe scripts/gen_kepadatan_bus.py --out "<dir>"
"""
from __future__ import annotations
import argparse, asyncio, csv, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.supabase_client import get_client
from services.dijkstra import load_graph_data
from services.gtfs_simulation import (
    load_simulation_context, display_load_factor, _trip_loads_for_corridor,
)
from services.config import SCOPED_KORIDOR, scoped_sorted

JAM_LIST = [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22]
HARI = "weekday"
TANGGAL_WEEKDAY = "2026-02-02"   # Senin, ada di ridership
TANGGAL_WEEKEND = "2026-02-01"   # Minggu, ada di ridership


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--koridor-baru", default="8,9,12")
    args = ap.parse_args()
    new_kor = {k.strip() for k in args.koridor_baru.split(",") if k.strip()}
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)

    sb = get_client()
    print(f"scope: {','.join(scoped_sorted())}")
    gd = await load_graph_data(sb)
    halte = sb.table("halte").select("halte_id, nama, lat, lng").execute().data
    shapes = []
    off = 0
    while True:
        c = sb.table("shapes").select("*").range(off, off + 999).execute().data
        if not c: break
        shapes += c; off += 1000
        if len(c) < 1000: break
    ctx = load_simulation_context(sb, halte_rows=halte, segmen=gd["segmen"],
                                  shapes_rows=shapes,
                                  allowed_halte_ids=set(gd["halte_to_koridor"]))
    print(f"trip instances: {len(ctx.instances)}")

    # bus per koridor dari jadwal hasil simulasi
    bus_by_kor: dict[str, list[str]] = {}
    for bus_id, stops in ctx.jadwal.items():
        if not stops: continue
        kid = str(stops[0].get("koridor_id"))
        bus_by_kor.setdefault(kid, []).append(bus_id)

    rows = []
    run_id = "gen-kepadatan-bus"
    for kid in sorted(new_kor, key=lambda x: int(x) if x.isdigit() else 999):
        vals = []
        for hari, tanggal in (("weekday", TANGGAL_WEEKDAY), ("weekend", TANGGAL_WEEKEND)):
            loads, debug = _trip_loads_for_corridor(ctx, tanggal, kid, run_id)
            if not loads:
                print(f"  WARNING: koridor {kid} tidak menghasilkan trip load", file=sys.stderr)
                break
            meta = {i["trip_instance_id"]: i for i in ctx.instances if i["koridor_key"] == kid}
            for tid, payload in loads.items():
                inst = meta.get(tid)
                if inst is None:
                    continue
                lf = display_load_factor(float(payload["trip_load_factor"]))
                # skema live TIDAK punya tanggal/periode -> jangan ditulis
                jam = int(inst["departure_time"]) // 3600 % 24
                vals.append(lf)
                rows.append({
                    "bus_id": tid,
                    "koridor_id": int(kid),
                    "jam": jam,
                    "hari_tipe": hari,
                    "kepadatan": round(lf, 4),
                })
        if vals:
            print(f"  koridor {kid:3s}: {len(vals):4d} baris | "
                  f"LF min={min(vals):.3f} max={max(vals):.3f} rata={sum(vals)/len(vals):.4f}")

    fields = ["bus_id","koridor_id","jam","hari_tipe","kepadatan"]
    p = out / "kepadatan_bus_new.csv"
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields); w.writeheader(); w.writerows(rows)
    print(f"\nOK -> {p}  ({len(rows)} baris)")
    return 0

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
