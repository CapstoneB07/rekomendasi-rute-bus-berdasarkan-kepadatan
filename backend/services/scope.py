"""Satu sumber kebenaran untuk cakupan koridor (scope) sistem.

Sebelumnya cakupan koridor di-hardcode di EMPAT tempat berbeda:

    services/dijkstra.py:47          SCOPED_KORIDOR = {"1","2","3","4","5"}
    services/gtfs_simulation.py:30   SCOPED_KORIDOR = {"1","2","3","4","5"}
    services/scenario_classifier.py  if kid in {"1","2","3","4","5"}
    scripts/screen_candidate_pairs.py if kid in {"1","2","3","4","5"}

Akibatnya menambah/menghapus koridor butuh edit di 4 file, dan mudah lupa
satu sehingga screening (yang memakai literal) tidak sepakat dengan simulasi
(yang memakai SCOPED_KORIDOR) — persis kelas bug yang membuat catalog kosong.

Modul ini jadi satu-satunya tempat daftar koridor ditulis. Ubah di sini
(atau lewat env `SCOPED_KORIDOR="1,2,3,4,5,8,9,12"`), dan seluruh sistem ikut.

Catatan desain: `MAKS_TRANSIT` TIDAK diturunkan dari jumlah koridor. Transit
maksimum adalah batasan pengalaman penumpang (lansia), bukan fungsi topologi —
lihat c251 (maksimum 4 transfer). Jumlah koridor boleh berubah tanpa mengubah
batas transit.
"""

from __future__ import annotations

import os

# Cakupan default bila env tidak diisi. Urutan tidak penting (ini himpunan),
# tetapi ditulis terurut supaya diff-nya enak dibaca.
DEFAULT_SCOPED_KORIDOR: tuple[str, ...] = ("1", "2", "3", "4", "5")

_ENV_VAR = "SCOPED_KORIDOR"


def _parse(value: str) -> frozenset[str]:
    """Parse "1,2,3" atau "1 2 3" jadi himpunan id koridor (string, tanpa spasi)."""
    cleaned = value.replace(",", " ").split()
    return frozenset(token.strip() for token in cleaned if token.strip())


def _load() -> frozenset[str]:
    raw = os.getenv(_ENV_VAR, "").strip()
    if raw:
        parsed = _parse(raw)
        if parsed:
            return parsed
    return frozenset(DEFAULT_SCOPED_KORIDOR)


#: Himpunan id koridor yang dipakai seluruh pipeline (dijkstra, simulasi GTFS,
#: Monte Carlo, classifier skenario, screening).
SCOPED_KORIDOR: frozenset[str] = _load()


def normalize_koridor_id(value: object) -> str:
    """Normalisasi id koridor dari Supabase (int 4, float 4.0, str "4") -> "4".

    Satu implementasi untuk seluruh sistem; sebelumnya ada dua salinan
    identik di `dijkstra.py` dan `gtfs_simulation.py`.
    """
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
    """Daftar koridor terurut stabil: numerik dulu, lalu alfabetis (mis. "2A")."""
    return sorted(SCOPED_KORIDOR, key=lambda k: (0, int(k)) if k.isdigit() else (1, k))


def describe() -> str:
    """Ringkasan cakupan untuk log startup."""
    return f"{len(SCOPED_KORIDOR)} koridor: {','.join(scoped_sorted())}"
