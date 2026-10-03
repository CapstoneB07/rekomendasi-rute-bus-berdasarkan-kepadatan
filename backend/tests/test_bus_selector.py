"""Unit test untuk services/bus_selector.py (Algoritma 2)."""

from services.bus_selector import (
    MAX_ETA_MENIT_DEFAULT,
    density_category,
    rerank_routes,
    select_bus_per_segmen,
)


def _jadwal_dummy() -> dict[str, list[dict]]:
    """Dua bus di koridor 1, satu bus di koridor 2.

    Semua tiba di halte 'A' tapi pada waktu berbeda.
    """
    return {
        "B-K1-01": [
            {"halte_id": "A", "koridor_id": 1, "waktu_tiba_detik": 8 * 3600 + 60},
            {"halte_id": "B", "koridor_id": 1, "waktu_tiba_detik": 8 * 3600 + 300},
        ],
        "B-K1-02": [
            {"halte_id": "A", "koridor_id": 1, "waktu_tiba_detik": 8 * 3600 + 600},
            {"halte_id": "B", "koridor_id": 1, "waktu_tiba_detik": 8 * 3600 + 900},
        ],
        "B-K2-01": [
            {"halte_id": "A", "koridor_id": 2, "waktu_tiba_detik": 8 * 3600 + 120},
        ],
    }


def test_pilih_bus_berdasarkan_kepadatan_terendah():
    """Dua bus di koridor sama: yang kepadatan lebih rendah harus terpilih,
    walau ETA-nya lebih lama."""
    segmen = [{
        "tipe": "naik",
        "koridor_id": 1,
        "naik_di_id": "A",
    }]
    jadwal = _jadwal_dummy()
    realtime = {"B-K1-01": 0.80, "B-K1-02": 0.20}  # bus-02 lebih sepi

    select_bus_per_segmen(segmen, sim_time=8 * 3600, jadwal=jadwal, realtime_kepadatan=realtime)
    rek = segmen[0]["bus_rekomendasi"]
    assert rek["bus_id"] == "B-K1-02"
    assert rek["label_kepadatan"] == "Sepi"
    assert rek["eta_menit"] == 10  # 600 detik / 60


def test_tiebreak_eta_saat_kepadatan_setara():
    """Kepadatan setara (perbedaan < epsilon 0.01) -> pilih ETA terkecil."""
    segmen = [{
        "tipe": "naik",
        "koridor_id": 1,
        "naik_di_id": "A",
    }]
    jadwal = _jadwal_dummy()
    # 0.30 vs 0.304 -> dibulatkan 2-decimal == 0.30 -> tie -> eta menang
    realtime = {"B-K1-01": 0.30, "B-K1-02": 0.304}

    select_bus_per_segmen(segmen, sim_time=8 * 3600, jadwal=jadwal, realtime_kepadatan=realtime)
    assert segmen[0]["bus_rekomendasi"]["bus_id"] == "B-K1-01"  # ETA 1 min < 10 min


def test_bus_yang_sudah_lewat_diabaikan():
    """Bus yang waktu_tiba_detik-nya < sim_time tidak boleh jadi kandidat."""
    segmen = [{
        "tipe": "naik",
        "koridor_id": 1,
        "naik_di_id": "A",
    }]
    jadwal = _jadwal_dummy()
    realtime = {"B-K1-01": 0.10, "B-K1-02": 0.50}
    # sim_time melewati bus-01 (tiba 8:00:60) tapi belum lewat bus-02 (8:10:00)
    select_bus_per_segmen(segmen, sim_time=8 * 3600 + 120, jadwal=jadwal, realtime_kepadatan=realtime)
    assert segmen[0]["bus_rekomendasi"]["bus_id"] == "B-K1-02"


def test_bus_terlalu_jauh_diabaikan_walau_lebih_sepi():
    """Trip besok/lintas hari yang sangat jauh tidak boleh menang dari bus dekat."""
    segmen = [{
        "tipe": "naik",
        "koridor_id": 1,
        "naik_di_id": "A",
    }]
    jadwal = {
        "B-DEKAT": [
            {"halte_id": "A", "koridor_id": 1, "waktu_tiba_detik": 5 * 3600 + 6 * 60},
        ],
        "B-BESOK": [
            {"halte_id": "A", "koridor_id": 1, "waktu_tiba_detik": 26 * 3600 + 10 * 60},
        ],
    }
    realtime = {"B-DEKAT": 0.60, "B-BESOK": 0.05}

    select_bus_per_segmen(segmen, sim_time=5 * 3600, jadwal=jadwal, realtime_kepadatan=realtime)

    rek = segmen[0]["bus_rekomendasi"]
    assert rek["bus_id"] == "B-DEKAT"
    assert rek["eta_menit"] == 6


def test_bus_di_atas_batas_eta_default_diabaikan():
    """Default selector hanya melihat kandidat sampai 45 menit dari sekarang."""
    segmen = [{
        "tipe": "naik",
        "koridor_id": 1,
        "naik_di_id": "A",
    }]
    jadwal = {
        "B-45-MENIT": [
            {
                "halte_id": "A",
                "koridor_id": 1,
                "waktu_tiba_detik": 7 * 3600 + MAX_ETA_MENIT_DEFAULT * 60,
            },
        ],
        "B-46-MENIT-SEPI": [
            {
                "halte_id": "A",
                "koridor_id": 1,
                "waktu_tiba_detik": 7 * 3600 + (MAX_ETA_MENIT_DEFAULT + 1) * 60,
            },
        ],
    }
    realtime = {"B-45-MENIT": 0.80, "B-46-MENIT-SEPI": 0.05}

    select_bus_per_segmen(segmen, sim_time=7 * 3600, jadwal=jadwal, realtime_kepadatan=realtime)

    rek = segmen[0]["bus_rekomendasi"]
    assert rek["bus_id"] == "B-45-MENIT"
    assert rek["eta_menit"] == MAX_ETA_MENIT_DEFAULT
    assert rek["candidate_count"] == 1


def test_bus_cepat_bisa_menang_dari_bus_jauh_yang_lebih_sepi():
    """Skor gabungan mencegah rekomendasi menunggu terlalu lama demi sepi."""
    segmen = [{
        "tipe": "naik",
        "koridor_id": 3,
        "naik_di_id": "PESAKIH",
    }]
    jadwal = {
        "BUS-CEPAT": [
            {"halte_id": "PESAKIH", "koridor_id": 3, "waktu_tiba_detik": 5 * 3600 + 8 * 60},
        ],
        "BUS-SEPI-JAUH": [
            {"halte_id": "PESAKIH", "koridor_id": 3, "waktu_tiba_detik": 5 * 3600 + 39 * 60},
        ],
    }
    realtime = {"BUS-CEPAT": 0.60, "BUS-SEPI-JAUH": 0.09}

    select_bus_per_segmen(segmen, sim_time=5 * 3600, jadwal=jadwal, realtime_kepadatan=realtime)

    rek = segmen[0]["bus_rekomendasi"]
    assert rek["bus_id"] == "BUS-CEPAT"
    assert rek["eta_menit"] == 8
    assert rek["extra_wait_menit"] == 0


def test_bus_lebih_sepi_dalam_tambahan_tunggu_wajar_bisa_menang():
    """Pada jam sibuk, menunggu sedikit lebih lama layak bila bus jauh lebih sepi."""
    segmen = [{
        "tipe": "naik",
        "koridor_id": 3,
        "naik_di_id": "PESAKIH",
    }]
    jadwal = {
        "BUS-CEPAT-PADAT": [
            {"halte_id": "PESAKIH", "koridor_id": 3, "waktu_tiba_detik": 8 * 3600 + 2 * 60},
        ],
        "BUS-LEBIH-SEPI": [
            {"halte_id": "PESAKIH", "koridor_id": 3, "waktu_tiba_detik": 8 * 3600 + 12 * 60},
        ],
    }
    realtime = {"BUS-CEPAT-PADAT": 0.74, "BUS-LEBIH-SEPI": 0.30}

    select_bus_per_segmen(segmen, sim_time=8 * 3600, jadwal=jadwal, realtime_kepadatan=realtime)

    rek = segmen[0]["bus_rekomendasi"]
    assert rek["bus_id"] == "BUS-LEBIH-SEPI"
    assert rek["eta_menit"] == 12
    assert rek["extra_wait_menit"] == 10


def test_bus_berikutnya_langsung_dipilih_jika_kepadatan_aman():
    """Kalau bus tercepat <= threshold aman 0.35, tidak perlu menunggu lagi."""
    segmen = [{
        "tipe": "naik",
        "koridor_id": 3,
        "naik_di_id": "PESAKIH",
    }]
    jadwal = {
        "BUS-CEPAT-AMAN": [
            {"halte_id": "PESAKIH", "koridor_id": 3, "waktu_tiba_detik": 9 * 3600 + 2 * 60},
        ],
        "BUS-LEBIH-SEPI": [
            {"halte_id": "PESAKIH", "koridor_id": 3, "waktu_tiba_detik": 9 * 3600 + 12 * 60},
        ],
    }
    realtime = {"BUS-CEPAT-AMAN": 0.35, "BUS-LEBIH-SEPI": 0.10}

    select_bus_per_segmen(segmen, sim_time=9 * 3600, jadwal=jadwal, realtime_kepadatan=realtime)

    rek = segmen[0]["bus_rekomendasi"]
    assert rek["bus_id"] == "BUS-CEPAT-AMAN"
    assert rek["eta_menit"] == 2
    assert rek["selection_reason"] == "next_bus_safe_density"


def test_jam_sibuk_selector_melihat_beberapa_bus_berikutnya():
    """Bus dua puluh menit lagi bisa dipilih jika jauh lebih lega dari bus pertama."""
    segmen = [{
        "tipe": "naik",
        "koridor_id": 3,
        "naik_di_id": "PESAKIH",
    }]
    jadwal = {
        "BUS-2-MENIT-PADAT": [
            {"halte_id": "PESAKIH", "koridor_id": 3, "waktu_tiba_detik": 9 * 3600 + 2 * 60},
        ],
        "BUS-8-MENIT-MASIH-PADAT": [
            {"halte_id": "PESAKIH", "koridor_id": 3, "waktu_tiba_detik": 9 * 3600 + 8 * 60},
        ],
        "BUS-18-MENIT-LEGA": [
            {"halte_id": "PESAKIH", "koridor_id": 3, "waktu_tiba_detik": 9 * 3600 + 18 * 60},
        ],
    }
    realtime = {
        "BUS-2-MENIT-PADAT": 0.74,
        "BUS-8-MENIT-MASIH-PADAT": 0.68,
        "BUS-18-MENIT-LEGA": 0.35,
    }

    select_bus_per_segmen(segmen, sim_time=9 * 3600, jadwal=jadwal, realtime_kepadatan=realtime)

    rek = segmen[0]["bus_rekomendasi"]
    assert rek["bus_id"] == "BUS-18-MENIT-LEGA"
    assert rek["eta_menit"] == 18
    assert rek["extra_wait_menit"] == 16


def test_tidak_ada_kandidat_return_none():
    """Tidak ada bus tersisa -> bus_rekomendasi=None (frontend graceful)."""
    segmen = [{
        "tipe": "naik",
        "koridor_id": 1,
        "naik_di_id": "A",
    }]
    jadwal = _jadwal_dummy()
    realtime = {"B-K1-01": 0.10, "B-K1-02": 0.50}
    # sim_time di luar jadwal semua bus
    select_bus_per_segmen(segmen, sim_time=20 * 3600, jadwal=jadwal, realtime_kepadatan=realtime)
    assert segmen[0]["bus_rekomendasi"] is None


def test_segmen_transit_tidak_disentuh():
    """Segmen tipe transit tidak boleh mendapat bus_rekomendasi."""
    segmen = [
        {"tipe": "transit", "transit_di": "C", "dari_koridor": 1, "ke_koridor": 2},
    ]
    select_bus_per_segmen(segmen, sim_time=8 * 3600, jadwal=_jadwal_dummy(), realtime_kepadatan={})
    assert "bus_rekomendasi" not in segmen[0]


def test_label_kepadatan_threshold():
    """Mapping label: <=0.33 Sepi, <=0.66 Sedang, >0.66 Padat."""
    base_segmen = {"tipe": "naik", "koridor_id": 2, "naik_di_id": "A"}
    jadwal = _jadwal_dummy()

    for kepadatan, label in [(0.20, "Sepi"), (0.50, "Sedang"), (0.90, "Padat")]:
        segmen = [dict(base_segmen)]
        select_bus_per_segmen(
            segmen,
            sim_time=8 * 3600,
            jadwal=jadwal,
            realtime_kepadatan={"B-K2-01": kepadatan},
        )
        assert segmen[0]["bus_rekomendasi"]["label_kepadatan"] == label


# ----------------------------------------------------------------------
# Part A (masalah #9): journey clock antar kaki perjalanan
# ----------------------------------------------------------------------

def _dua_kaki_dummy() -> tuple[list[dict], dict, dict]:
    """Kaki 1: A->C koridor 1. Kaki 2: C->E koridor 2.

    sim_time = 08:00:00. Bus K1-01 tiba A 08:05 dan C 08:20.
    Bus K2-01 tiba C 08:15 (terlalu mepet dari sudut sim_time kalau pakai
    sim_time global: ETA = 15 menit masih masuk jendela). Dengan journey clock,
    jam tiba C = 08:20, maka bus K2-01 sudah lewat -> kandidat harus gugur.
    """
    sim_time = 8 * 3600
    segmen = [
        {
            "tipe": "naik",
            "koridor_id": 1,
            "naik_di_id": "A",
            "turun_di_id": "C",
            "segmen_detail": [
                {"dari_id": "A", "ke_id": "B", "waktu_menit": 5},
                {"dari_id": "B", "ke_id": "C", "waktu_menit": 5},
            ],
        },
        {
            "tipe": "naik",
            "koridor_id": 2,
            "naik_di_id": "C",
            "turun_di_id": "E",
            "segmen_detail": [{"dari_id": "C", "ke_id": "E", "waktu_menit": 5}],
        },
    ]
    jadwal = {
        "B-K1-01": [
            {"halte_id": "A", "koridor_id": 1, "waktu_tiba_detik": 8 * 3600 + 5 * 60},
            {"halte_id": "B", "koridor_id": 1, "waktu_tiba_detik": 8 * 3600 + 12 * 60},
            {"halte_id": "C", "koridor_id": 1, "waktu_tiba_detik": 8 * 3600 + 20 * 60},
        ],
        "B-K2-01": [
            {"halte_id": "C", "koridor_id": 2, "waktu_tiba_detik": 8 * 3600 + 15 * 60},
            {"halte_id": "E", "koridor_id": 2, "waktu_tiba_detik": 8 * 3600 + 20 * 60},
        ],
        "B-K2-02": [
            {"halte_id": "C", "koridor_id": 2, "waktu_tiba_detik": 8 * 3600 + 25 * 60},
            {"halte_id": "E", "koridor_id": 2, "waktu_tiba_detik": 8 * 3600 + 30 * 60},
        ],
    }
    realtime = {
        "B-K1-01": 0.30,
        "B-K2-01": 0.30,
        "B-K2-02": 0.30,
    }
    return segmen, jadwal, realtime, sim_time


def test_transfer_leg_eta_uses_previous_arrival_clock():
    """ETA kaki kedua dihitung dari kedatangan kaki pertama, bukan sim_time."""
    segmen, jadwal, realtime, sim_time = _dua_kaki_dummy()
    select_bus_per_segmen(segmen, sim_time=sim_time, jadwal=jadwal, realtime_kepadatan=realtime)

    rek1 = segmen[0]["bus_rekomendasi"]
    rek2 = segmen[1]["bus_rekomendasi"]

    assert rek1["bus_id"] == "B-K1-01"
    assert rek1["eta_menit"] == 5  # 08:05 - 08:00

    # Dengan journey clock, jam berdiri di C = 08:20 (bukan 08:00). Bus K2-01
    # sudah lewat, bus K2-02 (08:25) yang tersedia -> ETA 5 menit dari 08:20.
    assert rek2["bus_id"] == "B-K2-02"
    assert rek2["eta_menit"] == 5
    assert rek2["leg_clock_detik"] == 8 * 3600 + 20 * 60


def test_transfer_wait_can_shift_bus_choice_outside_window():
    """Bus yang terlihat tersedia dari sim_time global bisa gugur karena sudah
    lewat saat penumpang benar-benar tiba di titik transfer."""
    segmen, jadwal, realtime, sim_time = _dua_kaki_dummy()

    # Buat K2-02 jauh lebih sepi: kalau K2-01 masih dianggap tersedia (sim_time
    # global), K2-01 menang karena lebih dulu; dengan journey clock K2-01 gugur
    # dan K2-02 yang menang.
    realtime["B-K2-01"] = 0.10
    realtime["B-K2-02"] = 0.90
    select_bus_per_segmen(segmen, sim_time=sim_time, jadwal=jadwal, realtime_kepadatan=realtime)

    rek2 = segmen[1]["bus_rekomendasi"]
    assert rek2["bus_id"] == "B-K2-02"
    assert rek2["leg_clock_detik"] == 8 * 3600 + 20 * 60


def test_first_leg_uses_sim_time_unchanged():
    """Kaki pertama tetap menghitung ETA dari sim_time global."""
    segmen, jadwal, realtime, sim_time = _dua_kaki_dummy()
    select_bus_per_segmen(segmen, sim_time=sim_time, jadwal=jadwal, realtime_kepadatan=realtime)

    rek1 = segmen[0]["bus_rekomendasi"]
    assert rek1["leg_clock_detik"] == sim_time
    assert rek1["eta_menit"] == 5


# ----------------------------------------------------------------------
# Re-ranking kategori kepadatan (masalah #4)
# ----------------------------------------------------------------------

def test_density_category_thresholds():
    assert density_category(0.49) == "sepi"
    assert density_category(0.50) == "sedang"
    assert density_category(0.79) == "sedang"
    assert density_category(0.80) == "padat"
    assert density_category(0.99) == "padat"
    assert density_category(1.00) == "sangat_padat"
    assert density_category(1.30) == "sangat_padat"


def test_rerank_routes_sorts_by_density_category_first():
    """Rute sepi harus di atas rute padat meski primary_score-nya lebih besar."""
    routes = [
        {"estimasi_menit": 10, "total_jarak_meter": 1000, "rata_kepadatan": 0.90, "primary_score": 0.05},
        {"estimasi_menit": 12, "total_jarak_meter": 1200, "rata_kepadatan": 0.20, "primary_score": 0.50},
    ]
    ordered = rerank_routes(routes)
    assert ordered[0]["rata_kepadatan"] == 0.20
    assert ordered[0]["kategori_kepadatan"] == "sepi"
    assert ordered[1]["kategori_kepadatan"] == "padat"


def test_rerank_routes_less_crowded_wins_within_same_category():
    """Regresi route-level MC 2026-09-28 (pasangan A G00168 -> G00214).

    Dua rute sama-sama 'sepi' (0.39 vs 0.31). Rute yang lebih cepat punya
    primary_score lebih kecil, tetapi rute yang lebih sepi harus tetap menang:
    di dalam kategori yang sama, kepadatan kontinu memutus seri sebelum
    primary_score (c251 Eq 4.20).
    """
    routes = [
        {"estimasi_menit": 20, "total_jarak_meter": 5000, "rata_kepadatan": 0.39, "primary_score": 0.10},
        {"estimasi_menit": 21, "total_jarak_meter": 5200, "rata_kepadatan": 0.31, "primary_score": 0.60},
    ]
    ordered = rerank_routes(routes)
    assert ordered[0]["rata_kepadatan"] == 0.31
    assert [r["kategori_kepadatan"] for r in ordered] == ["sepi", "sepi"]


def test_rerank_routes_exact_density_tie_uses_primary_score():
    """Kategori DAN kepadatan sama -> primary_score terkecil menang."""
    routes = [
        {"estimasi_menit": 10, "total_jarak_meter": 1000, "rata_kepadatan": 0.30, "primary_score": 0.40},
        {"estimasi_menit": 12, "total_jarak_meter": 1200, "rata_kepadatan": 0.30, "primary_score": 0.10},
    ]
    ordered = rerank_routes(routes)
    assert ordered[0]["primary_score"] == 0.10


def test_rerank_routes_cap_penalizes_extreme_detour():
    """Rute sepi tapi jauh lebih lama/lebih jauh melebihi cap -> diturunkan."""
    routes = [
        # Tercepat & terpendek, tapi padat.
        {"estimasi_menit": 10, "total_jarak_meter": 1000, "rata_kepadatan": 0.90, "primary_score": 0.05},
        # Sepi tapi 40 menit lebih lama (melebihi cap 15 mnt).
        {"estimasi_menit": 50, "total_jarak_meter": 2000, "rata_kepadatan": 0.10, "primary_score": 0.90},
    ]
    ordered = rerank_routes(routes, max_extra_time_menit=15, max_extra_distance_meter=3000)
    assert ordered[0]["rata_kepadatan"] == 0.90  # padat tetap menang karena sepi melebihi cap


def test_rerank_routes_key_fn_extracts_formatted_dict():
    """key_fn dipakai untuk mengambil dict formatted dari item wrapper."""
    items = [
        {"formatted": {"estimasi_menit": 10, "total_jarak_meter": 1000, "rata_kepadatan": 0.90, "primary_score": 0.05}},
        {"formatted": {"estimasi_menit": 12, "total_jarak_meter": 1200, "rata_kepadatan": 0.20, "primary_score": 0.50}},
    ]
    ordered = rerank_routes(items, key_fn=lambda item: item["formatted"])
    assert ordered[0]["formatted"]["rata_kepadatan"] == 0.20
    assert ordered[0]["formatted"]["kategori_kepadatan"] == "sepi"
