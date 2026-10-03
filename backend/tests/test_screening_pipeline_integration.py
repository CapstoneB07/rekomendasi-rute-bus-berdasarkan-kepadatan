"""Integration test: full screening → sensitivity-plan → summary chain, offline.

This simulates the live-data pipeline with a synthetic two-corridor graph so
the whole flow can be verified without Supabase:

    build_screening_pairs -> classify_od_pair -> build_sensitivity_requests
    -> (simulated MC result) -> extract_summary_row
"""

from services.scenario_classifier import (
    build_screening_pairs,
    classify_od_pair,
)
from services.sensitivity_plan import (
    build_sensitivity_requests,
    extract_summary_row,
)


def _two_corridor_graph_data() -> dict:
    return {
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
        "kepadatan_bus": [
            {"bus_id": "B-K1-01", "koridor_id": 1, "jam": 8,
             "hari_tipe": "weekday", "kepadatan": 0.9},
            {"bus_id": "B-K2-01", "koridor_id": 2, "jam": 8,
             "hari_tipe": "weekday", "kepadatan": 0.2},
        ],
        "halte": {
            "A": {"halte_id": "A", "nama": "A", "lat": 0.0, "lng": 0.0},
            "B": {"halte_id": "B", "nama": "B", "lat": 0.0, "lng": 0.002},
            "C": {"halte_id": "C", "nama": "C", "lat": 0.0, "lng": 0.004},
            "D": {"halte_id": "D", "nama": "D", "lat": 0.001, "lng": 0.002},
        },
        "koridor_halte": [
            {"koridor_id": 1, "halte_id": "A"},
            {"koridor_id": 1, "halte_id": "B"},
            {"koridor_id": 1, "halte_id": "C"},
            {"koridor_id": 2, "halte_id": "A"},
            {"koridor_id": 2, "halte_id": "D"},
            {"koridor_id": 2, "halte_id": "C"},
        ],
        "koridor": {
            1: {"koridor_id": 1, "nama_pendek": "K1", "nama_panjang": "Koridor 1"},
            2: {"koridor_id": 2, "nama_pendek": "K2", "nama_panjang": "Koridor 2"},
        },
        "halte_to_koridor": {
            "A": {1, 2}, "B": {1}, "C": {1, 2}, "D": {2},
        },
    }


def test_offline_screening_to_summary_pipeline():
    graph_data = _two_corridor_graph_data()

    # 1. Screening pairs: must discover the A->C pair.
    pairs = build_screening_pairs(graph_data)
    assert {"origin": "A", "destination": "C"} in pairs

    # 2. Classify: must be severe conflict (C).
    row = classify_od_pair(graph_data, "A", "C", jam=8, hari_tipe="weekday")
    assert row["scenario_type"] == "C"
    assert row["candidate_count"] >= 2
    assert row["density_delta"] == 0.7

    # 3. Sensitivity plan: 1 selected OD -> 4 weight sweeps, each carrying weights.
    plans = build_sensitivity_requests([row], replications=25)
    assert len(plans) == 4
    assert {plan["weight_label"] for plan in plans} == {"w020", "w040", "w060", "w080"}
    assert all(plan["request_body"]["replications"] == 25 for plan in plans)
    assert all("weights" in plan["request_body"] for plan in plans)

    # 4. Summary extraction from a simulated MC response.
    simulated_result = {
        "routing_sensitivity": {
            "scenarios": [{
                "replications": [{"replication_index": i} for i in range(25)],
                "paired_comparison": {
                    "route_change_rate": 0.64,
                    "mean_density_delta": 0.42,
                    "median_density_delta": 0.40,
                    "p05_density_delta": 0.15,
                    "p95_density_delta": 0.62,
                    "mean_extra_time_seconds": 300.0,
                    "improvement_rate": 0.60,
                },
                "baseline_density_mean": 0.90,
                "recommended_density_mean": 0.48,
            }]
        }
    }
    summary = extract_summary_row(plans[0], simulated_result)
    assert summary["divergence_rate"] == 0.64
    assert summary["mean_extra_time_minutes"] == 5.0
    assert summary["replications"] == 25
