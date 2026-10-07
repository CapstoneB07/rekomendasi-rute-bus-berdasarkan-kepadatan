import json

from services.live_buses import LiveBuses, bangun_jadwal_live, parse_pesan, topik_langganan

KORIDOR = {"1": 1, "9": 9}


def _payload(**override) -> bytes:
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
    return json.dumps(data).encode()


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
    assert parse_pesan(b"bukan json", KORIDOR) is None
    assert parse_pesan(json.dumps({"route_code": "1"}).encode(), KORIDOR) is None
    assert parse_pesan(_payload(latitude=None), KORIDOR) is None


def test_parse_pesan_tanpa_stops_next_stop_kosong():
    assert parse_pesan(_payload(stops=[]), KORIDOR)["next_stop"] == ""


def test_snapshot_membuang_bus_basi_dan_menyimpan_pesan_terakhir():
    now = [0.0]
    live = LiveBuses(KORIDOR, max_age=120, clock=lambda: now[0])
    live.terima(_payload(bus_body_no="A", latitude=-6.1))
    now[0] = 100
    live.terima(_payload(bus_body_no="B"))
    live.terima(_payload(bus_body_no="A", latitude=-6.3))  # menimpa pesan lama bus A

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


def test_topik_langganan_per_route_code():
    assert topik_langganan({"9", "1", "JAK.01"}) == [
        "/mobile_armada/+/1/#",
        "/mobile_armada/+/9/#",
        "/mobile_armada/+/JAK.01/#",
    ]
