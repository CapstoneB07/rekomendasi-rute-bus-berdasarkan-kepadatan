from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import live as live_router
from services import live_buses
from services.live_buses import LiveBuses, bangun_jadwal_live, parse_pesan

KORIDOR = {"1": 1, "9": 9}


def _payload(**override) -> dict:
    data = {
        "latitude": -6.2379,
        "longitude": 106.8267,
        "bearing": 28,
        "route_code": "1",
        "bus_body_no": "TJ-826",
        "trip_id": "1-R01",
        "eta": 2,
        "passengers_status": "",
        "stops": [{"name": "Transvision", "stop_id": "B05802P", "parent_stop_id": "P1", "eta": 2}],
    }
    data.update(override)
    return data


def test_parse_pesan_bus_koridor_dikenal():
    bus = parse_pesan(_payload(), KORIDOR)
    assert bus == {
        "bus_id": "TJ-826",
        "koridor_id": 1,
        "lat": -6.2379,
        "lng": 106.8267,
        "bearing": 28,
        "next_stop": "Transvision",
        "eta_minutes": 2,
        "trip_id": "1-R01",
        "stops": [{"stop_id": "B05802P", "parent_stop_id": "P1", "eta": 2}],
    }


def test_parse_pesan_route_tidak_dikenal_diabaikan():
    assert parse_pesan(_payload(route_code="JAK.27"), KORIDOR) is None


def test_parse_pesan_rusak_diabaikan():
    assert parse_pesan({"route_code": "1"}, KORIDOR) is None
    assert parse_pesan(_payload(latitude=None), KORIDOR) is None


def test_parse_pesan_tanpa_stops_next_stop_kosong():
    assert parse_pesan(_payload(stops=[]), KORIDOR)["next_stop"] == ""


def test_parse_pesan_halte_tanpa_eta_dilewati_bukan_membuang_bus():
    bus = parse_pesan(
        _payload(stops=[
            {"name": "Sedang disinggahi", "stop_id": "G0", "parent_stop_id": None},
            {"name": "Berikutnya", "stop_id": "G1", "parent_stop_id": None, "eta": 3},
        ]),
        KORIDOR,
    )
    assert bus["next_stop"] == "Berikutnya"
    assert bus["stops"] == [{"stop_id": "G1", "parent_stop_id": None, "eta": 3}]


def test_snapshot_membuang_bus_basi_dan_menyimpan_pesan_terakhir():
    now = [0.0]
    live = LiveBuses(KORIDOR, max_age=120, clock=lambda: now[0])
    live.terima_relay("tersambung", [_payload(bus_body_no="A", latitude=-6.1)])
    now[0] = 100
    live.terima_relay("tersambung", [_payload(bus_body_no="B"), _payload(bus_body_no="A", latitude=-6.3)])

    assert {b["bus_id"]: b["lat"] for b in live.snapshot()} == {"A": -6.3, "B": -6.2379}

    now[0] = 230  # A dan B sudah > 120 detik
    assert live.snapshot() == []


def test_bangun_jadwal_live_cocokkan_halte_dan_hitung_waktu_tiba():
    bus = parse_pesan(
        _payload(stops=[
            {"name": "A", "stop_id": "G1", "parent_stop_id": "H1", "eta": 1},
            {"name": "B", "stop_id": "X9", "parent_stop_id": "G2", "eta": 4},  # cocok via parent
            {"name": "C", "stop_id": "X8", "parent_stop_id": "X7", "eta": 6},  # tidak dikenal
        ]),
        KORIDOR,
    )
    kosong = parse_pesan(_payload(bus_body_no="KOSONG", stops=[]), KORIDOR)

    jadwal = bangun_jadwal_live([bus, kosong], {"G1", "G2"}, detik_sekarang=36000)

    assert jadwal == {
        "TJ-826": [
            {"halte_id": "G1", "koridor_id": 1, "waktu_tiba_detik": 36060},
            {"halte_id": "G2", "koridor_id": 1, "waktu_tiba_detik": 36240},
        ]
    }


def test_select_bus_per_segmen_memakai_eta_dan_kepadatan_bus_live():
    from services.bus_selector import select_bus_per_segmen

    buses = [
        parse_pesan(_payload(bus_body_no="CEPAT", stops=[
            {"name": "A", "stop_id": "G1", "parent_stop_id": None, "eta": 3},
            {"name": "B", "stop_id": "G2", "parent_stop_id": None, "eta": 9},
        ]), KORIDOR),
        parse_pesan(_payload(bus_body_no="SEPI", stops=[
            {"name": "A", "stop_id": "G1", "parent_stop_id": None, "eta": 5},
            {"name": "B", "stop_id": "G2", "parent_stop_id": None, "eta": 11},
        ]), KORIDOR),
        parse_pesan(_payload(bus_body_no="TANPA-DATA", stops=[
            {"name": "A", "stop_id": "G1", "parent_stop_id": None, "eta": 1},
        ]), KORIDOR),
        parse_pesan(_payload(bus_body_no="LEWAT", stops=[
            {"name": "B", "stop_id": "G2", "parent_stop_id": None, "eta": 2},
        ]), KORIDOR),
    ]
    jadwal = bangun_jadwal_live(buses, {"G1", "G2"}, detik_sekarang=36000)
    kepadatan = {"CEPAT": 0.9, "SEPI": 0.2, "LEWAT": 0.1}  # TANPA-DATA tidak punya kepadatan
    segmen = [{"tipe": "naik", "koridor_id": 1, "naik_di_id": "G1", "turun_di_id": "G2"}]

    select_bus_per_segmen(segmen, 36000, jadwal, kepadatan)

    rek = segmen[0]["bus_rekomendasi"]
    assert rek["bus_id"] == "SEPI"  # 2 menit lebih lama tapi jauh lebih sepi dari CEPAT
    assert rek["eta_menit"] == 5
    assert rek["candidate_count"] == 2  # LEWAT sudah melewati G1, TANPA-DATA tanpa kepadatan


def test_status_menyambung_sebelum_ada_relay_lalu_terputus_saat_relay_basi():
    now = [0.0]
    live = LiveBuses(KORIDOR, relay_basi=30, clock=lambda: now[0])
    assert live.status == live_buses.MENYAMBUNG

    live.terima_relay("tersambung", [])
    assert live.status == live_buses.TERSAMBUNG

    now[0] = 31  # tidak ada browser relay yang mengirim lagi
    assert live.status == live_buses.TERPUTUS


def test_status_relay_tersambung_menang_atas_relay_lain_yang_gagal():
    now = [0.0]
    live = LiveBuses(KORIDOR, relay_basi=30, clock=lambda: now[0])
    live.terima_relay("tersambung", [])
    now[0] = 5
    live.terima_relay("ditolak", [])
    assert live.status == live_buses.TERSAMBUNG

    now[0] = 40  # relay yang tersambung sudah basi, yang ditolak belum
    live.terima_relay("ditolak", [])
    assert live.status == live_buses.DITOLAK


def _client() -> tuple[TestClient, LiveBuses]:
    app = FastAPI()
    app.include_router(live_router.router)
    app.state.live_buses = LiveBuses(KORIDOR)
    app.state.simulation_context = None
    return TestClient(app), app.state.live_buses


def test_api_koridor_mengembalikan_route_code_untuk_dilanggan():
    client, _ = _client()
    assert client.get("/api/live/koridor").json() == {"route_codes": ["1", "9"]}


def test_api_relay_lalu_positions_menampilkan_bus_dan_status():
    client, _ = _client()
    r = client.put("/api/live/buses", json={
        "status": "tersambung",
        "buses": [
            _payload(),
            _payload(bus_body_no="TANPA-GPS", latitude=0, longitude=0),  # ditolak sendiri
            _payload(bus_body_no="LUAR", route_code="JAK.27"),  # valid, koridor tidak dipakai
            "bukan objek",
        ],
    })
    assert r.status_code == 200
    assert r.json() == {"diterima": 1, "ditolak": 2}

    posisi = client.get("/api/live/positions").json()
    assert posisi["status"] == "tersambung"
    assert [f["properties"]["bus_id"] for f in posisi["features"]] == ["TJ-826"]


def test_api_relay_menolak_status_tidak_dikenal_dan_laporan_terlalu_besar():
    client, _ = _client()
    assert client.put("/api/live/buses", json={"status": "bebas", "buses": []}).status_code == 422
    besar = {"status": "tersambung", "buses": [_payload()] * 2001}
    assert client.put("/api/live/buses", json=besar).status_code == 422
