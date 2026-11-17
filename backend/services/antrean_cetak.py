"""Antrean cetak lewat Supabase (tabel `antrean_cetak`, skema: backend/sql/antrean_cetak.sql).

Dipakai saat backend tidak berada di komputer yang terhubung ke printer (produksi di server):
router menaruh byte ESC/POS di antrean, `scripts/agen_cetak.py` di komputer printer
mengambilnya. Aktif bila PRINT_MODE=antrean; selain itu backend mencetak langsung.
"""

import base64
import os

from services.supabase_client import get_client

TABEL = "antrean_cetak"


class AntreanGagal(Exception):
    """Supabase tidak terjangkau atau menolak operasi antrean."""


def aktif() -> bool:
    return os.getenv("PRINT_MODE", "").strip().lower() == "antrean"


def antre(jenis: str, data: bytes) -> int:
    """Taruh satu cetakan di antrean; mengembalikan id barisnya."""
    try:
        baris = get_client().table(TABEL).insert({"jenis": jenis, "data_b64": base64.b64encode(data).decode()}).execute().data
        return int(baris[0]["id"])
    except Exception as exc:
        raise AntreanGagal(f"Antrean cetak tidak tersedia: {type(exc).__name__}") from exc


def status(id_cetak: int) -> dict | None:
    """{"status", "galat"} satu cetakan, None bila tidak ada. Sekaligus menggugurkan yang kedaluwarsa."""
    try:
        baris = get_client().rpc("status_cetak", {"p_id": id_cetak}).execute().data
    except Exception as exc:
        raise AntreanGagal(f"Antrean cetak tidak tersedia: {type(exc).__name__}") from exc
    return baris[0] if baris else None


def ambil() -> dict | None:
    """Untuk agen cetak: ambil cetakan tertua dan tandai 'mencetak'. None bila antrean kosong."""
    baris = get_client().rpc("ambil_cetak").execute().data
    return baris[0] if baris else None


def selesai(id_cetak: int) -> None:
    get_client().table(TABEL).update({"status": "selesai", "data_b64": ""}).eq("id", id_cetak).execute()


def gagal(id_cetak: int, galat: str) -> None:
    get_client().table(TABEL).update({"status": "gagal", "galat": galat[:300], "data_b64": ""}).eq("id", id_cetak).execute()
