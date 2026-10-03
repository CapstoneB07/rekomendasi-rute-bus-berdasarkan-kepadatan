"""Evaluasi metrik sukses skenario sistem (target 50%) atas seluruh catalog.

Menjalankan pipeline produksi (rute.py) per baris results/scenario_catalog.csv
dan menghitung win rate V1 (headline) dan V2 (konservatif). Lihat
services/success_metric.py untuk definisi lengkap.

Jalankan dari backend/:
    ./venv/Scripts/python.exe scripts/eval_success_rate.py --limit 3
    ./venv/Scripts/python.exe scripts/eval_success_rate.py
Output: results/success_rate_eval.csv + results/success_rate_summary.json
Butuh Supabase live; gagal keras (exit 2) bila tidak terjangkau.
"""

import argparse
import asyncio
import csv
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.config import (  # noqa: E402
    BUS_SCORE_DENSITY_WEIGHT,
    MAX_ETA_MENIT,
    MAX_EXTRA_WAIT_MENIT,
    describe,
)
from services.dijkstra import load_graph_data  # noqa: E402
from services.gtfs_simulation import load_simulation_context  # noqa: E402
from services.success_metric import (  # noqa: E402
    evaluate_scenario_success,
    summarize_success,
)
from services.supabase_client import get_client  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "results" / "scenario_catalog.csv"
OUTPUT = ROOT / "results" / "success_rate_eval.csv"
SUMMARY_OUTPUT = ROOT / "results" / "success_rate_summary.json"

FIELDNAMES = [
    "scenario_type", "origin", "destination", "time_period", "jam",
    "candidate_count", "blocks", "blocks_without_candidates",
    "max_bus_candidates", "blocks_with_multiple_buses",
    "d_base_v1", "d_base_v2", "d_rec", "delta_v1", "delta_v2",
    "win_v1", "win_v2", "route_changed", "mean_extra_wait_menit",
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="batasi jumlah baris (0 = semua)")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if not CATALOG.exists():
        print(f"FATAL: {CATALOG} tidak ada; jalankan scripts/screen_scenarios.py dulu.",
              file=sys.stderr)
        return 2

    print(
        f"CONFIG scope={describe()} max_extra_wait={MAX_EXTRA_WAIT_MENIT} "
        f"max_eta={MAX_ETA_MENIT} density_weight={BUS_SCORE_DENSITY_WEIGHT}"
    )

    try:
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
    except Exception as exc:
        print(f"FATAL: Supabase tidak terjangkau: {exc!r}", file=sys.stderr)
        return 2

    with CATALOG.open(newline="", encoding="utf-8") as stream:
        catalog = list(csv.DictReader(stream))
    if args.limit:
        catalog = catalog[: args.limit]

    rows: list[dict] = []
    for index, entry in enumerate(catalog, 1):
        jam = int(str(entry.get("time_period", "08h00")).split("h")[0])
        origin, destination = entry["origin"], entry["destination"]
        if not args.quiet:
            print(f"[{index}/{len(catalog)}] {entry.get('time_period')} {origin}->{destination}")
        try:
            hasil = evaluate_scenario_success(
                ctx, graph_data, origin, destination,
                jam=jam, hari_tipe="weekday", sim_time=jam * 3600,
            )
        except Exception as exc:
            print(f"SKIP {origin}->{destination} ({exc!r})", file=sys.stderr)
            continue
        hasil["scenario_type"] = entry.get("scenario_type", "")
        hasil["time_period"] = entry.get("time_period", f"{jam:02d}h00")
        hasil["jam"] = jam
        rows.append(hasil)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in FIELDNAMES})

    summary = summarize_success(rows)
    SUMMARY_OUTPUT.write_text(json.dumps(summary, indent=2, ensure_ascii=True), encoding="utf-8")
    print(f"Saved: {OUTPUT} ({len(rows)} baris)")
    print(f"Saved: {SUMMARY_OUTPUT}")
    print(
        f"SUMMARY n={summary['n']} win_rate_v1={summary['win_rate_v1']:.4f} "
        f"win_rate_v2={summary['win_rate_v2']:.4f} "
        f"mean_extra_wait={summary['mean_extra_wait_menit']:.3f} "
        f"mean_delta_v1={summary['mean_delta_v1']:.4f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
