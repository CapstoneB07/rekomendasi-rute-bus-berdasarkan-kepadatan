from services.dijkstra import build_graph, dijkstra
from services.scenario_classifier import (
    BUS_CROWDED_THRESHOLD,
    BUS_EMPTY_THRESHOLD,
    classify_bus_level,
    classify_od_pair,
    classify_routes,
)


def _severe_conflict_graph_data() -> dict:
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
        "koridor_halte": [],
        "koridor": {
            1: {"koridor_id": 1, "nama_pendek": "K1", "nama_panjang": "Koridor 1"},
            2: {"koridor_id": 2, "nama_pendek": "K2", "nama_panjang": "Koridor 2"},
        },
        "halte_to_koridor": {
            "A": {1, 2}, "B": {1}, "C": {1, 2}, "D": {2},
        },
    }


def test_classify_routes_detects_severe_conflict():
    data = _severe_conflict_graph_data()
    graph = build_graph(data, jam=8, hari_tipe="weekday")
    routes = dijkstra(graph, "A", "C", k=3)

    result = classify_routes(routes)

    assert result["scenario_type"] == "C"
    assert result["unique_corridor_sequences"] == 2
    assert result["density_delta"] == 0.7


def test_classify_od_pair_adds_context_fields():
    data = _severe_conflict_graph_data()
    result = classify_od_pair(data, "A", "C", jam=8, hari_tipe="weekday")

    assert result["origin"] == "A"
    assert result["destination"] == "C"
    assert result["time_period"] == "08h00"
    assert result["candidate_count"] >= 2
    assert result["scenario_type"] == "C"


# ----------------------------------------------------------------------
# Part B (masalah #6): klasifikasi skenario level bus
# ----------------------------------------------------------------------

def test_classify_bus_level_conflict_awal_padat_lalu_sepi():
    """Bus tercepat padat (>=0.80), bus berikutnya sepi (<=0.35), gap < 0.50 -> B'."""
    candidates = [
        {"bus_id": "BUS-PADAT", "eta_menit": 2, "kepadatan": 0.80},
        {"bus_id": "BUS-SEPI", "eta_menit": 12, "kepadatan": 0.35},
    ]
    result = classify_bus_level(candidates)
    assert result["scenario_type"] == "B'"
    assert result["density_delta"] == 0.45
    assert result["wait_menit"] == 10


def test_classify_bus_level_severe_gap_besar():
    """Gap density >= 0.50 -> C'."""
    candidates = [
        {"bus_id": "BUS-PADAT", "eta_menit": 2, "kepadatan": 0.95},
        {"bus_id": "BUS-SEPI", "eta_menit": 10, "kepadatan": 0.15},
    ]
    result = classify_bus_level(candidates)
    assert result["scenario_type"] == "C'"
    assert result["density_delta"] == 0.80


def test_classify_bus_level_no_alt_saat_semua_mirip():
    """Semua bus mirip -> D' (negative control)."""
    candidates = [
        {"bus_id": "BUS-A", "eta_menit": 2, "kepadatan": 0.45},
        {"bus_id": "BUS-B", "eta_menit": 8, "kepadatan": 0.50},
    ]
    result = classify_bus_level(candidates)
    assert result["scenario_type"] == "D'"
    assert result["spread_density"] == 0.05


def test_classify_bus_level_kurang_dua_kandidat():
    """Satu kandidat saja -> D'."""
    candidates = [{"bus_id": "BUS-A", "eta_menit": 2, "kepadatan": 0.90}]
    result = classify_bus_level(candidates)
    assert result["scenario_type"] == "D'"


def test_classify_bus_level_tercepat_sudah_sepi():
    """Tercepat sudah sepi -> tidak ada konflik (bukan B'/C')."""
    candidates = [
        {"bus_id": "BUS-SEPI", "eta_menit": 2, "kepadatan": 0.20},
        {"bus_id": "BUS-PADAT", "eta_menit": 8, "kepadatan": 0.90},
    ]
    result = classify_bus_level(candidates)
    assert result["scenario_type"] == "D'"


def test_classify_bus_level_threshold_konstanta_sesuai_c251():
    assert BUS_CROWDED_THRESHOLD == 0.80
    assert BUS_EMPTY_THRESHOLD == 0.35
