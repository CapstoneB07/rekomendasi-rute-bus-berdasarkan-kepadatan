"""Bus-level MC N=500 pada pasangan C' (koridor 3, G00161 -> G00157).

Jalankan dari backend/:
    ./venv/Scripts/python.exe scripts/run_bus_level_mc.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.supabase_client import get_client
from services.dijkstra import load_graph_data
from services.gtfs_simulation import load_simulation_context
from services.monte_carlo import run_bus_level_monte_carlo


async def main() -> int:
    sb = get_client()
    graph_data = await load_graph_data(sb)
    halte = sb.table("halte").select("halte_id, nama, lat, lng").execute().data
    shapes = (
        sb.table("shapes")
        .select("*")
        .order("koridor_id")
        .order("urutan")
        .execute()
        .data
    )
    ctx = load_simulation_context(
        sb,
        halte_rows=halte,
        segmen=graph_data["segmen"],
        shapes_rows=shapes,
        allowed_halte_ids=set(graph_data["halte_to_koridor"]),
    )
    sim_time = 8 * 3600
    r = run_bus_level_monte_carlo(
        ctx,
        ctx.jadwal,
        koridor_id=3,
        halte_naik="G00161",
        sim_time=sim_time,
        replications=500,
        master_seed="live-bus-mc",
    )
    for key in (
        "koridor_id",
        "halte_naik",
        "eligible_count",
        "bus_change_rate",
        "tie_rate",
        "mean_density_delta",
        "median_density_delta",
        "mean_extra_wait_menit",
    ):
        print(f"{key}: {r[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
