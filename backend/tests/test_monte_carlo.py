import math
from types import SimpleNamespace

import pytest

from routers import rute as rute_router
from services.gtfs_simulation import SimulationContext
from services.monte_carlo import (
    MC_POISSON_SCALE_FACTOR,
    _scaled_poisson_draw,
    _segment_ids_from_signature,
    run_bus_level_monte_carlo,
    run_load_factor_monte_carlo,
    run_routing_sensitivity,
)


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


def _stop(halte_id: str, koridor_id: int, tiba: int, berangkat: int | None = None) -> dict:
    return {
        "halte_id": halte_id,
        "koridor_id": koridor_id,
        "waktu_tiba_detik": tiba,
        "waktu_berangkat_detik": berangkat if berangkat is not None else tiba,
    }


def _mc_context() -> SimulationContext:
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
        jadwal={
            "T1": route_1_stops,
            "T2": route_2_stops,
        },
        trip_supply_per_koridor={"1": 1, "2": 1},
        daily_mean_load_factor={("2026-05-01", "1"): 0.5, ("2026-05-01", "2"): 0.5},
        latest_date="2026-05-01",
        latest_date_per_koridor={"1": "2026-05-01", "2": "2026-05-01"},
        recent_dates_per_koridor={"1": ["2026-05-01"], "2": ["2026-05-01"]},
        ridership_by_date_koridor={("2026-05-01", "1"): 1000.0, ("2026-05-01", "2"): 1000.0},
        segmen_by_id={
            "S1": {"segmen_id": "S1"},
            "S2": {"segmen_id": "S2"},
            "S3": {"segmen_id": "S3"},
            "S4": {"segmen_id": "S4"},
        },
        fallback_jadwal={},
    )


def _graph_data() -> dict:
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


def test_load_factor_monte_carlo_is_reproducible_and_balances_totals():
    ctx = _mc_context()

    first = run_load_factor_monte_carlo(ctx, tanggal="2026-05-01", replications=6, master_seed=1234)
    second = run_load_factor_monte_carlo(ctx, tanggal="2026-05-01", replications=6, master_seed=1234)

    assert first["master_seed"] == second["master_seed"]
    assert first["sub_seeds"] == second["sub_seeds"]
    assert first["replications"] == second["replications"]

    for replication in first["replications"]:
        assert math.isclose(replication["allocated_passenger_total"], 2000.0, rel_tol=0, abs_tol=1e-9)
        assert math.isclose(replication["trip_load_factor_total"], sum(
            payload["trip_load_factor"] for payload in replication["trip_loads"].values()
        ), rel_tol=0, abs_tol=1e-12)

    assert set(first["trip_aggregates"]) == {"T1", "T2"}
    assert set(first["segment_aggregates"]) == {"S1", "S2", "S3", "S4"}
    assert "mean" in first["trip_aggregates"]["T1"]
    assert "std_dev" in first["segment_aggregates"]["S1"]
    assert "p05" in first["segment_aggregates"]["S1"]
    assert "p95" in first["segment_aggregates"]["S1"]


def test_poisson_draw_uses_configured_rate_scaling():
    raw_draw, scaled_draw = _scaled_poisson_draw(1234, 1.0)

    assert MC_POISSON_SCALE_FACTOR == 25
    assert raw_draw >= 0
    assert scaled_draw == raw_draw / MC_POISSON_SCALE_FACTOR


def test_routing_sensitivity_reports_stability_and_rank_correlation():
    ctx = _mc_context()
    graph_data = _graph_data()
    load_factor_experiment = {
        "replications": [
            {
                "replication_index": 0,
                "replication_seed": 111,
                "trip_loads": {
                    "T1": {"trip_load_factor": 0.20, "estimated_passengers": 16.0, "tanggal": "2026-05-01"},
                    "T2": {"trip_load_factor": 0.90, "estimated_passengers": 72.0, "tanggal": "2026-05-01"},
                },
                "segment_loads": {
                    "T1": {"S1": 0.20, "S2": 0.20},
                    "T2": {"S3": 0.90, "S4": 0.90},
                },
            },
            {
                "replication_index": 1,
                "replication_seed": 222,
                "trip_loads": {
                    "T1": {"trip_load_factor": 0.85, "estimated_passengers": 68.0, "tanggal": "2026-05-01"},
                    "T2": {"trip_load_factor": 0.25, "estimated_passengers": 20.0, "tanggal": "2026-05-01"},
                },
                "segment_loads": {
                    "T1": {"S1": 0.85, "S2": 0.85},
                    "T2": {"S3": 0.25, "S4": 0.25},
                },
            },
        ]
    }

    result = run_routing_sensitivity(
        ctx,
        graph_data,
        scenarios=[{"name": "same-corridor", "halte_asal": "A", "halte_tujuan": "C"}],
        load_factor_experiment=load_factor_experiment,
        jam=8,
        hari_tipe="weekday",
        sim_time=8 * 3600,
        tanggal="2026-05-01",
    )

    scenario = result["scenarios"][0]
    assert scenario["top_route_stability_rate"] == 0.5
    assert scenario["unique_top_route_count"] == 2
    assert scenario["top_route_mode_count"] == 1
    assert scenario["average_spearman_rho"] is not None
    assert scenario["average_kendall_tau"] is not None
    assert len(scenario["replications"]) == 2
    assert scenario["replications"][0]["top_route_signature"] != scenario["replications"][1]["top_route_signature"]
    assert scenario["segment_aggregates"]
    assert all(
        stats["count"] >= 1
        for stats in scenario["segment_aggregates"].values()
    )
    assert all(
        "active_segment_loads" in replication
        for replication in scenario["replications"]
    )
    assert all(
        replication["top_route_segment_weights"]
        for replication in scenario["replications"]
    )
    assert all(
        weight["source"] in {
            "boarding_trip_segment",
            "active_segment",
            "corridor_daily_mean",
            "kepadatan_bus_or_default",
        }
        for replication in scenario["replications"]
        for weight in replication["top_route_segment_weights"]
    )


def test_rekomendasi_uses_seeded_monte_carlo_snapshot(monkeypatch):
    ctx = _mc_context()
    graph_data = _graph_data()
    captured = {}

    def fake_snapshot(simulation_context, tanggal=None, sim_time=None, request_seed_parts=()):
        captured["simulation_context"] = simulation_context
        captured["tanggal"] = tanggal
        captured["sim_time"] = sim_time
        captured["request_seed_parts"] = request_seed_parts
        return {
            "master_seed": "seed-123",
            "replication": {},
            "segment_crowding": {"S1": 0.25, "S2": 0.25, "S3": 0.75, "S4": 0.75},
            "daily_mean_by_koridor": {"1": 0.25, "2": 0.75},
            "realtime_kepadatan": {"T1": 0.25, "T2": 0.75},
        }

    monkeypatch.setattr(rute_router, "build_recommendation_crowding_snapshot", fake_snapshot)
    monkeypatch.setattr(rute_router, "select_bus_per_segmen", lambda *args, **kwargs: None)

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                graph_data=graph_data,
                jadwal=ctx.jadwal,
                simulation_context=ctx,
            )
        )
    )

    result = rute_router.rekomendasi(
        rute_router.RuteRequest(
            halte_asal="A",
            halte_tujuan="C",
            jam=8,
            hari_tipe="weekday",
            sim_time=8 * 3600,
            tanggal="2026-05-01",
            simulation_run_id="run-1",
        ),
        request,
    )

    assert captured["request_seed_parts"] == ("A", "C", 8, "weekday", 8 * 3600, "run-1")
    assert captured["tanggal"] == "2026-05-01"
    assert captured["sim_time"] == 8 * 3600
    assert isinstance(result, list)
    assert result


def test_synthetic_reranking_selects_less_crowded_alternative_route():
    """Route via koridor 1 (T1) and koridor 2 (T2) tie on distance/time; koridor 1
    is far more crowded. Two-ranking must select koridor 2 instead of the k=1
    baseline, and the reported density must reflect the actually selected bus.
    """
    ctx = _mc_context()
    graph_data = _graph_data()
    load_factor_experiment = {
        "replications": [
            {
                "replication_index": 0,
                "replication_seed": 111,
                "trip_loads": {
                    "T1": {"trip_load_factor": 0.90, "estimated_passengers": 72.0, "tanggal": "2026-05-01"},
                    "T2": {"trip_load_factor": 0.20, "estimated_passengers": 16.0, "tanggal": "2026-05-01"},
                },
                "segment_loads": {
                    "T1": {"S1": 0.90, "S2": 0.90},
                    "T2": {"S3": 0.20, "S4": 0.20},
                },
            },
        ]
    }

    result = run_routing_sensitivity(
        ctx,
        graph_data,
        scenarios=[{"name": "crowded-vs-sparse", "halte_asal": "A", "halte_tujuan": "C"}],
        load_factor_experiment=load_factor_experiment,
        jam=8,
        hari_tipe="weekday",
        sim_time=8 * 3600,
        tanggal="2026-05-01",
    )

    replication = result["scenarios"][0]["replications"][0]
    baseline_segment_ids = _segment_ids_from_signature(replication["baseline_route_signature"])
    top_segment_ids = _segment_ids_from_signature(replication["top_route_signature"])

    # k=1 baseline ignores crowding and picks the shorter koridor 1 (via B) route.
    assert baseline_segment_ids == {"S1", "S2"}
    # Two-ranking must switch to the far less crowded koridor 2 (via D) route.
    assert top_segment_ids == {"S3", "S4"}
    assert replication["baseline_route_signature"] != replication["top_route_signature"]
    assert replication["recommended_density"] < replication["baseline_density"]
    assert replication["recommended_density"] == pytest.approx(0.20, abs=0.05)
    assert replication["baseline_density"] == pytest.approx(0.90, abs=0.05)


def test_paired_comparison_metrics_across_replications():
    """Replication 0: koridor 2 is far sparser, so two-ranking should win.
    Replication 1: koridor 1 is sparser, so baseline and two-ranking tie on the
    same route. Paired metrics must reflect this replication-by-replication,
    not just an aggregated mean that could hide the mixed outcome.
    """
    ctx = _mc_context()
    graph_data = _graph_data()
    load_factor_experiment = {
        "replications": [
            {
                "replication_index": 0,
                "replication_seed": 111,
                "trip_loads": {
                    "T1": {"trip_load_factor": 0.90, "estimated_passengers": 72.0, "tanggal": "2026-05-01"},
                    "T2": {"trip_load_factor": 0.20, "estimated_passengers": 16.0, "tanggal": "2026-05-01"},
                },
                "segment_loads": {
                    "T1": {"S1": 0.90, "S2": 0.90},
                    "T2": {"S3": 0.20, "S4": 0.20},
                },
            },
            {
                "replication_index": 1,
                "replication_seed": 222,
                "trip_loads": {
                    "T1": {"trip_load_factor": 0.30, "estimated_passengers": 24.0, "tanggal": "2026-05-01"},
                    "T2": {"trip_load_factor": 0.80, "estimated_passengers": 64.0, "tanggal": "2026-05-01"},
                },
                "segment_loads": {
                    "T1": {"S1": 0.30, "S2": 0.30},
                    "T2": {"S3": 0.80, "S4": 0.80},
                },
            },
        ]
    }

    result = run_routing_sensitivity(
        ctx,
        graph_data,
        scenarios=[{"name": "crowded-vs-sparse", "halte_asal": "A", "halte_tujuan": "C"}],
        load_factor_experiment=load_factor_experiment,
        jam=8,
        hari_tipe="weekday",
        sim_time=8 * 3600,
        tanggal="2026-05-01",
    )

    replications = result["scenarios"][0]["replications"]
    assert replications[0]["is_better"] is True
    assert replications[0]["route_changed"] is True
    assert replications[0]["density_delta"] == pytest.approx(0.70, abs=0.05)

    assert replications[1]["is_better"] is False
    assert replications[1]["route_changed"] is False
    assert replications[1]["density_delta"] == pytest.approx(0.0, abs=0.05)

    paired = result["scenarios"][0]["paired_comparison"]
    assert paired["improvement_rate"] == pytest.approx(0.5)
    assert paired["route_change_rate"] == pytest.approx(0.5)
    assert paired["tie_rate"] == pytest.approx(0.5)
    assert paired["mean_density_delta"] == pytest.approx(0.35, abs=0.05)


# ----------------------------------------------------------------------
# Bus-level Monte Carlo (Part B / masalah #6)
# ----------------------------------------------------------------------

def _bus_level_context() -> SimulationContext:
    """Satu koridor (1) dengan dua bus yang berangkat 10 menit terpisah."""
    base = 8 * 3600
    route_1a = [
        _stop("A", 1, base, base),
        _stop("B", 1, base + 300),
        _stop("C", 1, base + 600),
    ]
    route_1b = [
        _stop("A", 1, base + 600, base + 600),
        _stop("B", 1, base + 900),
        _stop("C", 1, base + 1200),
    ]
    instances = [
        _instance("T1", 1, route_1a, ["S1", "S2"]),
        _instance("T1b", 1, route_1b, ["S1", "S2"]),
    ]
    jadwal = {"T1": route_1a, "T1b": route_1b}
    return SimulationContext(
        instances=instances,
        jadwal=jadwal,
        trip_supply_per_koridor={"1": 2},
        daily_mean_load_factor={("2026-05-01", "1"): 0.5},
        latest_date="2026-05-01",
        latest_date_per_koridor={"1": "2026-05-01"},
        recent_dates_per_koridor={"1": ["2026-05-01"]},
        ridership_by_date_koridor={("2026-05-01", "1"): 1000.0},
        segmen_by_id={
            "S1": {"segmen_id": "S1"},
            "S2": {"segmen_id": "S2"},
        },
        fallback_jadwal={},
    )


def test_bus_level_monte_carlo_eligible_and_reproducible():
    ctx = _bus_level_context()
    sim_time = 8 * 3600

    result_a = run_bus_level_monte_carlo(
        ctx,
        ctx.jadwal,
        koridor_id=1,
        halte_naik="A",
        sim_time=sim_time,
        replications=50,
        master_seed="bus-level-seed",
    )
    result_b = run_bus_level_monte_carlo(
        ctx,
        ctx.jadwal,
        koridor_id=1,
        halte_naik="A",
        sim_time=sim_time,
        replications=50,
        master_seed="bus-level-seed",
    )

    assert result_a["replication_count"] == 50
    # Kedua bus selalu punya ETA valid & entri kepadatan -> semua replikasi eligible.
    assert result_a["eligible_count"] == 50

    # Deterministik untuk seed yang sama.
    assert result_a["mean_density_delta"] == result_b["mean_density_delta"]
    assert result_a["bus_change_rate"] == result_b["bus_change_rate"]

    # Rate selalu di [0, 1].
    assert 0.0 <= result_a["bus_change_rate"] <= 1.0
    assert 0.0 <= result_a["tie_rate"] <= 1.0


def test_bus_level_monte_carlo_reports_per_replication_fields():
    ctx = _bus_level_context()
    result = run_bus_level_monte_carlo(
        ctx,
        ctx.jadwal,
        koridor_id=1,
        halte_naik="A",
        sim_time=8 * 3600,
        replications=20,
        master_seed="bus-level-seed-2",
    )
    eligible = [r for r in result["replications"] if r.get("eligible")]
    assert len(eligible) == 20
    first = eligible[0]
    for key in (
        "baseline_bus_id",
        "recommended_bus_id",
        "baseline_density",
        "recommended_density",
        "density_delta",
        "extra_wait_menit",
    ):
        assert key in first