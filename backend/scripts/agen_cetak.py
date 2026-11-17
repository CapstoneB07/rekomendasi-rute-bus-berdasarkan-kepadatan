"""Agen cetak: ambil cetakan dari antrean Supabase lalu tulis ke printer thermal di komputer ini.

Backend produksi (server) tidak terhubung ke printer, jadi dengan PRINT_MODE=antrean ia hanya
menaruh byte ESC/POS di tabel `antrean_cetak` (backend/sql/antrean_cetak.sql). Jalankan agen ini
di komputer yang ter-pairing dengan printer Bluetooth (port COM, lihat PRINTER_PORT) dan biarkan
terus hidup selama kiosk dipakai:

    cd backend
    .venv\\Scripts\\python scripts\\agen_cetak.py

Butuh SUPABASE_URL dan SUPABASE_SERVICE_ROLE_KEY di backend/.env. Cetakan yang menunggu lebih
dari 30 detik digugurkan oleh database, jadi menyalakan agen belakangan tidak mencetak ulang
antrean lama. Ctrl+C untuk berhenti.
"""

import base64
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import antrean_cetak, thermal_printer  # noqa: E402

JEDA_KOSONG_DETIK = 1.0
JEDA_GALAT_DETIK = 3.0

logger = logging.getLogger("agen_cetak")


def _catat(fungsi, *args) -> None:
    """Tulis hasil ke antrean. Dicoba beberapa kali: kertas sudah keluar, jangan sampai barisnya
    tertinggal 'mencetak' (browser mengira gagal lalu operator mencetak ulang)."""
    for percobaan in range(3):
        try:
            fungsi(*args)
            return
        except Exception as exc:
            logger.error("gagal mencatat hasil cetak (percobaan %d/3): %s: %s", percobaan + 1, type(exc).__name__, exc)
            time.sleep(JEDA_GALAT_DETIK)


def proses(baris: dict) -> None:
    """Cetak satu baris antrean dan catat hasilnya; gagal cetak tidak menghentikan agen."""
    id_cetak = baris["id"]
    try:
        thermal_printer.kirim(base64.b64decode(baris["data_b64"], validate=True))
    except (thermal_printer.PrinterGagal, ValueError) as exc:
        logger.warning("cetak #%s (%s) gagal: %s", id_cetak, baris["jenis"], exc)
        _catat(antrean_cetak.gagal, id_cetak, str(exc))
        return
    logger.info("cetak #%s (%s) selesai", id_cetak, baris["jenis"])
    _catat(antrean_cetak.selesai, id_cetak)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger.info("Agen cetak jalan; printer di %s. Ctrl+C untuk berhenti.", thermal_printer.nama_port())
    while True:
        try:
            baris = antrean_cetak.ambil()
            if baris is None:
                time.sleep(JEDA_KOSONG_DETIK)
                continue
            proses(baris)
        except KeyboardInterrupt:
            break
        except Exception as exc:  # jaringan/Supabase putus: coba lagi, jangan mati
            logger.error("antrean tidak terjangkau: %s: %s", type(exc).__name__, exc)
            time.sleep(JEDA_GALAT_DETIK)


if __name__ == "__main__":
    main()
