import services.gtfs_simulation as gs
from services.gtfs_simulation import SimulationContext, kepadatan_bus_live

JAM = 3600


def _instance(tid: str, koridor: str, departure: int) -> dict:
    return {
        "trip_instance_id": tid,
        "koridor_key": koridor,
        "departure_time": departure,
    }


def _ctx(instances: list[dict]) -> SimulationContext:
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
    )


def _patch_crowding(monkeypatch, loads: dict[str, float]) -> None:
    monkeypatch.setattr(
        gs,
        "generate_crowding",
        lambda *_a, **_k: {"trip_loads": {t: {"trip_load_factor": v} for t, v in loads.items()}},
    )


def test_meminjam_trip_koridor_dan_time_band_yang_sama(monkeypatch):
    # morning_peak (06-09) dan midday_offpeak (09-16) di koridor 1; satu trip di koridor 2.
    ctx = _ctx([
        _instance("PAGI", "1", 7 * JAM),
        _instance("SIANG", "1", 12 * JAM),
        _instance("K2-PAGI", "2", 7 * JAM),
    ])
    _patch_crowding(monkeypatch, {"PAGI": 0.9, "SIANG": 0.3, "K2-PAGI": 0.1})

    pagi = kepadatan_bus_live(ctx, "TJ-1", 1, 7 * JAM + 600)
    siang = kepadatan_bus_live(ctx, "TJ-1", 1, 12 * JAM + 600)

    assert pagi["trip_load_factor"] == 0.9
    assert pagi["label_kepadatan"] == "Padat"
    assert pagi["capacity"] == gs.BUS_CAPACITY
    assert pagi["estimated_passengers"] == round(0.9 * gs.BUS_CAPACITY, 2)
    assert siang["trip_load_factor"] == 0.3
    assert siang["label_kepadatan"] == "Sepi"


def test_koridor_di_luar_simulasi_atau_band_tanpa_trip_null(monkeypatch):
    ctx = _ctx([_instance("PAGI", "1", 7 * JAM)])
    _patch_crowding(monkeypatch, {"PAGI": 0.9})

    assert kepadatan_bus_live(ctx, "TJ-1", 8, 7 * JAM) is None  # koridor 8 tidak disimulasikan
    assert kepadatan_bus_live(ctx, "TJ-1", 1, 12 * JAM) is None  # tidak ada trip di band siang


def test_bus_sama_selalu_mendapat_trip_sama_dan_bus_berbeda_tersebar(monkeypatch):
    instances = [_instance(f"T{i}", "1", 7 * JAM) for i in range(10)]
    ctx = _ctx(instances)
    _patch_crowding(monkeypatch, {f"T{i}": i / 10 for i in range(10)})

    hasil = {
        bus: kepadatan_bus_live(ctx, bus, 1, 7 * JAM)["trip_load_factor"]
        for bus in (f"TJ-{n}" for n in range(30))
    }
    ulang = {bus: kepadatan_bus_live(ctx, bus, 1, 8 * JAM)["trip_load_factor"] for bus in hasil}

    assert ulang == hasil  # stabil di dalam satu time band
    assert len(set(hasil.values())) > 3  # bus tidak semua mendapat nilai yang sama
