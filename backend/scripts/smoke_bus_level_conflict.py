"""Smoke offline: bus-level conflict (earliest padat vs later sepi) harus
menghasilkan B' atau C' dan selector density-aware memilih bus yang lebih sepi.

Jalankan dari backend/:
    ./venv/Scripts/python.exe scripts/smoke_bus_level_conflict.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.bus_selector import collect_bus_candidates, select_bus_per_segmen
from services.scenario_classifier import classify_bus_level


def main() -> int:
    sim_time = 8 * 3600
    jadwal = {
        "BUS-PADAT": [
            {"halte_id": "A", "koridor_id": 1, "waktu_tiba_detik": sim_time + 2 * 60},
        ],
        "BUS-SEPI": [
            {"halte_id": "A", "koridor_id": 1, "waktu_tiba_detik": sim_time + 12 * 60},
        ],
    }
    realtime = {"BUS-PADAT": 0.90, "BUS-SEPI": 0.20}

    kandidat = collect_bus_candidates(
        jadwal,
        realtime,
        koridor_id=1,
        halte_naik="A",
        reference_time=sim_time,
    )
    klasifikasi = classify_bus_level(kandidat)
    print(f"klasifikasi bus-level : {klasifikasi['scenario_type']} ({klasifikasi['reason']})")
    if klasifikasi["scenario_type"] not in ("B'", "C'"):
        print("FAIL: konflik padat-vs-sepi tidak terdeteksi")
        return 1

    segmen = [{"tipe": "naik", "koridor_id": 1, "naik_di_id": "A", "turun_di_id": "B",
               "segmen_detail": [{"waktu_menit": 5}]}]
    select_bus_per_segmen(segmen, sim_time=sim_time, jadwal=jadwal, realtime_kepadatan=realtime)
    rek = segmen[0]["bus_rekomendasi"]
    print(f"bus terpilih          : {rek['bus_id']} (density={rek['kepadatan']})")
    if rek["bus_id"] != "BUS-SEPI":
        print("FAIL: density-aware selector tidak memilih bus lebih sepi")
        return 1

    print("OK: bus-level conflict terdeteksi dan bus lebih sepi menang")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
