"""Unit test untuk service Dijkstra TransJakarta.

Tes-tes di sini sengaja memakai graph dummy in-memory (tanpa Supabase)
agar bisa berjalan deterministik dan cepat. Topologi:

    Koridor 1 (K1):  A --> B --> C
    Koridor 2 (K2):  C --> D --> E
    Halte C dilayani oleh K1 dan K2 -> titik transit.
"""

import pytest

from services.dijkstra import (
    build_graph,
    candidate_diversity_report,
    dijkstra,
    format_rute,
)
from services.geo import distance_meters

KEPADATAN_DUMMY = 0.50


def _graph_data_dummy() -> dict:
    """Bangun graph_data mirip output load_graph_data, tanpa hit Supabase.

    Skema baru: `kepadatan_bus` = per-bus per-jam (bukan per-segmen lagi).
    Dijkstra mengambil min() per koridor saat build_graph.
    """
    return {
        "segmen": [
            {"segmen_id": "K1_A_B", "koridor_id": 1, "halte_asal": "A",
             "halte_tujuan": "B", "urutan": 1, "waktu_tempuh_detik": 180},
            {"segmen_id": "K1_B_C", "koridor_id": 1, "halte_asal": "B",
             "halte_tujuan": "C", "urutan": 2, "waktu_tempuh_detik": 180},
            {"segmen_id": "K2_C_D", "koridor_id": 2, "halte_asal": "C",
             "halte_tujuan": "D", "urutan": 1, "waktu_tempuh_detik": 240},
            {"segmen_id": "K2_D_E", "koridor_id": 2, "halte_asal": "D",
             "halte_tujuan": "E", "urutan": 2, "waktu_tempuh_detik": 240},
        ],
        "kepadatan_bus": [
            # Koridor 1 punya 1 bus, koridor 2 punya 1 bus. Min == nilai itu.
            {"bus_id": "B-K1-01", "koridor_id": 1, "jam": 8,
             "hari_tipe": "weekday", "kepadatan": KEPADATAN_DUMMY},
            {"bus_id": "B-K2-01", "koridor_id": 2, "jam": 8,
             "hari_tipe": "weekday", "kepadatan": KEPADATAN_DUMMY},
        ],
        "halte": {
            h: {"halte_id": h, "nama": h, "lat": 0.0, "lng": i * 0.001}
            for i, h in enumerate(["A", "B", "C", "D", "E"])
        },
        "koridor_halte": [],
        "koridor": {
            1: {"koridor_id": 1, "nama_pendek": "K1", "nama_panjang": "Koridor 1"},
            2: {"koridor_id": 2, "nama_pendek": "K2", "nama_panjang": "Koridor 2"},
        },
        "halte_to_koridor": {
            "A": {1}, "B": {1}, "C": {1, 2}, "D": {2}, "E": {2},
        },
    }


# ----------------------------------------------------------------------
# Test case 1: rute dalam satu koridor (tanpa transit)
# ----------------------------------------------------------------------

def test_rute_dalam_satu_koridor_tanpa_transit():
    """A -> C lewat K1 saja. Dijkstra cost = total jarak Haversine."""
    data = _graph_data_dummy()
    graph = build_graph(data, jam=8, hari_tipe="weekday")
    rute = dijkstra(graph, "A", "C", k=1)

    assert len(rute) == 1
    r = rute[0]
    assert r["transit_count"] == 0
    assert r["n_segmen"] == 2
    expected = (
        distance_meters(0.0, 0.0, 0.0, 0.001)
        + distance_meters(0.0, 0.001, 0.0, 0.002)
    )
    assert r["cost"] == pytest.approx(expected, abs=1e-6)
    assert r["total_jarak_meter"] == pytest.approx(expected, abs=1e-6)
    assert r["rata_kepadatan"] == pytest.approx(KEPADATAN_DUMMY)

    # Pastikan semua edge yang ditempuh berupa segmen koridor 1
    tipe_path = [(e["tipe"], e["koridor_id"]) for e in r["path"]]
    assert tipe_path == [("segmen", 1), ("segmen", 1)]


# ----------------------------------------------------------------------
# Test case 2: rute dengan satu transit harus lebih mahal
# ----------------------------------------------------------------------

def test_rute_dengan_satu_transit_lebih_mahal():
    """A -> E mengharuskan transit di C antara K1 dan K2.

    Cost Dijkstra tetap jarak; metadata transfer dan kepadatan tetap dihitung
    untuk evaluasi setelah kandidat terbentuk.
    """
    data = _graph_data_dummy()
    graph = build_graph(data, jam=8, hari_tipe="weekday")
    rute = dijkstra(graph, "A", "E", k=1)

    assert len(rute) == 1
    r = rute[0]
    assert r["transit_count"] == 1
    assert r["n_segmen"] == 4

    expected = sum(
        distance_meters(0.0, i * 0.001, 0.0, (i + 1) * 0.001)
        for i in range(4)
    )
    assert r["cost"] == pytest.approx(expected, abs=1e-6)
    assert r["rata_kepadatan"] == pytest.approx(KEPADATAN_DUMMY)

    # Cek bahwa path mengandung tepat satu edge transit
    n_transit_edges = sum(1 for e in r["path"] if e["tipe"] == "transit")
    assert n_transit_edges == 1

    # Format response: harus ada marker transit di C antara koridor 1 dan 2
    formatted = format_rute(r, data)
    assert formatted["skor"] == pytest.approx(formatted["primary_score"], abs=1e-4)
    assert formatted["total_jarak_meter"] == pytest.approx(expected, abs=0.01)
    assert formatted["ranking_method"] == "primary_score_then_density_rerank"
    assert formatted["ranking_phase_1"]["estimasi_menit"] == 14
    assert formatted["ranking_phase_1"]["jumlah_transit"] == 1
    assert formatted["ranking_phase_1"]["primary_score"] == pytest.approx(formatted["primary_score"])
    assert formatted["ranking_phase_2"]["rata_kepadatan"] == pytest.approx(KEPADATAN_DUMMY)
    assert formatted["ranking_phase_2"]["density_norm"] == pytest.approx(KEPADATAN_DUMMY)
    transit_markers = [s for s in formatted["segmen"] if s.get("tipe") == "transit"]
    assert len(transit_markers) == 1
    t = transit_markers[0]
    assert t["transit_di"] == "C"
    assert t["transit_di_id"] == "C"
    assert t["dari_koridor"] == 1
    assert t["ke_koridor"] == 2

    # Pastikan field halte_id & segmen_detail tersedia pada grup "naik"
    # (dipakai frontend untuk plot polyline warna kepadatan).
    grup_naik = [s for s in formatted["segmen"] if s.get("tipe") == "naik"]
    assert len(grup_naik) == 2
    grup1, grup2 = grup_naik
    assert grup1["naik_di_id"] == "A"
    assert grup1["turun_di_id"] == "C"
    assert [d["dari_id"] for d in grup1["segmen_detail"]] == ["A", "B"]
    assert [d["ke_id"] for d in grup1["segmen_detail"]] == ["B", "C"]
    assert all("jarak_meter" in d for d in grup1["segmen_detail"])
    assert grup2["naik_di_id"] == "C"
    assert grup2["turun_di_id"] == "E"


def test_kandidat_diranking_fase_pertama_operasional_dulu():
    """Rute lebih dekat/waktu singkat tetap diutamakan sebelum kepadatan."""
    data = _graph_data_dummy()
    data["halte"]["X"] = {"halte_id": "X", "nama": "X", "lat": 0.001, "lng": 0.001}
    data["segmen"].extend([
        {"segmen_id": "K3_A_X", "koridor_id": 3, "halte_asal": "A",
         "halte_tujuan": "X", "urutan": 1, "waktu_tempuh_detik": 240},
        {"segmen_id": "K3_X_C", "koridor_id": 3, "halte_asal": "X",
         "halte_tujuan": "C", "urutan": 2, "waktu_tempuh_detik": 240},
    ])
    data["kepadatan_bus"].extend([
        {"bus_id": "B-K3-01", "koridor_id": 3, "jam": 8,
         "hari_tipe": "weekday", "kepadatan": 0.10},
    ])
    data["koridor"][3] = {
        "koridor_id": 3, "nama_pendek": "K3", "nama_panjang": "Koridor 3"
    }
    data["halte_to_koridor"]["A"].add(3)
    data["halte_to_koridor"]["C"].add(3)
    data["halte_to_koridor"]["X"] = {3}

    graph = build_graph(data, jam=8, hari_tipe="weekday")
    rute = dijkstra(graph, "A", "C", k=2)

    assert len(rute) == 2
    assert rute[0]["total_waktu_detik"] < rute[1]["total_waktu_detik"]
    assert [e["koridor_id"] for e in rute[0]["path"] if e["tipe"] == "segmen"] == [1, 1]
    assert rute[1]["rata_kepadatan"] == pytest.approx(0.10)


def test_segment_crowding_dipakai_sebagai_bobot_kepadatan_edge():
    data = _graph_data_dummy()
    graph = build_graph(
        data,
        jam=8,
        hari_tipe="weekday",
        segment_crowding={"K1_A_B": 0.90, "K1_B_C": 0.30},
    )
    rute = dijkstra(graph, "A", "C", k=1)

    assert rute[0]["rata_kepadatan"] == pytest.approx(0.60)


# ----------------------------------------------------------------------
# Test case 3: asal = tujuan harus raise ValueError
# ----------------------------------------------------------------------

def test_asal_sama_dengan_tujuan_raises():
    data = _graph_data_dummy()
    graph = build_graph(data, jam=8, hari_tipe="weekday")
    with pytest.raises(ValueError):
        dijkstra(graph, "A", "A", k=1)


# ----------------------------------------------------------------------
# Test case 4: halte tidak terhubung -> list kosong
# ----------------------------------------------------------------------

def test_halte_tidak_terhubung_return_kosong():
    """Halte F ditambahkan tanpa edge masuk maupun keluar.

    Karena tidak ada jalur dari A ke F dalam batas transit manapun,
    dijkstra() harus mengembalikan list kosong (router akan menerjemahkannya
    jadi HTTPException 404).
    """
    data = _graph_data_dummy()
    data["halte"]["F"] = {"halte_id": "F", "nama": "F", "lat": 0.0, "lng": 0.0}
    data["halte_to_koridor"]["F"] = {99}  # koridor tunggal, tidak terhubung
    graph = build_graph(data, jam=8, hari_tipe="weekday")

    rute = dijkstra(graph, "A", "F", k=3)
    assert rute == []


# ----------------------------------------------------------------------
# Test case 5: candidate generation harus mencoba blokir seluruh koridor,
# bukan cuma satu edge, agar kombinasi koridor lain benar-benar ditemukan
# ----------------------------------------------------------------------

def _corridor_diversity_graph_data() -> dict:
    """Koridor 1 punya dua jalur berbiaya sama (langsung A-D, dan lewat B);
    koridor 2 (lewat E) lebih jauh tapi satu-satunya jalur yang benar-benar
    keluar dari koridor 1. Rute pertama (A-D langsung) cuma punya satu edge
    segmen, jadi blokir-satu-edge tidak akan pernah menyentuh koridor 2.
    """
    return {
        "segmen": [
            {"segmen_id": "K1_A_D", "koridor_id": 1, "halte_asal": "A",
             "halte_tujuan": "D", "waktu_tempuh_detik": 400},
            {"segmen_id": "K1_A_B", "koridor_id": 1, "halte_asal": "A",
             "halte_tujuan": "B", "waktu_tempuh_detik": 200},
            {"segmen_id": "K1_B_D", "koridor_id": 1, "halte_asal": "B",
             "halte_tujuan": "D", "waktu_tempuh_detik": 200},
            {"segmen_id": "K2_A_E", "koridor_id": 2, "halte_asal": "A",
             "halte_tujuan": "E", "waktu_tempuh_detik": 250},
            {"segmen_id": "K2_E_D", "koridor_id": 2, "halte_asal": "E",
             "halte_tujuan": "D", "waktu_tempuh_detik": 250},
        ],
        "kepadatan_bus": [
            {"bus_id": "B-K1-01", "koridor_id": 1, "jam": 8,
             "hari_tipe": "weekday", "kepadatan": 0.5},
            {"bus_id": "B-K2-01", "koridor_id": 2, "jam": 8,
             "hari_tipe": "weekday", "kepadatan": 0.5},
        ],
        "halte": {
            "A": {"halte_id": "A", "nama": "A", "lat": 0.0, "lng": 0.0},
            "B": {"halte_id": "B", "nama": "B", "lat": 0.0, "lng": 0.002},
            "D": {"halte_id": "D", "nama": "D", "lat": 0.0, "lng": 0.004},
            "E": {"halte_id": "E", "nama": "E", "lat": 0.001, "lng": 0.002},
        },
        "koridor_halte": [],
        "koridor": {
            1: {"koridor_id": 1, "nama_pendek": "K1", "nama_panjang": "Koridor 1"},
            2: {"koridor_id": 2, "nama_pendek": "K2", "nama_panjang": "Koridor 2"},
        },
        "halte_to_koridor": {
            "A": {1, 2}, "B": {1}, "D": {1, 2}, "E": {2},
        },
    }


def test_corridor_level_blocking_surfaces_alternative_corridor_combination():
    data = _corridor_diversity_graph_data()
    graph = build_graph(data, jam=8, hari_tipe="weekday")
    routes = dijkstra(graph, "A", "D", k=3)

    corridor_sequences = [
        tuple(e["koridor_id"] for e in r["path"] if e["tipe"] == "segmen")
        for r in routes
    ]
    assert any(2 in seq for seq in corridor_sequences), (
        "koridor 2 alternative was not discovered by candidate generation"
    )

    report = candidate_diversity_report(routes)
    assert report["candidate_count"] == 3
    assert report["unique_segment_signatures"] == 3
    assert report["unique_corridor_sequences"] == 2


# ----------------------------------------------------------------------
# Test case: konflik parah — koridor cepat padat, koridor lambat sepi.
# dijkstra(k=3) HARUS menghasilkan >= 2 urutan koridor yang berbeda,
# termasuk koridor 2 yang lebih lambat, agar re-ranking punya bahan.
# ----------------------------------------------------------------------

def _severe_conflict_graph_data() -> dict:
    """Koridor 1 = cepat (2 segmen, 4 menit), koridor 2 = lambat (2 segmen, 6 menit).

    A -> C via K1 jelas lebih pendek; A -> D -> C via K2 adalah satu-satunya
    alternatif. Candidate generation harus menemukan K2, dan re-ranking
    berbasis kepadatan harus bisa memilih K2 saat K1 jauh lebih padat.
    """
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


def test_severe_conflict_returns_multi_corridor_candidates():
    data = _severe_conflict_graph_data()
    graph = build_graph(data, jam=8, hari_tipe="weekday")
    routes = dijkstra(graph, "A", "C", k=3)

    corridor_sequences = [
        tuple(e["koridor_id"] for e in r["path"] if e["tipe"] == "segmen")
        for r in routes
    ]
    assert len(routes) >= 2, (
        "candidate generation must produce >= 2 routes for the conflict OD"
    )
    assert (1, 1) in corridor_sequences, "fast corridor route missing"
    assert (2, 2) in corridor_sequences, (
        "slow corridor route was not discovered by candidate generation"
    )


def test_primary_ranking_penalizes_crowded_fast_route():
    """Fast-but-crowded K1 vs slow-but-empty K2.

    Primary ranking harus menghitung kepadatan sebagai komponen skor, bukan
    sekadar time/distance/transfer. Dengan bobot saat ini
    (time .30, distance .20, transfer .30, density .20):

        K1 = .30*0 + .20*0 + .30*0 + .20*1 = .20
        K2 = .30*1 + .20*1 + .30*0 + .20*0 = .50

    Jadi rute cepat-padat (K1) tetap menang fase 1, tetapi sudah terkena
    penalti kepadatan (skor naik dari 0.00 menjadi 0.20). Pergeseran final
    ke rute sepi terjadi di re-ranking, bukan di fase ini.
    """
    data = _severe_conflict_graph_data()
    graph = build_graph(data, jam=8, hari_tipe="weekday")
    routes = dijkstra(graph, "A", "C", k=3)

    by_corridor = {
        tuple(e["koridor_id"] for e in r["path"] if e["tipe"] == "segmen")[0]: r
        for r in routes
    }
    k1 = by_corridor[1]
    k2 = by_corridor[2]

    assert k1["rata_kepadatan"] > k2["rata_kepadatan"]
    assert k1["density_norm"] > k2["density_norm"]
    assert k1["primary_score"] == pytest.approx(0.20, abs=1e-9), (
        "crowded route must be penalized by its density_norm=1"
    )
    assert k2["primary_score"] == pytest.approx(0.50, abs=1e-9), (
        "sparse slow route must pay time+distance cost"
    )
    assert k1["primary_score"] < k2["primary_score"], (
        "operational factors still win phase 1; density flip is phase 2"
    )


def test_dijkstra_accepts_weight_override():
    data = _severe_conflict_graph_data()
    graph = build_graph(data, jam=8, hari_tipe="weekday")

    routes = dijkstra(graph, "A", "C", k=3, weights={
        "time": 0.0, "distance": 0.0, "transfer": 0.0, "density": 1.0,
    })

    by_corridor = {
        tuple(e["koridor_id"] for e in r["path"] if e["tipe"] == "segmen")[0]: r
        for r in routes
    }
    assert by_corridor[2]["primary_score"] < by_corridor[1]["primary_score"]
