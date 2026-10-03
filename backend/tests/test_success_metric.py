"""Test metrik sukses skenario (services/success_metric.py)."""

import pytest

import services.success_metric as sm
from services.gtfs_simulation import SimulationContext


def _stop(halte_id, koridor_id, tiba, berangkat=None):
    return {
        "halte_id": halte_id,
        "koridor_id": koridor_id,
        "waktu_tiba_detik": tiba,
        "waktu_berangkat_detik": berangkat if berangkat is not None else tiba,
    }


def _context(jadwal):
    return SimulationContext(
        instances=[],
        jadwal=jadwal,
        trip_supply_per_koridor={},
        daily_mean_load_factor={},
        latest_date=None,
        latest_date_per_koridor={},
        recent_dates_per_koridor={},
        ridership_by_date_koridor={},
        segmen_by_id={},
        fallback_jadwal={},
    )


def _two_corridor_graph():
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


def _single_corridor_graph():
    return {
        "segmen": [
            {"segmen_id": "S1", "koridor_id": 1, "halte_asal": "A", "halte_tujuan": "B", "waktu_tempuh_detik": 300},
            {"segmen_id": "S2", "koridor_id": 1, "halte_asal": "B", "halte_tujuan": "C", "waktu_tempuh_detik": 300},
        ],
        "kepadatan_bus": [],
        "halte": {
            "A": {"halte_id": "A", "nama": "A", "lat": 0.0, "lng": 0.0},
            "B": {"halte_id": "B", "nama": "B", "lat": 0.0, "lng": 0.001},
            "C": {"halte_id": "C", "nama": "C", "lat": 0.0, "lng": 0.002},
        },
        "koridor_halte": [],
        "koridor": {1: {"koridor_id": 1, "nama_pendek": "K1", "nama_panjang": "Koridor 1"}},
        "halte_to_koridor": {"A": {1}, "B": {1}, "C": {1}},
    }


def _fake_snapshot(segment_crowding, daily_mean, realtime):
    def _snapshot(ctx, tanggal=None, sim_time=None, request_seed_parts=()):
        return {
            "master_seed": "test-seed",
            "replication": {},
            "segment_crowding": segment_crowding,
            "daily_mean_by_koridor": daily_mean,
            "realtime_kepadatan": realtime,
        }

    return _snapshot


def test_route_level_win_multi_corridor(monkeypatch):
    base = 8 * 3600
    jadwal = {
        "T1": [_stop("A", 1, base), _stop("B", 1, base + 300), _stop("C", 1, base + 600)],
        "T2": [_stop("A", 2, base), _stop("D", 2, base + 300), _stop("C", 2, base + 600)],
    }
    ctx = _context(jadwal)
    monkeypatch.setattr(
        sm,
        "build_recommendation_crowding_snapshot",
        _fake_snapshot(
            {"S1": 0.9, "S2": 0.9, "S3": 0.2, "S4": 0.2},
            {"1": 0.9, "2": 0.2},
            {"T1": 0.9, "T2": 0.2},
        ),
    )

    hasil = sm.evaluate_scenario_success(
        ctx, _two_corridor_graph(), "A", "C", jam=8, hari_tipe="weekday", sim_time=base
    )

    assert hasil["win_v1"] is True
    assert hasil["route_changed"] is True
    assert hasil["d_rec"] == pytest.approx(0.2, abs=0.05)
    assert hasil["d_base_v1"] == pytest.approx(0.9, abs=0.05)


def test_bus_layer_win_single_route(monkeypatch):
    base = 8 * 3600
    jadwal = {
        "T1": [_stop("A", 1, base), _stop("B", 1, base + 300), _stop("C", 1, base + 600)],
        "T1b": [_stop("A", 1, base + 600), _stop("B", 1, base + 900), _stop("C", 1, base + 1200)],
    }
    ctx = _context(jadwal)
    monkeypatch.setattr(
        sm,
        "build_recommendation_crowding_snapshot",
        _fake_snapshot({"S1": 0.9, "S2": 0.9}, {"1": 0.9}, {"T1": 0.9, "T1b": 0.2}),
    )

    hasil = sm.evaluate_scenario_success(
        ctx, _single_corridor_graph(), "A", "C", jam=8, hari_tipe="weekday", sim_time=base
    )

    # Rute tidak berubah, tapi bus rekomendasi lebih sepi dari bus tercepat.
    assert hasil["route_changed"] is False
    assert hasil["win_v1"] is True
    assert hasil["win_v2"] is False  # V2 konservatif: baseline density-aware -> tie
    assert hasil["d_rec"] == pytest.approx(0.2, abs=0.05)
    assert hasil["d_base_v1"] == pytest.approx(0.9, abs=0.05)
    assert hasil["mean_extra_wait_menit"] == pytest.approx(10.0, abs=0.5)


def test_no_win_when_earliest_bus_already_empty(monkeypatch):
    base = 8 * 3600
    jadwal = {
        "T1": [_stop("A", 1, base), _stop("B", 1, base + 300), _stop("C", 1, base + 600)],
        "T1b": [_stop("A", 1, base + 600), _stop("B", 1, base + 900), _stop("C", 1, base + 1200)],
    }
    ctx = _context(jadwal)
    monkeypatch.setattr(
        sm,
        "build_recommendation_crowding_snapshot",
        _fake_snapshot({"S1": 0.2, "S2": 0.2}, {"1": 0.2}, {"T1": 0.2, "T1b": 0.25}),
    )

    hasil = sm.evaluate_scenario_success(
        ctx, _single_corridor_graph(), "A", "C", jam=8, hari_tipe="weekday", sim_time=base
    )

    # Bus tercepat sudah sepi (<= SAFE_NEXT_BUS_DENSITY_THRESHOLD) -> tidak ada
    # yang bisa diperbaiki -> tie, bukan kemenangan.
    assert hasil["win_v1"] is False
    assert hasil["win_v2"] is False
    assert hasil["d_rec"] == pytest.approx(0.2, abs=0.05)


def test_summarize_success_rates():
    rows = [
        {"win_v1": True, "win_v2": True, "delta_v1": 0.4, "mean_extra_wait_menit": 5.0},
        {"win_v1": True, "win_v2": False, "delta_v1": 0.2, "mean_extra_wait_menit": 10.0},
        {"win_v1": False, "win_v2": False, "delta_v1": -0.1, "mean_extra_wait_menit": 0.0},
        {"win_v1": False, "win_v2": False, "delta_v1": 0.0, "mean_extra_wait_menit": None},
    ]

    summary = sm.summarize_success(rows)

    assert summary["n"] == 4
    assert summary["wins_v1"] == 2
    assert summary["win_rate_v1"] == pytest.approx(0.5)
    assert summary["wins_v2"] == 1
    assert summary["win_rate_v2"] == pytest.approx(0.25)
    assert summary["mean_delta_v1"] == pytest.approx(0.125)
    assert summary["mean_extra_wait_menit"] == pytest.approx(5.0)
    assert summary["mean_extra_wait_wins_v1"] == pytest.approx(7.5)
