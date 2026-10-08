"""Probe diagnostik: apakah lever jendela tunggu bisa membalik baris yang kalah?

Untuk tiap baris D dengan delta_v1 == 0 dan densitas bus tercepat > 0.35,
hitung margin kemenangan terbaik yang tersedia di jendela tunggu yang lebih
lebar (20/30/40/60 menit). Margin = (D0 - D) - 0.176 * (w / W), di mana
0.176 = BUS_SCORE_WAIT_WEIGHT / BUS_SCORE_DENSITY_WEIGHT. Baris hanya bisa
menang bila ada kandidat dengan margin > 0 DAN (D0 - D) > 0.01.

Jalankan dari backend/ (butuh Supabase live):
    ./venv/Scripts/python.exe scripts/probe_wait_lever.py
"""

import asyncio
import csv
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.bus_selector import (
    BUS_SCORE_DENSITY_WEIGHT,
    BUS_SCORE_WAIT_WEIGHT,
    collect_bus_candidates,
)
from services.dijkstra import build_graph, dijkstra, format_rute, load_graph_data
from services.gtfs_simulation import load_simulation_context
from services.monte_carlo import build_recommendation_crowding_snapshot
from services.supabase_client import get_client

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "results" / "scenario_catalog.csv"
EVAL = ROOT / "results" / "success_rate_eval.csv"
OUTPUT = ROOT / "results" / "probe_wait_lever.csv"

WAIT_WINDOWS = (20, 30, 40, 60)
RATIO = BUS_SCORE_WAIT_WEIGHT / BUS_SCORE_DENSITY_WEIGHT

FIELDNAMES = [
    "origin", "destination", "time_period", "base_density",
    "best_density_120", "best_wait_menit", "density_advantage",
    "flips_wait20", "flips_wait30", "flips_wait40", "flips_wait60",
]


def _load_shapes(sb) -> list:
    rows: list[dict] = []
    offset = 0
    while True:
        chunk = (
            sb.table("shapes").select("*")
            .order("koridor_id").order("urutan")
            .range(offset, offset + 999).execute().data
        )
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < 1000:
            break
        offset += 1000
    return rows


async def main() -> int:
    print(f"ratio wait/density = {RATIO:.4f}")
    eval_rows = list(csv.DictReader(EVAL.open(newline="", encoding="utf-8")))
    targets = [
        r for r in eval_rows
        if r["scenario_type"] == "D"
        and r["delta_v1"] not in ("", None)
        and float(r["delta_v1"]) == 0.0
        and r["d_base_v1"] not in ("", None)
        and float(r["d_base_v1"]) > 0.35
    ]
    print(f"target rows: {len(targets)}")

    sb = get_client()
    graph_data = await load_graph_data(sb)
    halte = sb.table("halte").select("halte_id, nama, lat, lng").execute().data
    ctx = load_simulation_context(
        sb,
        halte_rows=halte,
        segmen=graph_data["segmen"],
        shapes_rows=_load_shapes(sb),
        allowed_halte_ids=set(graph_data["halte_to_koridor"]),
    )

    out_rows: list[dict] = []
    for index, entry in enumerate(targets, 1):
        jam = int(str(entry["time_period"]).split("h")[0])
        sim_time = jam * 3600
        origin, destination = entry["origin"], entry["destination"]
        print(f"[{index}/{len(targets)}] {origin}->{destination} {entry['time_period']}")
        try:
            snapshot = build_recommendation_crowding_snapshot(
                ctx, tanggal=None, sim_time=sim_time,
                request_seed_parts=(origin, destination, jam, "weekday"),
            )
            realtime = snapshot["realtime_kepadatan"]
            graph = build_graph(graph_data, jam=jam, hari_tipe="weekday")
            routes = dijkstra(graph, origin, destination, k=1)
            if not routes:
                continue
            formatted = format_rute(routes[0], graph_data)
            blocks = [s for s in formatted["segmen"] if s.get("tipe") == "naik"]
            if not blocks:
                continue
            blok = blocks[0]
            kandidat = collect_bus_candidates(
                ctx.jadwal, realtime, blok["koridor_id"], blok["naik_di_id"],
                reference_time=sim_time, max_eta_menit=120,
            )
            if not kandidat:
                continue
            earliest = min(kandidat, key=lambda b: (b["eta_menit"], b["bus_id"]))
            d0 = float(earliest["kepadatan"])
            best = None
            for b in kandidat:
                w = b["eta_menit"] - earliest["eta_menit"]
                advantage = d0 - float(b["kepadatan"])
                if best is None or advantage > best[0]:
                    best = (advantage, w, float(b["kepadatan"]))
            if best is None:
                continue
            advantage, w, dens = best
            flips = {}
            for window in WAIT_WINDOWS:
                margin = advantage - RATIO * (w / window)
                flips[window] = margin > 0 and advantage > 0.01
            out_rows.append({
                "origin": origin,
                "destination": destination,
                "time_period": entry["time_period"],
                "base_density": round(d0, 3),
                "best_density_120": round(dens, 3),
                "best_wait_menit": w,
                "density_advantage": round(advantage, 4),
                "flips_wait20": flips[20],
                "flips_wait30": flips[30],
                "flips_wait40": flips[40],
                "flips_wait60": flips[60],
            })
        except Exception as exc:
            print(f"SKIP {origin}->{destination} ({exc!r})", file=sys.stderr)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(out_rows)

    n = len(out_rows)
    print(f"\nSaved: {OUTPUT} ({n} baris)")
    for window in WAIT_WINDOWS:
        flips = sum(1 for r in out_rows if r[f"flips_wait{window}"])
        print(f"  flips at wait{window}: {flips}/{n} -> potential total wins: {39 + flips}/192")
    no_chance = sum(
        1 for r in out_rows
        if not any(r[f"flips_wait{w}"] for w in WAIT_WINDOWS)
    )
    print(f"  rows with no flipping candidate at any window: {no_chance}/{n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
