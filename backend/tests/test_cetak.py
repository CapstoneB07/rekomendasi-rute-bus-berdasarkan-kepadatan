import base64

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import cetak
from services import thermal_printer

app = FastAPI()
app.include_router(cetak.router)
client = TestClient(app)


def _body(lebar=16, tinggi=2, **extra):
    bits = bytes(range(lebar // 8 * tinggi))
    return {"lebar": lebar, "tinggi": tinggi, "bits_b64": base64.b64encode(bits).decode(), **extra}


def test_susun_escpos_membungkus_raster_dan_teks():
    bits = bytes([0xFF, 0x00, 0x0F, 0xF0])  # 16 dot x 2 baris
    data = thermal_printer.susun_escpos(16, 2, bits, ["Bus: CV-1", "Jam \u00e9"])
    assert data.startswith(b"\x1b\x40")
    assert b"\x1d\x76\x30\x00\x02\x00\x02\x00" + bits in data  # 2 byte/baris, 2 baris
    assert b"Bus: CV-1\n" in data and b"Jam ?\n" in data  # non-ASCII diganti
    assert data.endswith(b"\n\n\n\n")


def test_susun_escpos_memecah_pita_64_baris():
    tinggi = 130
    data = thermal_printer.susun_escpos(8, tinggi, bytes(tinggi), [])
    assert data.count(b"\x1d\x76\x30\x00") == 3  # 64 + 64 + 2


def test_susun_escpos_menolak_ukuran_tidak_cocok():
    with pytest.raises(ValueError):
        thermal_printer.susun_escpos(16, 2, b"\x00", [])


def test_cetak_foto_mengirim_ke_printer(monkeypatch):
    terkirim = []
    monkeypatch.setattr(thermal_printer, "kirim", terkirim.append)
    r = client.post("/api/print/foto", json=_body(baris=["Terdeteksi 7"]))
    assert r.status_code == 200 and r.json() == {"status": "ok"}
    assert len(terkirim) == 1 and b"Terdeteksi 7" in terkirim[0]


def test_cetak_foto_bitmap_tidak_cocok_400(monkeypatch):
    monkeypatch.setattr(thermal_printer, "kirim", lambda d: pytest.fail("tidak boleh mencetak"))
    body = _body()
    body["bits_b64"] = base64.b64encode(b"\x00").decode()
    assert client.post("/api/print/foto", json=body).status_code == 400
    body["bits_b64"] = "bukan base64!!"
    assert client.post("/api/print/foto", json=body).status_code == 400


def test_cetak_foto_validasi_ukuran_422():
    assert client.post("/api/print/foto", json=_body(lebar=12)).status_code == 422  # bukan kelipatan 8
    assert client.post("/api/print/foto", json=_body(lebar=584)).status_code == 422  # > 576 dot


def test_cetak_foto_printer_gagal_503(monkeypatch):
    def gagal(_data):
        raise thermal_printer.PrinterGagal("Printer di COM13 tidak dapat dihubungi")

    monkeypatch.setattr(thermal_printer, "kirim", gagal)
    r = client.post("/api/print/foto", json=_body())
    assert r.status_code == 503 and "COM13" in r.json()["detail"]


def test_nama_port_default_env_dan_validasi(monkeypatch):
    monkeypatch.delenv("PRINTER_PORT", raising=False)
    assert thermal_printer.nama_port() == "COM13"
    monkeypatch.setenv("PRINTER_PORT", "COM5")
    assert thermal_printer.nama_port() == "COM5"
    monkeypatch.setenv("PRINTER_PORT", "C:\\evil")
    with pytest.raises(thermal_printer.PrinterGagal):
        thermal_printer.nama_port()
