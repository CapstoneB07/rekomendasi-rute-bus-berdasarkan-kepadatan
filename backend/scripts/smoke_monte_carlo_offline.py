"""Smoke test Monte Carlo algorithm offline (tanpa Supabase/server).

Jalankan dari backend/:
    ./venv/Scripts/python.exe scripts/smoke_monte_carlo_offline.py

Membangun SimulationContext + graph_data sintetis (konflik parah K1 padat vs
K2 sepi), lalu memanggil run_monte_carlo_experiment() langsung — jalur yang
sama persis dengan endpoint POST /api/rute/monte-carlo.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.dijkstra import build_graph
from services.gtfs_simulation import SimulationContext
from services.monte_carlo import run_monte_carlo_experiment


def _stop(halte_id: str, koridor_id: int, tiba: int, berangkat: int | None = None) -> dict:
    return {
        "halte_id": halte_id,
        "koridor_id": koridor_id,
        "waktu_tiba_detik": tiba,
        "waktu_berangkat_detik": berangkat if berangkat is not None else tiba,
    }


def _instance(tid: str, koridor_id: int, stops: list[dict], segment_ids: list[str]) -> dict:
    departure_time = stops[0]["waktu_berangkat_detik"]
    return {
        "trip_instance_id": tid,
        "bus_id": tid,
        "trip_id": tid,
        "koridor_id": koridor_id,
        "koridor_key": str(koridor_id),
        "direction_id": "0",
        "departure_time": departure_time,
        "first_stop_departure_time": departure_time,
        "last_stop_arrival_time": stops[-1]["waktu_tiba_detik"],
        "stops": stops,
        "segment_ids": segment_ids,
    }


def _build_context() -> SimulationContext:
    route_1_stops = [
        _stop("A", 1, 8 * 3600, 8 * 3600),
        _stop("B", 1, 8 * 3600 + 300),
        _stop("C", 1, 8 * 3600 + 600),
    ]
    route_2_stops = [
        _stop("A", 2, 8 * 3600, 8 * 3600),
        _stop("D", 2, 8 * 3600 + 300),
        _stop("C", 2, 8 * 3600 + 600),
    ]
    instances = [
        _instance("T1", 1, route_1_stops, ["S1", "S2"]),
        _instance("T2", 2, route_2_stops, ["S3", "S4"]),
    ]
    return SimulationContext(
        instances=instances,
        jadwal={"T1": route_1_stops, "T2": route_2_stops},
        trip_supply_per_koridor={"1": 1, "2": 1},
        daily_mean_load_factor={("2026-05-01", "1"): 0.9, ("2026-05-01", "2"): 0.2},
        latest_date="2026-05-01",
        latest_date_per_koridor={"1": "2026-05-01", "2": "2026-05-01"},
        recent_dates_per_koridor={"1": ["2026-05-01"], "2": ["2026-05-01"]},
        ridership_by_date_koridor={
            ("2026-05-01", "1"): 72.0,
            ("2026-05-01", "2"): 16.0,
        },
        segmen_by_id={
            "S1": {"segmen_id": "S1"},
            "S2": {"segmen_id": "S2"},
            "S3": {"segmen_id": "S3"},
            "S4": {"segmen_id": "S4"},
        },
        fallback_jadwal={},
    )


def _build_graph_data() -> dict:
    return {
        "segmen": [
            {"segmen_id": "S1", "koridor_id": 1, "halte_asal": "A", "halte_tujuan": "B", "waktu_tempuh_detik": 300},
            {"segmen_id": "S2", "koridor_id": 1, "halte_asal": "B", "halte_tujuan": "C", "waktu_tempuh_detik": 300},
            {"segmen_id": "S3", "koridor_id": 2, "halte_asal": "A", "halte_tujuan": "D", "waktu_tempuh_detik": 300},
            {"segmen_id": "S4", "koridor_id": 2, "halte_asal": "D", "halte_tujuan": "C", "waktu_tempuh_detik": 300},
        ],
        "kepadatan_bus": [],
        "halte": {
            "A": {"halte_id": "A", "nama": "A", "lat": 0.0, "lng": 0.0},
            "B": {"halte_id": "B", "nama": "B", "lat": 0.0, "lng": 0.001},
            "C": {"halte_id": "C", "nama": "C", "lat": 0.0, "lng": 0.002},
            "D": {"halte_id": "D", "nama": "D", "lat": 0.001, "lng": 0.001},
        },
        "koridor_halte": [],
        "koridor": {
            1: {"koridor_id": 1, "nama_pendek": "K1", "nama_panjang": "Koridor 1"},
            2: {"koridor_id": 2, "nama_pendek": "K2", "nama_panjang": "Koridor 2"},
        },
        "halte_to_koridor": {"A": {1, 2}, "B": {1}, "C": {1, 2}, "D": {2}},
    }


def main() -> None:
    ctx = _build_context()
    graph_data = _build_graph_data()
    # Pastikan graph import build_graph tetap jalan (sanity).
    graph = build_graph(graph_data, jam=8, hari_tipe="weekday")
    print(f"graph nodes: {len(graph)}")

    print("Running run_monte_carlo_experiment (offline, replications=10)...")
    result = run_monte_carlo_experiment(
        ctx,
        graph_data,
        scenarios=[{"name": "smoke-conflict", "halte_asal": "A", "halte_tujuan": "C"}],
        replications=10,
        master_seed=12345,
        tanggal="2026-05-01",
        jam=8,
        hari_tipe="weekday",
        sim_time=8 * 3600,
    )

    load = result["load_factor"]
    print(f"load_factor.replication_count = {load['replication_count']}")
    print(f"load_factor.master_seed      = {load['master_seed']}")

    routing = result["routing_sensitivity"]
    scenario = routing["scenarios"][0]
    print(f"scenario                    = {scenario['name']}")
    print(f"stability_rate              = {scenario['top_route_stability_rate']}")
    print(f"unique_top_route_count      = {scenario['unique_top_route_count']}")
    pc = scenario["paired_comparison"]
    print(f"paired_comparison:")
    for key in ["improvement_rate", "route_change_rate", "tie_rate",
                "mean_density_delta", "median_density_delta",
                "mean_extra_time_seconds"]:
        print(f"  {key:24} = {pc.get(key)}")


if __name__ == "__main__":
    main()
