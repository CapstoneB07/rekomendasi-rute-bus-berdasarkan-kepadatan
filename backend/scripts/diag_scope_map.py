"""Diagnostik: peta koridor tiap baris catalog vs scope simulasi.

Jawab pertanyaan: berapa baris catalog yang origin/tujuannya berada di luar
scope simulasi (SCOPED_KORIDOR), sehingga tidak punya kandidat bus sama
sekali (hanya fallback kepadatan edge).

Jalankan dari backend/:
    ./venv/Scripts/python.exe scripts/diag_scope_map.py
"""

import asyncio
import csv
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.config import SCOPED_KORIDOR, describe  # noqa: E402
from services.dijkstra import load_graph_data  # noqa: E402
from services.supabase_client import get_client  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "results" / "scenario_catalog.csv"


async def main() -> int:
    print(f"scope: {describe()} -> {sorted(SCOPED_KORIDOR)}")
    graph_data = await load_graph_data(get_client())
    halte_to_koridor: dict = graph_data["halte_to_koridor"]

    def koridor_of(hid: str) -> str:
        kids = halte_to_koridor.get(hid, set())
        if not kids:
            return "?"
        return ",".join(sorted(str(k) for k in kids))

    rows = list(csv.DictReader(CATALOG.open(newline="", encoding="utf-8")))
    seen: dict[tuple, dict] = {}
    for row in rows:
        key = (row["origin"], row["destination"])
        if key in seen:
            continue
        ok = koridor_of(row["origin"])
        dk = koridor_of(row["destination"])
        in_scope = all(
            k in SCOPED_KORIDOR for k in (ok.split(",") + dk.split(",")) if k != "?"
        )
        seen[key] = {
            "origin": row["origin"],
            "destination": row["destination"],
            "o_koridor": ok,
            "d_koridor": dk,
            "in_scope": in_scope,
        }

    pairs = list(seen.values())
    n_out = sum(1 for p in pairs if not p["in_scope"])
    print(f"\npairs: {len(pairs)}, out-of-scope: {n_out}, in-scope: {len(pairs) - n_out}")
    print(f"rows (x2 windows): out-of-scope ~{n_out * 2}, in-scope ~{(len(pairs) - n_out) * 2}")

    print("\nkoridor pasangan (origin->dest), out-of-scope only:")
    out_pairs = [p for p in pairs if not p["in_scope"]]
    for p in sorted(out_pairs, key=lambda x: (x["o_koridor"], x["d_koridor"])):
        print(f"  {p['origin']}({p['o_koridor']}) -> {p['destination']}({p['d_koridor']})")

    print("\ncounts by corridor combo (all pairs):")
    combo = Counter((p["o_koridor"], p["d_koridor"]) for p in pairs)
    for k, v in sorted(combo.items()):
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
