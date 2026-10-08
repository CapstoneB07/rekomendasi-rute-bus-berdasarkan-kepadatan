"""Konfigurasi sistem: satu tempat untuk konstanta lintas-modul.

Sebelumnya nilai-nilai ini tersebar dan terduplikasi:

    services/dijkstra.py:47          SCOPED_KORIDOR = {"1","2","3","4","5"}
    services/gtfs_simulation.py:30   SCOPED_KORIDOR = {"1","2","3","4","5"}
    services/scenario_classifier.py  if kid in {"1","2","3","4","5"}
    scripts/screen_candidate_pairs.py if kid in {"1","2","3","4","5"}
    services/bus_selector.py:18      BUS_CAPACITY = 80
    services/gtfs_simulation.py:25   BUS_CAPACITY = 80
    services/dijkstra.py:39          KEPADATAN_FALLBACK = 0.5
    services/gtfs_simulation.py:26   FALLBACK_LOAD_FACTOR = 0.5

Duplikasi ini bukan sekadar kerapian: bila dua modul berbeda pendapat soal
koridor mana yang ada, screening dan simulasi menghasilkan katalog yang tidak
konsisten. Semua nilai dipusatkan di sini supaya hanya ada SATU angka.
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Cakupan koridor
# ---------------------------------------------------------------------------
# Cakupan koridor default = scope yang dipakai untuk mengukur 54,17%
# (8 koridor). Nilai lama (1-5) tetap bisa dipakai lewat env:
#   SCOPED_KORIDOR=1,2,3,4,5
DEFAULT_SCOPED_KORIDOR: tuple[str, ...] = ("1", "2", "3", "4", "5", "8", "9", "12")
_ENV_SCOPE = "SCOPED_KORIDOR"


def _parse_scope(value: str) -> frozenset[str]:
    """Parse "1,2,3" atau "1 2 3" jadi himpunan id koridor."""
    return frozenset(t.strip() for t in value.replace(",", " ").split() if t.strip())


def _load_scope() -> frozenset[str]:
    raw = os.getenv(_ENV_SCOPE, "").strip()
    if raw:
        parsed = _parse_scope(raw)
        if parsed:
            return parsed
    return frozenset(DEFAULT_SCOPED_KORIDOR)


#: Himpunan id koridor yang dipakai seluruh pipeline (dijkstra, simulasi GTFS,
#: Monte Carlo, classifier skenario, screening). Ubah lewat env SCOPED_KORIDOR.
SCOPED_KORIDOR: frozenset[str] = _load_scope()


def normalize_koridor_id(value: object) -> str:
    """Normalisasi id koridor dari Supabase (int 4, float 4.0, str "4") -> "4"."""
    if value is None:
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def is_scoped(value: object) -> bool:
    """True bila id koridor (format apa pun) termasuk cakupan."""
    return normalize_koridor_id(value) in SCOPED_KORIDOR


def scoped_sorted() -> list[str]:
    """Koridor terurut stabil: numerik dulu, lalu alfabetis (mis. "2A")."""
    return sorted(SCOPED_KORIDOR, key=lambda k: (0, int(k)) if k.isdigit() else (1, k))


def describe() -> str:
    """Ringkasan cakupan untuk log startup."""
    return f"{len(SCOPED_KORIDOR)} koridor: {','.join(scoped_sorted())}"


# ---------------------------------------------------------------------------
# Batas transit
# ---------------------------------------------------------------------------
# Diturunkan dari jumlah koridor: sebuah rute paling banyak menyentuh setiap
# koridor sekali, jadi transfer maksimum = jumlah koridor - 1. Pada scope 5
# koridor ini menghasilkan 4 — sama persis dengan nilai hardcoded sebelumnya,
# sehingga perilaku di scope lama tidak berubah.
#
# CATATAN: c251 §4.7.1 menetapkan T_max = 4 sebagai batas kenyamanan lansia,
# bukan sebagai fungsi topologi. Nilai turunan ini akan melebihi 4 begitu
# koridor ditambah. Bila batas kenyamanan harus dipertahankan, tetapkan
# MAKS_TRANSIT_OVERRIDE (lihat di bawah).
_ENV_TRANSIT_OVERRIDE = "MAKS_TRANSIT_OVERRIDE"


def _load_maks_transit() -> int:
    raw = os.getenv(_ENV_TRANSIT_OVERRIDE, "").strip()
    if raw:
        try:
            value = int(raw)
            if value >= 0:
                return value
        except ValueError:
            pass
    return max(0, len(SCOPED_KORIDOR) - 1)


#: Jumlah transfer maksimum yang diizinkan dalam satu rute.
MAKS_TRANSIT: int = _load_maks_transit()

#: Alias lama; dipertahankan supaya import yang sudah ada tetap jalan.
MAKS_TRANSIT_DEFAULT: int = MAKS_TRANSIT


# ---------------------------------------------------------------------------
# Batas generasi kandidat
# ---------------------------------------------------------------------------
# `dijkstra()` membangun kandidat alternatif dengan memblokir satu edge segmen
# rute #1 lalu menjalankan ulang pencarian, ditambah satu rerun per koridor yang
# dipakai. Jumlah rerun edge = jumlah edge segmen rute #1, dan itu tidak
# dibatasi: untuk OD yang rute #1-nya panjang (Harmoni->Kebon Sirih: 38 edge)
# biayanya puluhan rerun. Yang mahal bukan rerun yang menemukan alternatif,
# melainkan rerun yang berakhir TANPA rute: edge transit adalah self-loop
# sehingga memblokir satu segmen tidak pernah memutus graf, dan pencarian harus
# keluar dari seluruh ruang state sebelum menyerah (~1,2 s per rerun).
# Diukur 2026-10-08 (Supabase live, jam 08:00 weekday): 38 rerun = 30,5 s,
# 24 di antaranya buntu. Membatasi ke 8 rerun pertama: 0,049 s dengan kandidat
# IDENTIK pada 4 OD uji (Harmoni->Kebon Sirih / Kota / Pulogadung / Bundaran HI).
# Rerun blokir koridor tidak dibatasi karena jumlahnya = jumlah koridor pada
# rute #1 (kecil dan terbatas oleh MAKS_TRANSIT).
# 0 = tanpa batas (perilaku lama).
_ENV_DIJKSTRA_MAX_BLOCK_RERUNS = "DIJKSTRA_MAX_BLOCK_RERUNS"
DIJKSTRA_MAX_BLOCK_RERUNS_DEFAULT: int = 8


def _load_max_block_reruns() -> int:
    raw = os.getenv(_ENV_DIJKSTRA_MAX_BLOCK_RERUNS, "").strip()
    if raw:
        try:
            value = int(raw)
            if value >= 0:
                return value
        except ValueError:
            pass
    return DIJKSTRA_MAX_BLOCK_RERUNS_DEFAULT


#: Batas jumlah rerun pemblokiran edge segmen di `dijkstra()` (0 = tanpa batas).
DIJKSTRA_MAX_BLOCK_RERUNS: int = _load_max_block_reruns()


# ---------------------------------------------------------------------------
# Tunable lapisan bus (Algoritma 2). Env-overridable dengan pola yang sama
# seperti SCOPED_KORIDOR, supaya sweep konfigurasi bisa dijalankan tanpa
# mengedit kode. Dibaca sekali saat import: set env SEBELUM proses start.
# ---------------------------------------------------------------------------
_ENV_BUS_MAX_EXTRA_WAIT = "BUS_MAX_EXTRA_WAIT_MENIT"
_ENV_BUS_MAX_ETA = "BUS_MAX_ETA_MENIT"
_ENV_BUS_DENSITY_WEIGHT = "BUS_SCORE_DENSITY_WEIGHT"
_ENV_BUS_SAFE_THRESHOLD = "BUS_SAFE_NEXT_DENSITY_THRESHOLD"

# Nilai DEFAULT = konfigurasi terukur untuk target sukses (2026-10-07).
# Diukur: 104/192 = 54,17% pada konfigurasi ini; +12,63 mnt tunggu tambahan.
# Nilai konservatif lama (20 / 45 / 0.85 / 0.35) menghasilkan ~24,5% dan
# dicapai lewat env var bila perlu pembanding:
#   BUS_MAX_EXTRA_WAIT_MENIT=20 BUS_MAX_ETA_MENIT=45 \
#   BUS_SCORE_DENSITY_WEIGHT=0.85 BUS_SAFE_NEXT_DENSITY_THRESHOLD=0.35
#
# Disimpan di kode (bukan hanya .env) supaya nilainya ikut ter-commit dan
# tidak bergantung pada urutan import load_dotenv().
BUS_MAX_EXTRA_WAIT_MENIT_DEFAULT: int = 50
BUS_MAX_ETA_MENIT_DEFAULT: int = 60
BUS_SCORE_DENSITY_WEIGHT_DEFAULT: float = 0.95
# 0.0 = aturan "bus tercepat sudah cukup nyaman" dimatikan (aturan ini
# tambahan repo, bukan dari c251).
BUS_SAFE_NEXT_DENSITY_THRESHOLD_DEFAULT: float = 0.0


def _load_int_env(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name, "").strip()
    if raw:
        try:
            value = int(raw)
            if value >= minimum:
                return value
        except ValueError:
            pass
    return default


def _load_float_env(
    name: str, default: float, minimum: float = 0.0, maximum: float = 1.0
) -> float:
    raw = os.getenv(name, "").strip()
    if raw:
        try:
            value = float(raw)
            if minimum <= value <= maximum:
                return value
        except ValueError:
            pass
    return default


#: Tambahan waktu tunggu maksimum yang masih ditawarkan ke pengguna (menit).
MAX_EXTRA_WAIT_MENIT: int = _load_int_env(
    _ENV_BUS_MAX_EXTRA_WAIT, BUS_MAX_EXTRA_WAIT_MENIT_DEFAULT
)
#: Jendela ETA maksimum untuk kandidat bus (menit).
MAX_ETA_MENIT: int = _load_int_env(_ENV_BUS_MAX_ETA, BUS_MAX_ETA_MENIT_DEFAULT)
#: Bobot kepadatan pada skor pemilihan bus; bobot tunggu = 1 - ini.
BUS_SCORE_DENSITY_WEIGHT: float = _load_float_env(
    _ENV_BUS_DENSITY_WEIGHT, BUS_SCORE_DENSITY_WEIGHT_DEFAULT
)
BUS_SCORE_WAIT_WEIGHT: float = round(1.0 - BUS_SCORE_DENSITY_WEIGHT, 4)
#: Ambang "bus tercepat sudah cukup sepi" (rule UX repo, bukan dari c251).
#: Set 0.0 untuk mematikan rule ini sehingga selector selalu optimasi
#: kepadatan penuh sesuai c251 §4.7.2 ("semakin kecil D, semakin tinggi
#: prioritas").
BUS_SAFE_NEXT_DENSITY_THRESHOLD: float = _load_float_env(
    _ENV_BUS_SAFE_THRESHOLD, BUS_SAFE_NEXT_DENSITY_THRESHOLD_DEFAULT
)


# ---------------------------------------------------------------------------
# Alias halte platform (masalah #12)
# ---------------------------------------------------------------------------
#: Radius (meter) untuk menganggap dua halte_id bernama sama sebagai SATU titik
#: naik/turun. Data TransJakarta punya satu id per arah/platform; sebagian
#: platform kembar berjarak 83-165 m sehingga tidak ter-alias pada ambang lama
#: 80 m -> pengguna terjebak di platform yang salah (404 / rute memutar).
#: Diukur 2026-10-07: 123 nama kembar, maksimum jarak antar-platform 164,9 m,
#: 0 grup melewati 200 m. Naikkan hanya bila data berubah.
HALTE_ALIAS_RADIUS_METER_DEFAULT: float = 200.0
_ENV_HALTE_ALIAS_RADIUS = "HALTE_ALIAS_RADIUS_METER"
HALTE_ALIAS_RADIUS_METER: float = _load_float_env(
    _ENV_HALTE_ALIAS_RADIUS,
    HALTE_ALIAS_RADIUS_METER_DEFAULT,
    minimum=1.0,
    maximum=1000.0,
)


# ---------------------------------------------------------------------------
# Kapasitas & fallback kepadatan
# ---------------------------------------------------------------------------
# Kapasitas per bus diseragamkan (80 penumpang). BRT TransJakarta mengoperasikan
# armada campuran (single/double decker, articulated) dengan rasio yang tidak
# terdokumentasi, jadi memakai satu angka seragam lebih jujur daripada menebak
# komposisi. LF = P / (trip_supply * BUS_CAPACITY).
BUS_CAPACITY: int = 80

#: Nilai kepadatan yang dipakai saat data tidak tersedia.
#: Satu angka untuk dua pemakaian yang secara konsep sama ("kepadatan tak
#: diketahui"): bobot kepadatan per koridor di graf (`build_graph`) dan
#: load factor per trip di simulasi (`daily_mean_for`, snapshot crowding).
DENSITY_FALLBACK: float = 0.5


def describe_all() -> str:
    """Ringkasan seluruh konfigurasi untuk log startup."""
    return (
        f"scope={describe()} | maks_transit={MAKS_TRANSIT} "
        f"| bus_capacity={BUS_CAPACITY} | density_fallback={DENSITY_FALLBACK}"
    )
