"""Screen OD pairs dari Supabase, klasifikasikan A/B/C/D, simpan CSV.

Jalankan dari backend/:
    ./venv/Scripts/python.exe scripts/screen_scenarios.py
"""

import asyncio
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.dijkstra import load_graph_data
from services.scenario_classifier import (
    build_screening_pairs,
    classify_od_pair,
    write_catalog,
)
from services.supabase_client import get_client

OUTPUT = Path(__file__).resolve().parents[2] / "results" / "scenario_catalog.csv"
TIME_WINDOWS = [(8, "weekday"), (14, "weekday")]


async def main() -> int:
    try:
        graph_data = await load_graph_data(get_client())
    except Exception as exc:
        print(f"FATAL: Supabase tidak terjangkau: {exc!r}", file=sys.stderr)
        print("Pastikan backend/.env berisi SUPABASE_URL dan SUPABASE_SERVICE_ROLE_KEY "
              "serta koneksi internet tersedia.", file=sys.stderr)
        return 2

    pairs = build_screening_pairs(graph_data)
    rows: list[dict] = []
    seen: set[tuple] = set()
    for jam, hari_tipe in TIME_WINDOWS:
        for pair in pairs:
            key = (pair["origin"], pair["destination"], jam)
            if key in seen:
                continue
            seen.add(key)
            try:
                row = classify_od_pair(
                    graph_data,
                    pair["origin"],
                    pair["destination"],
                    jam=jam,
                    hari_tipe=hari_tipe,
                )
            except Exception as exc:
                print(f"SKIP {pair['origin']}->{pair['destination']} ({exc!r})", file=sys.stderr)
                continue
            rows.append(row)
            print(
                f"{row['time_period']} {row['origin']}->{row['destination']} "
                f"type={row['scenario_type']} candidates={row['candidate_count']} "
                f"delta={row.get('density_delta', '')}"
            )

    write_catalog(rows, OUTPUT)
    counts = Counter(row.get("scenario_type") for row in rows)
    print(f"\nSaved: {OUTPUT}")
    print(f"Type counts: {dict(counts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
