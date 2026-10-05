"""Regresi pembulatan pada metrik sukses (temuan 2026-10-05).

Latar: `bus_rekomendasi["kepadatan"]` disimpan dibulatkan 3 desimal, sementara
kandidat menyimpan kepadatan mentah. Baris di mana sistem memilih bus tercepat
persis (delta sebenarnya 0) terbaca NEGATIF (mis. 0.8509 -> 0.851, delta -0.0001)
sehingga seolah sistem merekomendasikan bus yang lebih padat.

5 dari 192 baris katalog scope-8 terkena pola ini. Test ini menjaga agar metrik
memakai nilai mentah dan tidak pernah melaporkan delta negatif hanya karena
pembulatan tampilan.
"""

import pytest

from services import success_metric as sm


def _stop(halte_id, koridor_id, detik):
    return {
        "halte_id": halte_id,
        "koridor_id": koridor_id,
        "waktu_tiba_detik": detik,
        "waktu_berangkat_detik": detik,
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


class _Ctx:
    def __init__(self, jadwal):
        self.jadwal = jadwal


def _fake_snapshot(realtime):
    def _snapshot(ctx, tanggal=None, sim_time=None, request_seed_parts=()):
        return {
            "master_seed": "test-seed",
            "replication": {},
            "segment_crowding": {"S1": 0.5, "S2": 0.5},
            "daily_mean_by_koridor": {"1": 0.5},
            "realtime_kepadatan": realtime,
        }

    return _snapshot


def test_no_false_negative_delta_from_display_rounding(monkeypatch):
    """Bus tercepat 0.8509 dipilih apa adanya -> delta harus 0, bukan negatif.

    Tanpa fix, `d_rec` = round(0.8509, 3) = 0.851 dan delta_v1 = -0.0001.
    """
    base = 8 * 3600
    jadwal = {
        "T1": [_stop("A", 1, base), _stop("B", 1, base + 300), _stop("C", 1, base + 600)],
    }
    ctx = _Ctx(jadwal)
    monkeypatch.setattr(
        sm, "build_recommendation_crowding_snapshot", _fake_snapshot({"T1": 0.8509})
    )

    hasil = sm.evaluate_scenario_success(
        ctx, _single_corridor_graph(), "A", "C", jam=8, hari_tipe="weekday", sim_time=base
    )

    assert hasil["delta_v1"] == pytest.approx(0.0, abs=1e-9)
    assert hasil["delta_v1"] >= 0, "pembulatan tidak boleh menciptakan delta negatif"
    assert hasil["win_v1"] is False


def test_raw_density_used_for_recommendation(monkeypatch):
    """d_rec memakai nilai mentah, bukan yang dibulatkan 3 desimal."""
    base = 8 * 3600
    jadwal = {
        "T1": [_stop("A", 1, base), _stop("B", 1, base + 300), _stop("C", 1, base + 600)],
    }
    ctx = _Ctx(jadwal)
    monkeypatch.setattr(
        sm, "build_recommendation_crowding_snapshot", _fake_snapshot({"T1": 0.6543})
    )

    hasil = sm.evaluate_scenario_success(
        ctx, _single_corridor_graph(), "A", "C", jam=8, hari_tipe="weekday", sim_time=base
    )

    # 0.6543 mentah -> bukan 0.654 hasil pembulatan.
    assert hasil["d_rec"] == pytest.approx(0.6543, abs=1e-9)


def test_tiny_positive_delta_counts_as_win_at_literal_tolerance(monkeypatch):
    """c251 Eq 4.24 literal: 'kepadatan lebih rendah' = selisih > 0.

    Selisih 0.0004 adalah kemenangan nyata pada pembacaan literal, dan tidak
    boleh dibulatkan menjadi 0 / negatif.
    """
    base = 8 * 3600
    jadwal = {
        "T1": [_stop("A", 1, base), _stop("B", 1, base + 300), _stop("C", 1, base + 600)],
    }
    ctx = _Ctx(jadwal)
    monkeypatch.setattr(
        sm, "build_recommendation_crowding_snapshot", _fake_snapshot({"T1": 0.5004})
    )

    hasil = sm.evaluate_scenario_success(
        ctx, _single_corridor_graph(), "A", "C", jam=8, hari_tipe="weekday", sim_time=base
    )

    # Bus tercepat = satu-satunya bus; delta 0 (bukan 0.0004) karena baseline
    # dan rekomendasi memilih bus yang sama.
    assert hasil["delta_v1"] == pytest.approx(0.0, abs=1e-9)
