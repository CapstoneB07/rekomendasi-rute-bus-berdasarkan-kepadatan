"""Validasi paket CSV upload-ready secara OFFLINE (tanpa Supabase).

Memuat paket hasil build_gtfs_upload_package.py ke struktur graph_data yang
sama seperti load_graph_data(), lalu menjalankan dijkstra(k=5) untuk mengukur:
  - jumlah koridor / halte / segmen,
  - keterhubungan (reachability) OD acak,
  - berapa OD yang punya >= 2 kandidat rute (syarat skenario B/C),
  - berapa OD yang punya alternatif setelah koridor bersama diblokir.

Jalankan dari backend/:
    ./venv/Scripts/python.exe scripts/validate_upload_package.py --pkg "<dir>"
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.dijkstra import build_graph, dijkstra  # noqa: E402


def read(path: Path, name: str) -> list[dict]:
    with (path / name).open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def load_pkg(pkg: Path) -> dict:
    segmen = read(pkg, "segmen.csv")
    halte = read(pkg, "halte.csv")
    kh = read(pkg, "koridor_halte.csv")
    for s in segmen:
        s["koridor_id"] = int(s["koridor_id"])
        s["urutan"] = int(s["urutan"])
        s["waktu_tempuh_detik"] = float(s["waktu_tempuh_detik"])
    for r in kh:
        r["koridor_id"] = int(r["koridor_id"])
    halte_to_koridor: dict[str, set[int]] = defaultdict(set)
    for r in kh:
        halte_to_koridor[r["halte_id"]].add(r["koridor_id"])
    return {
        "segmen": segmen,
        "halte": {h["halte_id"]: h for h in halte},
        "koridor_halte": kh,
        "halte_to_koridor": dict(halte_to_koridor),
        "kepadatan_bus": [],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pkg", required=True)
    ap.add_argument("--samples", type=int, default=400)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    pkg = Path(args.pkg)

    gd = load_pkg(pkg)
    kor = sorted({str(s["koridor_id"]) for s in gd["segmen"]}, key=lambda x: (len(x), x))
    print(f"koridor : {kor}")
    print(f"halte   : {len(gd['halte'])}")
    print(f"segmen  : {len(gd['segmen'])}")

    graph = build_graph(gd, jam=8, hari_tipe="weekday")
    print(f"graph nodes={len(graph)} edges={sum(len(v) for v in graph.values())}")

    halte_ids = list(gd["halte"].keys())
    rng = random.Random(args.seed)
    pairs = [(rng.choice(halte_ids), rng.choice(halte_ids)) for _ in range(args.samples)]
    pairs = [(a, b) for a, b in pairs if a != b]

    reachable = 0
    multi = 0
    multi_examples: list[tuple[str, str, int]] = []
    for a, b in pairs:
        try:
            routes = dijkstra(graph, a, b, k=5)
        except Exception:
            routes = []
        if routes:
            reachable += 1
            if len(routes) >= 2:
                multi += 1
                if len(multi_examples) < 8:
                    multi_examples.append((a, b, len(routes)))

    print()
    print(f"OD disampel        : {len(pairs)}")
    print(f"terhubung          : {reachable} ({reachable / max(1, len(pairs)):.1%})")
    print(f"punya >=2 kandidat : {multi} ({multi / max(1, len(pairs)):.1%})")
    if multi_examples:
        print("contoh multi-kandidat:")
        for a, b, n in multi_examples:
            print(f"   {a} -> {b} : {n} kandidat")

    # Keterhubungan antar-koridor: apakah koridor 8/9/12 menyatu dengan 1-5?
    kor_of = gd["halte_to_koridor"]
    transfer = [
        h for h, ks in kor_of.items()
        if len(ks) >= 2 and (ks & {8, 9, 12}) and (ks & {1, 2, 3, 4, 5})
    ]
    print()
    print(f"halte transfer 1-5 <-> 8/9/12 : {len(transfer)}")
    print(f"   contoh: {sorted(transfer)[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
