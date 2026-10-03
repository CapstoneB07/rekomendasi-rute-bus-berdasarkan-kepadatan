from datetime import datetime, timedelta, timezone

from services.bus_selector import select_bus_per_segmen
from services.gtfs_simulation import (
    BUS_CAPACITY,
    SimulationContext,
    effective_trip_loads,
    live_overlay,
    live_trip_instance_id,
    realtime_trip_loads,
)
from services.live_crowding import LiveCrowding, _parse_timestamp

NOW = datetime.now(timezone.utc)


def _store(passengers: int | None, age_seconds: float = 0, ttl: float = 120) -> LiveCrowding:
    store = LiveCrowding(None, "CV-1", ttl_seconds=ttl)
    if passengers is not None:
        store.update({
            "jumlah_penumpang": passengers,
            "updated_at": (NOW - timedelta(seconds=age_seconds)).isoformat(),
        })
    return store


def _instance(tid: str, koridor: str, direction: str, start: int, end: int) -> dict:
    return {
        "trip_instance_id": tid,
        "bus_id": tid,
        "trip_id": tid,
        "koridor_id": int(koridor),
        "koridor_key": koridor,
        "direction_id": direction,
        "departure_time": start,
        "first_stop_departure_time": start,
        "last_stop_arrival_time": end,
        "stops": [],
        "segment_ids": [],
    }


def _ctx(instances: list[dict], live: LiveCrowding | None) -> SimulationContext:
    return SimulationContext(
        instances=instances,
        jadwal={},
        trip_supply_per_koridor={},
        daily_mean_load_factor={},
        latest_date=None,
        latest_date_per_koridor={},
        recent_dates_per_koridor={},
        ridership_by_date_koridor={},
        segmen_by_id={},
        fallback_jadwal={},
        live_crowding=live,
    )


def _crowding(*tids: str) -> dict:
    return {"trip_loads": {t: {"trip_load_factor": 0.5, "estimated_passengers": 40.0} for t in tids}}


def test_timestamp_postgres_pecahan_detik_5_digit():
    parsed = _parse_timestamp("2026-10-03T12:00:00.12345+00:00")
    assert parsed == datetime(2026, 10, 3, 12, 0, 0, 123450, tzinfo=timezone.utc)


def test_pembacaan_segar_dan_stale():
    assert _store(30, age_seconds=10).latest(NOW)["jumlah_penumpang"] == 30
    assert _store(30, age_seconds=500).latest(NOW) is None
    assert _store(None).latest(NOW) is None


def test_instance_live_aktif_dipilih_dulu_lalu_berikutnya():
    instances = [
        _instance("BUS-1-0-001", "1", "0", 3600, 7200),
        _instance("BUS-1-0-002", "1", "0", 5400, 9000),
        _instance("BUS-1-1-001", "1", "1", 3600, 7200),  # arah lain
        _instance("BUS-2-0-001", "2", "0", 3600, 7200),  # koridor lain
    ]
    ctx = _ctx(instances, None)
    assert live_trip_instance_id(ctx, 6000) == "BUS-1-0-001"  # dua aktif -> berangkat awal
    assert live_trip_instance_id(ctx, 7500) == "BUS-1-0-002"  # yang pertama sudah selesai
    assert live_trip_instance_id(ctx, 1000) == "BUS-1-0-001"  # belum ada aktif -> berikutnya
    assert live_trip_instance_id(ctx, 10000) is None  # semua sudah selesai


def test_override_hanya_bus_live_dan_tidak_memutasi_cache():
    ctx = _ctx([_instance("BUS-1-0-001", "1", "0", 3600, 7200)], _store(60))
    crowding = _crowding("BUS-1-0-001", "BUS-2-0-001")

    loads = effective_trip_loads(ctx, crowding, 4000)

    assert loads["BUS-1-0-001"]["trip_load_factor"] == 60 / BUS_CAPACITY
    assert loads["BUS-1-0-001"]["data_source"] == "cv_live"
    assert loads["BUS-2-0-001"] == crowding["trip_loads"]["BUS-2-0-001"]
    assert "data_source" not in crowding["trip_loads"]["BUS-1-0-001"]


def test_tanpa_data_segar_kembali_ke_generated():
    instances = [_instance("BUS-1-0-001", "1", "0", 3600, 7200)]
    crowding = _crowding("BUS-1-0-001")
    for live in (None, _store(None), _store(60, age_seconds=500)):
        assert effective_trip_loads(_ctx(instances, live), crowding, 4000) is crowding["trip_loads"]


def test_selector_memilih_bus_live_yang_sepi():
    ctx = _ctx([_instance("B-K1-01", "1", "0", 0, 7200)], _store(8))
    ctx.crowding_cache[(f"sample30:x", "x")] = _crowding("B-K1-01", "B-K1-02") | {
        "tanggal": None, "sampled_dates_by_koridor": {}, "simulation_run_id": "x", "segment_loads": {},
    }
    ctx.crowding_cache[(f"sample30:x", "x")]["trip_loads"]["B-K1-01"]["trip_load_factor"] = 0.9
    ctx.crowding_cache[(f"sample30:x", "x")]["trip_loads"]["B-K1-02"]["trip_load_factor"] = 0.6

    kepadatan = realtime_trip_loads(ctx, simulation_run_id="x", sim_time=100)
    assert kepadatan["B-K1-01"] == 8 / BUS_CAPACITY

    stops = lambda t: [  # noqa: E731
        {"halte_id": "H1", "koridor_id": 1, "waktu_tiba_detik": t, "urutan": 1},
    ]
    jadwal = {"B-K1-01": stops(300), "B-K1-02": stops(300)}
    segmen = [{"tipe": "naik", "koridor_id": 1, "naik_di_id": "H1"}]
    select_bus_per_segmen(segmen, 100, jadwal, kepadatan)
    assert segmen[0]["bus_rekomendasi"]["bus_id"] == "B-K1-01"


def test_live_overlay_hanya_bila_data_segar():
    instances = [_instance("BUS-1-0-001", "1", "0", 3600, 7200)]
    tid, payload = live_overlay(_ctx(instances, _store(60)), 4000)
    assert tid == "BUS-1-0-001"
    assert payload["trip_load_factor"] == 60 / BUS_CAPACITY
    assert live_overlay(_ctx(instances, _store(60, age_seconds=500)), 4000) is None
    assert live_overlay(_ctx(instances, None), 4000) is None


def test_rekomendasi_menandai_data_source_live():
    jadwal = {
        "B-K1-01": [{"halte_id": "H1", "koridor_id": 1, "waktu_tiba_detik": 300, "urutan": 1}],
        "B-K1-02": [{"halte_id": "H1", "koridor_id": 1, "waktu_tiba_detik": 600, "urutan": 1}],
    }
    for live_id, expected in (("B-K1-01", "cv_live"), (None, "generated")):
        segmen = [{"tipe": "naik", "koridor_id": 1, "naik_di_id": "H1"}]
        select_bus_per_segmen(
            segmen, 100, jadwal, {"B-K1-01": 0.1, "B-K1-02": 0.9}, live_bus_id=live_id
        )
        assert segmen[0]["bus_rekomendasi"]["bus_id"] == "B-K1-01"
        assert segmen[0]["bus_rekomendasi"]["data_source"] == expected
