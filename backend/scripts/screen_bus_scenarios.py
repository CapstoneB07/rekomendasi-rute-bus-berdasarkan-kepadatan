"""Screen pasangan OD yang route-level-nya D, klasifikasikan skenario bus-level.

Reframe evaluasi (Part B / masalah #6): karena route-level B/C hampir tidak
muncul (0/60 OD alternatif), evaluasi MC dialihkan ke level bus. Script ini
mengambil pasangan OD dari results/scenario_catalog.csv yang bertipe D (atau
semua pasangan bila flag --all), menjalankan pipeline rute sekali, lalu
mengklasifikasikan kandidat bus tiap blok 'naik' memakai classify_bus_level().

Jalankan dari backend/:
    ./venv/Scripts/python.exe scripts/screen_bus_scenarios.py [--all]
"""

import argparse
import asyncio
import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.bus_selector import collect_bus_candidates
from services.dijkstra import (
    build_graph,
    dijkstra,
    format_rute,
    load_graph_data,
)
from services.gtfs_simulation import load_simulation_context
from services.monte_carlo import build_recommendation_crowding_snapshot
from services.scenario_classifier import classify_bus_level
from services.supabase_client import get_client

RESULTS_DIR = Path(__file__).resolve().parents[2] / "results"
CATALOG = RESULTS_DIR / "scenario_catalog.csv"
OUTPUT = RESULTS_DIR / "bus_scenario_catalog.csv"
TIME_WINDOWS = [(8, "weekday")]

FIELDNAMES = [
    "scenario_type", "origin", "destination", "koridor_id", "halte_naik",
    "earliest_bus_density", "later_bus_density", "density_delta",
    "earliest_eta_menit", "later_eta_menit", "wait_menit", "reason",
]


def _load_shapes(sb) -> list:
    rows: list[dict] = []
    offset = 0
    while True:
        chunk = (
            sb.table("shapes")
            .select("*")
            .order("koridor_id")
            .order("urutan")
            .range(offset, offset + 999)
            .execute()
            .data
        )
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < 1000:
            break
        offset += 1000
    return rows


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true",
                        help="screening semua pasangan (bukan hanya tipe D)")
    args = parser.parse_args()

    try:
        sb = get_client()
        graph_data = await load_graph_data(sb)
        halte = sb.table("halte").select("halte_id, nama, lat, lng").execute().data
        shapes = _load_shapes(sb)
        ctx = load_simulation_context(
            sb,
            halte_rows=halte,
            segmen=graph_data["segmen"],
            shapes_rows=shapes,
            allowed_halte_ids=set(graph_data["halte_to_koridor"]),
        )
    except Exception as exc:
        print(f"FATAL: Supabase tidak terjangkau: {exc!r}", file=sys.stderr)
        return 2

    if not CATALOG.exists():
        print(f"FATAL: {CATALOG} belum ada; jalankan screen_scenarios.py dulu.", file=sys.stderr)
        return 2

    pairs: set[tuple[str, str]] = set()
    with CATALOG.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if args.all or row.get("scenario_type") == "D":
                pairs.add((row["origin"], row["destination"]))

    rows: list[dict] = []
    for jam, hari_tipe in TIME_WINDOWS:
        sim_time = jam * 3600
        for origin, destination in sorted(pairs):
            try:
                graph = build_graph(graph_data, jam=jam, hari_tipe=hari_tipe)
                routes = dijkstra(graph, origin, destination, k=5)
                if not routes:
                    continue
                snapshot = build_recommendation_crowding_snapshot(
                    ctx,
                    tanggal=None,
                    sim_time=sim_time,
                    request_seed_parts=(origin, destination, jam, hari_tipe),
                )
                realtime = snapshot["realtime_kepadatan"]
                # Ambil rute pertama (route-level D = cuma 1 rute) dan scan
                # semua blok 'naik'.
                formatted = format_rute(routes[0], graph_data)
                for blok in formatted["segmen"]:
                    if blok.get("tipe") != "naik":
                        continue
                    kandidat = collect_bus_candidates(
                        ctx.jadwal,
                        realtime,
                        blok["koridor_id"],
                        blok["naik_di_id"],
                        reference_time=sim_time,
                    )
                    klasifikasi = classify_bus_level(kandidat)
                    row = {
                        "scenario_type": klasifikasi["scenario_type"],
                        "origin": origin,
                        "destination": destination,
                        "koridor_id": blok["koridor_id"],
                        "halte_naik": blok["naik_di_id"],
                        "reason": klasifikasi.get("reason", ""),
                    }
                    for key in (
                        "earliest_bus_density",
                        "later_bus_density",
                        "density_delta",
                        "earliest_eta_menit",
                        "later_eta_menit",
                        "wait_menit",
                    ):
                        row[key] = klasifikasi.get(key, "")
                    rows.append(row)
            except Exception as exc:
                print(f"SKIP {origin}->{destination} ({exc!r})", file=sys.stderr)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in FIELDNAMES})

    counts = Counter(row["scenario_type"] for row in rows)
    print(f"Saved: {OUTPUT}")
    print(f"Total blok naik tersaring: {len(rows)}")
    print(f"Type counts: {dict(counts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
