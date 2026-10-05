"""Service pemilih bus per-segmen 'naik' (Algoritma 2).

Dipanggil SETELAH Dijkstra (services/dijkstra.py) menentukan rute terbaik.
Algoritma 1 mencari kandidat rute; Algoritma 2 memilih bus SPESIFIK yang
direkomendasikan untuk tiap segmen 'naik'. Pemilihan bus memakai skor gabungan
kepadatan dan tambahan waktu tunggu dari bus tercepat agar bus yang sedikit
lebih lama tetapi jauh lebih sepi bisa dipilih, tanpa menyarankan tunggu
terlalu lama.

Dua algoritma sengaja dipisah: Dijkstra tidak perlu tahu identitas bus, dan
bus_selector tidak perlu tahu topologi graf. State tidak dibagi.
"""

from collections import defaultdict
from typing import Any, Callable

from services.config import (
    BUS_CAPACITY,
    BUS_SAFE_NEXT_DENSITY_THRESHOLD,
    BUS_SCORE_DENSITY_WEIGHT,
    BUS_SCORE_WAIT_WEIGHT,
    MAX_ETA_MENIT,
    MAX_EXTRA_WAIT_MENIT,
)

KEPADATAN_DECIMAL = 2  # presisi bulatan untuk grouping kepadatan setara
# Nama lama dipertahankan agar importer (monte_carlo, routers/rute) tidak putus.
MAX_ETA_MENIT_DEFAULT = MAX_ETA_MENIT
MAX_ETA_DETIK_DEFAULT = MAX_ETA_MENIT_DEFAULT * 60
MAX_EXTRA_WAIT_MENIT_DEFAULT = MAX_EXTRA_WAIT_MENIT
SAFE_NEXT_BUS_DENSITY_THRESHOLD = BUS_SAFE_NEXT_DENSITY_THRESHOLD
TRANSFER_WALK_PENALTY_DETIK = 0  # tunable: waktu jalan antar platform saat transfer


def _label_kepadatan(k: float) -> str:
    """Mapping numerik -> label lama UI. Sangat padat tetap dipetakan Padat."""
    if k < 0.50:
        return "Sepi"
    if k < 0.80:
        return "Sedang"
    return "Padat"


def _kategori_kepadatan(k: float) -> str:
    return density_category(k)


# Kategori kepadatan c251 §4.2: <0.50 sepi, 0.50–0.80 sedang, 0.80–1.00 padat,
# >=1.00 sangat padat. Urutan ini jadi kunci sort re-ranking (masalah #4).
DENSITY_CATEGORY_ORDER: dict[str, int] = {
    "sepi": 0,
    "sedang": 1,
    "padat": 2,
    "sangat_padat": 3,
}
# Batas penalti Pareto: rute tidak dipromosikan ke kategori kepadatan lebih baik
# bila waktu/jaraknya melebihi batas ini relatif terhadap rute tercepat/terpendek.
MAX_EXTRA_TIME_MENIT_DEFAULT = 15
MAX_EXTRA_DISTANCE_METER_DEFAULT = 3000


def density_category(load_factor: float) -> str:
    if load_factor < 0.50:
        return "sepi"
    if load_factor < 0.80:
        return "sedang"
    if load_factor < 1.00:
        return "padat"
    return "sangat_padat"


def rerank_routes(
    routes: list[dict],
    key_fn: Callable[[dict], dict] | None = None,
    max_extra_time_menit: int = MAX_EXTRA_TIME_MENIT_DEFAULT,
    max_extra_distance_meter: int = MAX_EXTRA_DISTANCE_METER_DEFAULT,
) -> list[dict]:
    """Re-ranking tahap 2: kategori kepadatan dulu, lalu primary_score.

    Menggantikan sort lexicographic `(density_norm, primary_score)` (masalah
    #4). Urutan:
      1. Kategori kepadatan (c251 §4.2) — sepi < sedang < padat < sangat_padat.
      2. Dalam kategori yang sama, kepadatan kontinu `lf` (c251 Eq 4.20) —
         rute lebih sepi menang.
      3. Bila kepadatan juga persis sama, primary_score (skor gabungan yang
         sudah menghukum waktu/jarak/transfer).

    Batas penalti Pareto mencegah rute ekstrem (jauh lebih lama/lebih jauh)
    menang hanya karena sedikit lebih sepi: rute yang waktu ATAU jaraknya
    melebihi (tercepat + cap) / (terpendek + cap) diturunkan ke bawah semua
    rute yang masih dalam batas.

    `key_fn` (opsional) memetakan tiap item ke dict `formatted` yang memuat
    `estimasi_menit`, `total_jarak_meter`, `rata_kepadatan`, `primary_score`.
    Default: item itu sendiri adalah dict formatted (dipakai routers/rute.py).
    """
    if key_fn is None:
        key_fn = lambda r: r
    if len(routes) <= 1:
        return list(routes)

    formatted = [key_fn(r) for r in routes]

    def _est_menit(f: dict) -> float:
        if "estimasi_menit" in f:
            return float(f.get("estimasi_menit", 0.0) or 0.0)
        # Raw route dict (belum format_rute) membawa total_waktu_detik, bukan
        # estimasi_menit.
        return float(f.get("total_waktu_detik", 0.0) or 0.0) / 60.0

    ref_time = min(_est_menit(f) for f in formatted)
    ref_dist = min(float(f.get("total_jarak_meter", 0.0) or 0.0) for f in formatted)

    def _sort_key(r: dict) -> tuple:
        f = key_fn(r)
        t = _est_menit(f)
        d = float(f.get("total_jarak_meter", 0.0) or 0.0)
        within_cap = (
            t <= ref_time + max_extra_time_menit
            and d <= ref_dist + max_extra_distance_meter
        )
        lf = float(f.get("rata_kepadatan", 0.0) or 0.0)
        cat_rank = DENSITY_CATEGORY_ORDER[density_category(lf)]
        primary = float(f.get("primary_score", 0.0) or 0.0)
        return (0 if within_cap else 1, cat_rank, lf, primary)

    ordered = sorted(routes, key=_sort_key)
    for r in ordered:
        f = key_fn(r)
        lf = float(f.get("rata_kepadatan", 0.0) or 0.0)
        cat = density_category(lf)
        f["kategori_kepadatan"] = cat
        f["kategori_rank"] = DENSITY_CATEGORY_ORDER[cat]
    return ordered


def _bus_selection_score(
    kepadatan: float,
    eta_menit: int,
    earliest_eta_menit: int,
    max_extra_wait_menit: int,
) -> dict[str, float]:
    kepadatan_norm = min(max(float(kepadatan), 0.0), 1.0)
    extra_wait_menit = max(0, eta_menit - earliest_eta_menit)
    extra_wait_norm = min(extra_wait_menit / max(1, max_extra_wait_menit), 1.0)
    score = (
        BUS_SCORE_DENSITY_WEIGHT * kepadatan_norm
        + BUS_SCORE_WAIT_WEIGHT * extra_wait_norm
    )
    return {
        "score": score,
        "kepadatan_norm": kepadatan_norm,
        "earliest_eta_menit": earliest_eta_menit,
        "extra_wait_menit": extra_wait_menit,
        "extra_wait_norm": extra_wait_norm,
    }


def _eta_menit_ke_halte(
    stops: list[dict],
    halte_id: str,
    koridor_id: int,
    sim_time: int,
    max_eta_detik: int = MAX_ETA_DETIK_DEFAULT,
) -> int | None:
    """ETA dalam menit dari sim_time sampai bus tiba di halte_id.

    Pakai waktu_tiba_detik dari jadwal — primitif yang sama dipakai oleh
    services/interpolation.py:get_bus_position (untuk eta_minutes ke next_stop)
    dan routers/rute.py:bus_berikutnya. Tidak ada perhitungan paralel di sini.

    Return None bila bus sudah lewat halte_naik di sim_time, atau halte tidak
    ada di jadwal bus tsb.
    """
    for stop in stops:
        if stop.get("halte_id") != halte_id:
            continue
        if stop.get("koridor_id") != koridor_id:
            continue
        eta_detik = stop["waktu_tiba_detik"] - sim_time
        if eta_detik < 0:
            continue  # kunjungan sebelumnya sudah lewat; cari yang berikut
        if eta_detik > max_eta_detik:
            continue  # hindari trip besok / kandidat yang terlalu jauh
        return round(eta_detik / 60)
    return None


def _find_stop_time(
    stops: list[dict],
    halte_id: str,
    koridor_id: int,
    after_detik: int | None = None,
) -> int | None:
    """Waktu tiba (detik) bus di halte_id untuk koridor_id.

    Bila after_detik diberikan, hanya kunjungan dengan waktu_tiba_detik >=
    after_detik yang dikembalikan (untuk menghindari kunjungan sebelum naik).
    Return None bila stop tidak ditemukan.
    """
    for stop in stops:
        if stop.get("halte_id") != halte_id:
            continue
        if stop.get("koridor_id") != koridor_id:
            continue
        tiba = int(stop.get("waktu_tiba_detik", 0))
        if after_detik is not None and tiba < after_detik:
            continue
        return tiba
    return None


def collect_bus_candidates(
    jadwal: dict[str, list[dict]],
    realtime_kepadatan: dict[str, float],
    koridor_id: int,
    halte_naik: str,
    reference_time: int,
    max_eta_menit: int = MAX_ETA_MENIT_DEFAULT,
) -> list[dict]:
    """Kumpulkan kandidat bus untuk satu blok 'naik'.

    Logika filter sama persis dengan loop kandidat di select_bus_per_segmen:
    bus harus punya entri realtime_kepadatan dan ETA valid (belum lewat, tidak
    lebih dari max_eta_menit) dihitung dari reference_time. Dipakai juga oleh
    screen_bus_scenarios.py supaya klasifikasi bus-level memakai definisi
    kandidat yang sama dengan produksi.
    """
    bus_per_koridor: dict[int, list[str]] = defaultdict(list)
    for bus_id, stops in jadwal.items():
        if not stops:
            continue
        bus_per_koridor[stops[0]["koridor_id"]].append(bus_id)

    kandidat: list[dict] = []
    for bus_id in bus_per_koridor.get(koridor_id, []):
        kepadatan = realtime_kepadatan.get(bus_id)
        if kepadatan is None:
            continue
        eta = _eta_menit_ke_halte(
            jadwal[bus_id],
            halte_naik,
            koridor_id,
            reference_time,
            max_eta_detik=max_eta_menit * 60,
        )
        if eta is None:
            continue
        kandidat.append({
            "bus_id": bus_id,
            "kepadatan": float(kepadatan),
            "eta_menit": eta,
        })
    return kandidat


def select_bus_per_segmen(
    segmen_list: list[dict],
    sim_time: int,
    jadwal: dict[str, list[dict]],
    realtime_kepadatan: dict[str, float],
    max_eta_menit: int = MAX_ETA_MENIT_DEFAULT,
    max_extra_wait_menit: int = MAX_EXTRA_WAIT_MENIT_DEFAULT,
) -> list[dict]:
    """Inject `bus_rekomendasi` ke tiap segmen tipe='naik' (mutasi in-place).

    Args:
        segmen_list: list segmen hasil format_rute (campuran 'naik' & 'transit').
        sim_time: detik sim saat ini (dipakai filter bus yang belum lewat &
            untuk hitung ETA).
        jadwal: dict bus_id -> list stop (urut per urutan), sama dengan
            app.state.jadwal.
        realtime_kepadatan: dict bus_id -> kepadatan (0..1) pada jam request.
            Bus tanpa entri di sini akan diabaikan (tidak masuk kandidat).

    Bus tanpa kandidat valid -> `bus_rekomendasi: None` (frontend graceful).
    """
    # Index bus per koridor sekali, dipakai ulang untuk setiap segmen 'naik'.
    # (logika kandidat dipindah ke collect_bus_candidates agar identik dengan
    # screen_bus_scenarios.py)
    leg_clock_detik = sim_time

    for segmen in segmen_list:
        if segmen.get("tipe") != "naik":
            continue

        koridor_id = segmen["koridor_id"]
        halte_naik = segmen["naik_di_id"]

        kandidat = collect_bus_candidates(
            jadwal,
            realtime_kepadatan,
            koridor_id,
            halte_naik,
            reference_time=leg_clock_detik,
            max_eta_menit=max_eta_menit,
        )

        if not kandidat:
            segmen["bus_rekomendasi"] = None
            continue

        earliest_eta = min(b["eta_menit"] for b in kandidat)
        earliest_candidates = [b for b in kandidat if b["eta_menit"] == earliest_eta]
        earliest_best = min(
            earliest_candidates,
            key=lambda b: (round(b["kepadatan"], KEPADATAN_DECIMAL), b["bus_id"]),
        )
        kandidat_layak = [
            b for b in kandidat
            if b["eta_menit"] <= earliest_eta + max_extra_wait_menit
        ]
        for bus in kandidat_layak:
            bus.update(_bus_selection_score(
                bus["kepadatan"],
                bus["eta_menit"],
                earliest_eta,
                max_extra_wait_menit,
            ))

        if earliest_best["kepadatan"] <= SAFE_NEXT_BUS_DENSITY_THRESHOLD:
            earliest_best.update(_bus_selection_score(
                earliest_best["kepadatan"],
                earliest_best["eta_menit"],
                earliest_eta,
                max_extra_wait_menit,
            ))
            terbaik = earliest_best
            selection_reason = "next_bus_safe_density"
        else:
            kandidat_layak.sort(key=lambda b: (
                b["score"],
                b["eta_menit"],
                round(b["kepadatan"], KEPADATAN_DECIMAL),
            ))
            terbaik = kandidat_layak[0]
            selection_reason = "bus_score"

        segmen["bus_rekomendasi"] = {
            "bus_id": terbaik["bus_id"],
            "kepadatan": round(terbaik["kepadatan"], 3),
            # Nilai mentah sebelum pembulatan. Dipakai konsumen yang butuh
            # perbandingan presisi (metrik sukses) agar pembulatan 3 desimal
            # tidak menciptakan delta palsu antar bus.
            "kepadatan_raw": float(terbaik["kepadatan"]),
            "label_kepadatan": _label_kepadatan(terbaik["kepadatan"]),
            "kategori_kepadatan": _kategori_kepadatan(terbaik["kepadatan"]),
            "eta_menit": terbaik["eta_menit"],
            "selection_score": round(terbaik["score"], 4),
            "selection_reason": selection_reason,
            "safe_density_threshold": SAFE_NEXT_BUS_DENSITY_THRESHOLD,
            "earliest_eta_menit": terbaik["earliest_eta_menit"],
            "extra_wait_menit": terbaik["extra_wait_menit"],
            "extra_wait_norm": round(terbaik["extra_wait_norm"], 3),
            "estimated_passengers": round(terbaik["kepadatan"] * BUS_CAPACITY, 2),
            "capacity": BUS_CAPACITY,
            "candidate_count": len(kandidat),
            "considered_candidate_count": len(kandidat_layak),
            "candidate_debug": [
                {
                    "bus_id": bus["bus_id"],
                    "eta_menit": bus["eta_menit"],
                    "kepadatan": round(bus["kepadatan"], 3),
                    "score": round(bus.get("score", 0.0), 4),
                }
                for bus in sorted(
                    kandidat_layak,
                    key=lambda b: (b["eta_menit"], round(b["kepadatan"], KEPADATAN_DECIMAL)),
                )[:5]
            ],
        }

        # --- Journey clock (masalah #9): majukan jam ke kedatangan bus terpilih
        # di halte turun, supaya kaki berikutnya menghitung ETA dari waktu
        # benar-benar sampai di titik transit, bukan dari sim_time global.
        turun_di_id = segmen.get("turun_di_id")
        terbaik_eta_detik = terbaik["eta_menit"] * 60
        arrival_at_turun = None
        if turun_di_id:
            arrival_at_turun = _find_stop_time(
                jadwal[terbaik["bus_id"]],
                turun_di_id,
                koridor_id,
                after_detik=leg_clock_detik,
            )
        if arrival_at_turun is None:
            # Fallback: leg_clock + wait + akumulasi waktu_tempuh_detik segmen.
            segmen_waktu_total = sum(
                d.get("waktu_menit", 0) * 60
                for d in segmen.get("segmen_detail", [])
            )
            arrival_at_turun = leg_clock_detik + terbaik_eta_detik + segmen_waktu_total

        transfer_wait_menit = max(
            0,
            round((arrival_at_turun - leg_clock_detik) / 60) - terbaik["eta_menit"],
        )
        segmen["bus_rekomendasi"]["transfer_wait_menit"] = transfer_wait_menit
        segmen["bus_rekomendasi"]["leg_clock_detik"] = leg_clock_detik

        leg_clock_detik = arrival_at_turun + TRANSFER_WALK_PENALTY_DETIK

    return segmen_list


def apply_selected_bus_density(formatted: dict) -> dict:
    """Hitung ulang kepadatan rute setelah bus_rekomendasi dipilih.

    Ini menyelaraskan implementasi dengan Bab 4.6.2: kepadatan rute memakai
    load factor trip/bus yang benar-benar direkomendasikan pada tiap segmen
    naik. Jika bus tidak tersedia, fallback ke kepadatan edge yang sudah ada.

    Dipakai bersama oleh routers/rute.py (rekomendasi deterministik) dan
    services/monte_carlo.py (routing sensitivity per replikasi) agar kedua
    alur memakai definisi kepadatan rute yang sama persis.
    """
    naik_items = [s for s in formatted["segmen"] if s.get("tipe") == "naik"]
    density_values: list[float] = []
    selected_count = 0

    for item in naik_items:
        rek = item.get("bus_rekomendasi")
        if rek is not None and rek.get("kepadatan") is not None:
            density = float(rek["kepadatan"])
            selected_count += 1
            item["kepadatan"] = round(density, 3)
        else:
            density = float(item.get("kepadatan", 0.0))
        density_values.append(density)

    if not density_values:
        return formatted

    rata_kepadatan = sum(density_values) / len(density_values)

    formatted["rata_kepadatan"] = round(rata_kepadatan, 3)
    density_norm = min(rata_kepadatan, 1.0)
    formatted["density_norm"] = round(density_norm, 3)
    formatted["skor"] = round(density_norm, 4)
    formatted["ranking_phase_2"] = {
        "rata_kepadatan": round(rata_kepadatan, 3),
        "density_norm": round(density_norm, 3),
    }
    formatted["density_source"] = (
        "selected_bus"
        if selected_count == len(density_values)
        else "mixed_edge_fallback"
    )
    return formatted
