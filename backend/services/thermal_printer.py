"""Cetak ke printer thermal ESC/POS lewat port serial Bluetooth (SPP) milik Windows.

Printer murah seperti RPP02N dipasangkan lewat Bluetooth Classic dan Windows membuatkan port
COM untuknya, tetapi tanpa driver printer sehingga `window.print()` tidak bisa memakainya.
Port itu dibuka sebagai file biner dan diisi perintah ESC/POS mentah. Baud rate tidak
berpengaruh pada tautan Bluetooth, jadi tidak perlu pyserial.
"""

import os
import re
import textwrap
import threading
import time
from dataclasses import dataclass

PORT_DEFAULT = "COM13"
# Font A printer 80 mm: 12 dot per karakter, jadi 576 dot = 48 kolom.
KOLOM_TEKS = 48
LEBAR_MAKS_DOT = 576
TINGGI_MAKS_DOT = 3000
# Printer kecil punya buffer terbatas: raster dikirim per pita lalu diberi jeda, bukan sekali jalan.
_BARIS_PER_PITA = 64
_JEDA_PITA_DETIK = 0.08
_KUNCI = threading.Lock()


class PrinterGagal(Exception):
    """Printer tidak bisa dihubungi atau menolak data."""


def nama_port() -> str:
    # Dibaca saat dipanggil, bukan saat import: .env baru dimuat setelah modul ini di-import.
    port = os.getenv("PRINTER_PORT", "").strip() or PORT_DEFAULT
    if not re.fullmatch(r"COM\d{1,3}", port):
        raise PrinterGagal(f"PRINTER_PORT tidak valid: {port!r}")
    return port


def _teks_ascii(teks: str) -> bytes:
    return "".join(c if 32 <= ord(c) < 127 else "?" for c in teks).encode("ascii")


@dataclass(frozen=True)
class BarisTeks:
    """Satu baris struk teks. `kanan` diisi bila baris berbentuk "label ..... nilai"."""

    teks: str = ""
    kanan: str = ""
    tebal: bool = False
    besar: bool = False  # judul: tinggi dua kali, lebar kolom tetap
    tengah: bool = False
    garis: bool = False


def _tata_baris(b: BarisTeks, kolom: int) -> list[str]:
    """Pecah satu BarisTeks menjadi baris-baris selebar `kolom` (teks ASCII)."""
    if b.garis:
        return ["-" * kolom]
    teks, kanan = _teks_ascii(b.teks).decode(), _teks_ascii(b.kanan).decode()
    if kanan:
        if len(teks) + 1 + len(kanan) <= kolom:
            return [teks + " " * (kolom - len(teks) - len(kanan)) + kanan]
        # Terlalu panjang untuk satu baris: label dibungkus, nilai rata kanan di baris sendiri.
        kiri = textwrap.wrap(teks, kolom) if teks else []
        return kiri + [x.rjust(kolom) for x in textwrap.wrap(kanan, kolom)]
    baris = textwrap.wrap(teks, kolom) or [""]
    return [x.center(kolom).rstrip() for x in baris] if b.tengah else baris


def susun_escpos_teks(baris: list[BarisTeks], kolom: int = KOLOM_TEKS) -> bytes:
    """Struk teks ESC/POS: tiap BarisTeks ditata ke `kolom` karakter lalu dicetak apa adanya.

    Karakter Font A 1x; baris `besar` (judul) hanya dua kali tinggi, jadi lebar kolom tetap."""
    out = bytearray(b"\x1b\x40")  # ESC @: reset
    for b in baris:
        # ESC E n: tebal. GS ! n: ukuran karakter (0x01 = tinggi dua kali).
        gaya_awal = (b"\x1b\x45\x01" if b.tebal else b"") + (b"\x1d\x21\x01" if b.besar else b"")
        gaya_akhir = (b"\x1d\x21\x00" if b.besar else b"") + (b"\x1b\x45\x00" if b.tebal else b"")
        for teks in _tata_baris(b, kolom):
            out += gaya_awal + _teks_ascii(teks) + gaya_akhir + b"\n"
    out += b"\n\n\n\n"  # dorong kertas keluar dari kepala cetak
    return bytes(out)


def susun_escpos(lebar: int, tinggi: int, bits: bytes, baris: list[str]) -> bytes:
    """Bungkus bitmap 1-bit (bit 1 = hitam, per baris dibulatkan ke byte) menjadi struk."""
    byte_per_baris = lebar // 8
    if lebar % 8 or len(bits) != byte_per_baris * tinggi:
        raise ValueError("ukuran bitmap tidak cocok dengan lebar x tinggi")

    out = bytearray(b"\x1b\x40")  # ESC @: reset
    pita: list[bytes] = []
    for y in range(0, tinggi, _BARIS_PER_PITA):
        n = min(_BARIS_PER_PITA, tinggi - y)
        # GS v 0 m xL xH yL yH: raster bit image, m=0 skala normal.
        kepala = b"\x1d\x76\x30\x00" + byte_per_baris.to_bytes(2, "little") + n.to_bytes(2, "little")
        pita.append(kepala + bits[y * byte_per_baris : (y + n) * byte_per_baris])
    out += b"".join(pita)
    out += b"\n"
    for b in baris:
        out += _teks_ascii(b) + b"\n"
    out += b"\n\n\n\n"  # dorong kertas keluar dari kepala cetak
    return bytes(out)


def _tulis_port(port: str, data: bytes, jeda: float) -> None:
    """Tulis ke port COM via Win32. Port serial wajib dibuka eksklusif (share mode 0), sedangkan
    open()/os.open() Python selalu memakai share baca/tulis sehingga ditolak "Permission denied"."""
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    k32.WriteFile.argtypes = [wintypes.HANDLE, wintypes.LPCVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]

    generic_write, open_existing = 0x40000000, 3
    handle = k32.CreateFileW("\\\\.\\" + port, generic_write, 0, None, open_existing, 0, None)
    if handle in (None, ctypes.c_void_p(-1).value):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        for awal in range(0, len(data), 2048):
            potong = data[awal : awal + 2048]
            ditulis = wintypes.DWORD(0)
            if not k32.WriteFile(handle, potong, len(potong), ctypes.byref(ditulis), None):
                raise ctypes.WinError(ctypes.get_last_error())
            time.sleep(jeda)
    finally:
        k32.CloseHandle(handle)


def kirim(data: bytes, *, jeda_pita: float = _JEDA_PITA_DETIK) -> None:
    """Tulis ke printer. Satu cetakan sekali jalan; permintaan lain menunggu giliran."""
    port = nama_port()
    with _KUNCI:
        try:
            _tulis_port(port, data, jeda_pita)
        except OSError as exc:
            raise PrinterGagal(f"Printer di {port} tidak dapat dihubungi: {exc}") from exc
