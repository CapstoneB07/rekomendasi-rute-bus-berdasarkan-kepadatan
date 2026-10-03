"""Route-level Monte Carlo terhadap kode terbaru (R8 step 1-5).

Membandingkan rekomendasi density-aware vs baseline bidirectional Dijkstra
(crowding-unaware, k=1) pada graf Supabase, atas N replikasi kepadatan stokastik.

Pasangan A (G00168 -> G00214) punya 2 kandidat rute -> satu-satunya tempat
route-level MC bisa menunjukkan divergence. Pasangan D dipakai sebagai negative
control (ekspektasi route_change_rate ~ 0 karena cuma 1 rute feasible).

Jalankan dari backend/:
    ./venv/Scripts/python.exe scripts/run_route_level_mc.py [--replications N]
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.supabase_client import get_client
from services.dijkstra import load_graph_data
from services.gtfs_simulation import load_simulation_context
from services.monte_carlo import run_monte_carlo_experiment

SCENARIOS = [
    # Pasangan A (2 kandidat) — satu-satunya yang bisa divergen.
    {"name": "A-G00168-G00214", "halte_asal": "G00168", "halte_tujuan": "G00214"},
    # Negative control D (1 rute feasible) — ekspektasi tidak ada perubahan rute.
    {"name": "D-P00017-G00016", "halte_asal": "P00017", "halte_tujuan": "G00016"},
    {"name": "D-P00017-G00039", "halte_asal": "P00017", "halte_tujuan": "G00039"},
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
    parser.add_argument("--replications", type=int, default=100)
    parser.add_argument("--jam", type=int, default=8)
    args = parser.parse_args()

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

    sim_time = args.jam * 3600
    result = run_monte_carlo_experiment(
        ctx,
        graph_data,
        SCENARIOS,
        replications=args.replications,
        master_seed="route-level-mc",
        jam=args.jam,
        hari_tipe="weekday",
        sim_time=sim_time,
    )

    for scenario in result["routing_sensitivity"]["scenarios"]:
        pc = scenario["paired_comparison"]
        print(f"\n=== {scenario['name']} ===")
        print(f"  unique_top_route_count : {scenario['unique_top_route_count']}")
        print(f"  route_change_rate      : {pc['route_change_rate']}")
        print(f"  tie_rate               : {pc['tie_rate']}")
        print(f"  improvement_rate       : {pc['improvement_rate']}")
        print(f"  mean_density_delta     : {pc['mean_density_delta']}")
        print(f"  median_density_delta   : {pc['median_density_delta']}")
        print(f"  mean_extra_time_s      : {pc['mean_extra_time_seconds']}")
        print(f"  baseline_density_mean  : {scenario['baseline_density_mean']}")
        print(f"  recommended_density_mean: {scenario['recommended_density_mean']}")
        reps = scenario["replications"]
        worse = sum(
            1 for r in reps
            if r["density_delta"] is not None and r["density_delta"] < -0.01
        )
        baseline_in_candidates = sum(
            1 for r in reps
            if any(c["is_baseline_candidate"] for c in r["candidate_details"])
        )
        print(f"  p05_density_delta      : {pc['p05_density_delta']}")
        print(f"  worse_than_baseline    : {worse}/{len(reps)}")
        print(f"  baseline_in_candidates : {baseline_in_candidates}/{len(reps)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
