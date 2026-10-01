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
DEFAULT_SCOPED_KORIDOR: tuple[str, ...] = ("1", "2", "3", "4", "5")
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
