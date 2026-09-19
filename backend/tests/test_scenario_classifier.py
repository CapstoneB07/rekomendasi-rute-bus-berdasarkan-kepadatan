from services.dijkstra import build_graph, dijkstra
from services.scenario_classifier import classify_od_pair, classify_routes


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
