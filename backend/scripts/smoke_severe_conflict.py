"""Smoke test: konflik parah deterministik tanpa Supabase/server.

Jalankan dari backend/:
    ./venv/Scripts/python.exe scripts/smoke_severe_conflict.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.dijkstra import build_graph, dijkstra, format_rute

GRAPH_DATA = {
    "segmen": [
        {"segmen_id": "K1_A_B", "koridor_id": 1, "halte_asal": "A",
         "halte_tujuan": "B", "urutan": 1, "waktu_tempuh_detik": 120},
        {"segmen_id": "K1_B_C", "koridor_id": 1, "halte_asal": "B",
         "halte_tujuan": "C", "urutan": 2, "waktu_tempuh_detik": 120},
        {"segmen_id": "K2_A_D", "koridor_id": 2, "halte_asal": "A",
         "halte_tujuan": "D", "urutan": 1, "waktu_tempuh_detik": 180},
        {"segmen_id": "K2_D_C", "koridor_id": 2, "halte_asal": "D",
         "halte_tujuan": "C", "urutan": 2, "waktu_tempuh_detik": 180},
    ],
    "kepadatan_bus": [],
    "halte": {
        "A": {"halte_id": "A", "nama": "A", "lat": 0.0, "lng": 0.0},
        "B": {"halte_id": "B", "nama": "B", "lat": 0.0, "lng": 0.002},
        "C": {"halte_id": "C", "nama": "C", "lat": 0.0, "lng": 0.004},
        "D": {"halte_id": "D", "nama": "D", "lat": 0.001, "lng": 0.002},
    },
    "koridor_halte": [],
    "koridor": {
        1: {"koridor_id": 1, "nama_pendek": "K1", "nama_panjang": "Koridor 1"},
        2: {"koridor_id": 2, "nama_pendek": "K2", "nama_panjang": "Koridor 2"},
    },
    "halte_to_koridor": {
        "A": {1, 2}, "B": {1}, "C": {1, 2}, "D": {2},
    },
}

SEGMENT_CROWDING = {
    "K1_A_B": 0.90,
    "K1_B_C": 0.90,
    "K2_A_D": 0.20,
    "K2_D_C": 0.20,
}


def _path_text(r):
    return " -> ".join([r["path"][0]["asal"]] + [e["tujuan"] for e in r["path"]])


def main() -> None:
    graph = build_graph(
        GRAPH_DATA,
        jam=8,
        hari_tipe="weekday",
        segment_crowding=SEGMENT_CROWDING,
    )

    baseline = dijkstra(graph, "A", "C", k=1)[0]
    routes = dijkstra(graph, "A", "C", k=3)

    print(f"baseline k=1 : {_path_text(baseline)} "
          f"density={baseline['rata_kepadatan']:.3f} "
          f"primary={baseline['primary_score']:.4f}")
    print(f"candidates   : {len(routes)}")
    for i, r in enumerate(routes, 1):
        print(f"  {i}: {_path_text(r)} "
              f"density={r['rata_kepadatan']:.3f} "
              f"density_norm={r['density_norm']:.3f} "
              f"primary={r['primary_score']:.4f}")
    formatted_top = format_rute(routes[0], GRAPH_DATA)
    print(f"top formatted: density_norm={formatted_top['ranking_phase_2']['density_norm']} "
          f"primary={formatted_top['primary_score']}")

    # Re-ranking fase 2: urutkan berdasarkan kategori kepadatan lalu primary.
    # Ini adalah perilaku routers/rute.py dan services/monte_carlo.py via rerank_routes.
    from services.bus_selector import rerank_routes
    reranked = rerank_routes(routes)
    top = reranked[0]
    print(f"final reranked: {_path_text(top)} density={top['rata_kepadatan']:.3f} "
          f"density_norm={top['density_norm']:.3f} primary={top['primary_score']:.4f}")
    if top["rata_kepadatan"] != min(r["rata_kepadatan"] for r in routes):
        raise SystemExit(
            "FAIL: re-ranking did not promote the least crowded route"
        )
    if len(routes) < 2:
        raise SystemExit(
            "FAIL: candidate generation produced fewer than 2 routes"
        )
    print("OK: >=2 candidates and least-crowded route wins re-ranking")


if __name__ == "__main__":
    main()
