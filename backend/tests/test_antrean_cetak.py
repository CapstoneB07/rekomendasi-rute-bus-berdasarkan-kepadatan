import base64
import importlib.util
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import cetak
from services import antrean_cetak, thermal_printer

app = FastAPI()
app.include_router(cetak.router)
client = TestClient(app)


class KlienPalsu:
    """Meniru bagian supabase-py yang dipakai: table().insert/update().eq().execute() dan rpc().execute()."""

    def __init__(self, data=None, galat=None):
        self.data, self.galat, self.panggilan = data, galat, []

    def _hasil(self):
        if self.galat:
            raise self.galat
        return type("R", (), {"data": self.data})()

    def table(self, nama):
        self.panggilan.append(("table", nama))
        return self

    def insert(self, baris):
        self.panggilan.append(("insert", baris))
        return self

    def update(self, baris):
        self.panggilan.append(("update", baris))
        return self

    def eq(self, kolom, nilai):
        self.panggilan.append(("eq", kolom, nilai))
        return self

    def rpc(self, nama, params=None):
        self.panggilan.append(("rpc", nama, params))
        return self

    def execute(self):
        return self._hasil()


@pytest.fixture
def klien(monkeypatch):
    k = KlienPalsu()
    monkeypatch.setattr(antrean_cetak, "get_client", lambda: k)
    return k


@pytest.fixture
def mode_antrean(monkeypatch):
    monkeypatch.setenv("PRINT_MODE", "antrean")
    monkeypatch.setattr(thermal_printer, "kirim", lambda d: pytest.fail("mode antrean tidak boleh menulis ke printer"))


def _foto():
    return {"lebar": 8, "tinggi": 2, "bits_b64": base64.b64encode(b"\xff\x00").decode(), "baris": ["Bus: CV-1"]}


def _tiket():
    return {"baris": [{"teks": "Tiket Rencana Perjalanan"}]}


# --- service ---------------------------------------------------------------------------------


def test_aktif_hanya_untuk_print_mode_antrean(monkeypatch):
    monkeypatch.delenv("PRINT_MODE", raising=False)
    assert not antrean_cetak.aktif()
    monkeypatch.setenv("PRINT_MODE", "langsung")
    assert not antrean_cetak.aktif()
    monkeypatch.setenv("PRINT_MODE", " Antrean ")
    assert antrean_cetak.aktif()


def test_antre_menyimpan_byte_sebagai_base64_dan_mengembalikan_id(klien):
    klien.data = [{"id": 7}]
    assert antrean_cetak.antre("foto", b"\x1b\x40abc") == 7
    assert ("table", "antrean_cetak") in klien.panggilan
    baris = next(p[1] for p in klien.panggilan if p[0] == "insert")
    assert baris["jenis"] == "foto" and base64.b64decode(baris["data_b64"]) == b"\x1b\x40abc"


def test_antre_gagal_menjadi_antrean_gagal(klien):
    klien.galat = RuntimeError("jaringan putus")
    with pytest.raises(antrean_cetak.AntreanGagal):
        antrean_cetak.antre("tiket", b"x")


def test_status_dan_ambil_kosong_menjadi_none(klien):
    klien.data = []
    assert antrean_cetak.status(1) is None
    assert antrean_cetak.ambil() is None
    klien.data = [{"status": "selesai", "galat": None}]
    assert antrean_cetak.status(1) == {"status": "selesai", "galat": None}
    assert ("rpc", "status_cetak", {"p_id": 1}) in klien.panggilan


def test_selesai_dan_gagal_mengosongkan_data_foto(klien):
    antrean_cetak.selesai(3)
    antrean_cetak.gagal(4, "x" * 500)
    memperbarui = [p[1] for p in klien.panggilan if p[0] == "update"]
    assert memperbarui[0] == {"status": "selesai", "data_b64": ""}
    assert memperbarui[1]["status"] == "gagal" and memperbarui[1]["data_b64"] == "" and len(memperbarui[1]["galat"]) == 300
    assert [p for p in klien.panggilan if p[0] == "eq"] == [("eq", "id", 3), ("eq", "id", 4)]


# --- router ----------------------------------------------------------------------------------


def test_mode_antrean_foto_diantre_bukan_dicetak(mode_antrean, monkeypatch):
    diantre = []
    monkeypatch.setattr(antrean_cetak, "antre", lambda jenis, data: diantre.append((jenis, data)) or 11)
    r = client.post("/api/print/foto", json=_foto())
    assert r.status_code == 202 and r.json() == {"status": "antre", "id": 11}
    jenis, data = diantre[0]
    assert jenis == "foto" and data.startswith(b"\x1b\x40") and b"Bus: CV-1" in data


def test_mode_antrean_tiket_diantre(mode_antrean, monkeypatch):
    diantre = []
    monkeypatch.setattr(antrean_cetak, "antre", lambda jenis, data: diantre.append((jenis, data)) or 12)
    r = client.post("/api/print/tiket", json=_tiket())
    assert r.status_code == 202 and r.json() == {"status": "antre", "id": 12}
    assert diantre[0][0] == "tiket" and b"Tiket Rencana Perjalanan" in diantre[0][1]


def test_mode_antrean_tetap_memvalidasi_sebelum_diantre(mode_antrean, monkeypatch):
    monkeypatch.setattr(antrean_cetak, "antre", lambda *_: pytest.fail("input tidak valid tidak boleh masuk antrean"))
    assert client.post("/api/print/foto", json={**_foto(), "bits_b64": base64.b64encode(b"\x00").decode()}).status_code == 400
    assert client.post("/api/print/foto", json={**_foto(), "lebar": 12}).status_code == 422
    assert client.post("/api/print/tiket", json={"baris": []}).status_code == 422


def test_mode_antrean_supabase_gagal_503(mode_antrean, monkeypatch):
    def gagal(*_):
        raise antrean_cetak.AntreanGagal("Antrean cetak tidak tersedia: ConnectError")

    monkeypatch.setattr(antrean_cetak, "antre", gagal)
    r = client.post("/api/print/tiket", json=_tiket())
    assert r.status_code == 503 and "Antrean cetak" in r.json()["detail"]


def test_tanpa_mode_antrean_tetap_mencetak_langsung(monkeypatch):
    monkeypatch.delenv("PRINT_MODE", raising=False)
    monkeypatch.setattr(antrean_cetak, "antre", lambda *_: pytest.fail("tidak boleh masuk antrean"))
    terkirim = []
    monkeypatch.setattr(thermal_printer, "kirim", terkirim.append)
    r = client.post("/api/print/tiket", json=_tiket())
    assert r.status_code == 200 and r.json() == {"status": "ok"} and len(terkirim) == 1


def test_status_antrean(mode_antrean, monkeypatch):
    monkeypatch.setattr(antrean_cetak, "status", lambda i: {"status": "gagal", "galat": "Agen cetak tidak merespons"} if i == 5 else None)
    assert client.get("/api/print/antrean/5").json() == {"status": "gagal", "galat": "Agen cetak tidak merespons"}
    assert client.get("/api/print/antrean/6").status_code == 404
    assert client.get("/api/print/antrean/0").status_code == 422
    assert client.get("/api/print/antrean/abc").status_code == 422
    assert client.get(f"/api/print/antrean/{2**63}").status_code == 422  # di luar bigint


def test_status_antrean_mati_di_luar_mode_antrean(monkeypatch):
    monkeypatch.delenv("PRINT_MODE", raising=False)
    monkeypatch.setattr(antrean_cetak, "status", lambda i: pytest.fail("tidak boleh menyentuh database"))
    assert client.get("/api/print/antrean/1").status_code == 404


def test_status_antrean_supabase_gagal_503(mode_antrean, monkeypatch):
    def gagal(_i):
        raise antrean_cetak.AntreanGagal("x")

    monkeypatch.setattr(antrean_cetak, "status", gagal)
    assert client.get("/api/print/antrean/1").status_code == 503


# --- agen cetak ------------------------------------------------------------------------------


@pytest.fixture
def agen(monkeypatch):
    jalur = Path(__file__).resolve().parents[1] / "scripts" / "agen_cetak.py"
    spec = importlib.util.spec_from_file_location("agen_cetak_uji", jalur)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    monkeypatch.setattr(modul.time, "sleep", lambda _s: None)
    return modul


def _baris(data=b"\x1b\x40hai"):
    return {"id": 9, "jenis": "tiket", "data_b64": base64.b64encode(data).decode()}


def test_agen_mencetak_lalu_menandai_selesai(agen, monkeypatch):
    terkirim, hasil = [], []
    monkeypatch.setattr(thermal_printer, "kirim", terkirim.append)
    monkeypatch.setattr(antrean_cetak, "selesai", lambda i: hasil.append(("selesai", i)))
    monkeypatch.setattr(antrean_cetak, "gagal", lambda i, g: hasil.append(("gagal", i, g)))
    agen.proses(_baris())
    assert terkirim == [b"\x1b\x40hai"] and hasil == [("selesai", 9)]


def test_agen_printer_gagal_menandai_gagal_dengan_pesannya(agen, monkeypatch):
    def gagal(_d):
        raise thermal_printer.PrinterGagal("Printer di COM13 tidak dapat dihubungi")

    hasil = []
    monkeypatch.setattr(thermal_printer, "kirim", gagal)
    monkeypatch.setattr(antrean_cetak, "selesai", lambda i: hasil.append(("selesai", i)))
    monkeypatch.setattr(antrean_cetak, "gagal", lambda i, g: hasil.append(("gagal", i, g)))
    agen.proses(_baris())
    assert hasil == [("gagal", 9, "Printer di COM13 tidak dapat dihubungi")]


def test_agen_data_rusak_ditandai_gagal_tanpa_menyentuh_printer(agen, monkeypatch):
    hasil = []
    monkeypatch.setattr(thermal_printer, "kirim", lambda d: pytest.fail("data rusak tidak boleh dicetak"))
    monkeypatch.setattr(antrean_cetak, "gagal", lambda i, g: hasil.append((i, g)))
    agen.proses({"id": 2, "jenis": "foto", "data_b64": "bukan base64!!"})
    assert hasil and hasil[0][0] == 2


def test_agen_mengulang_pencatatan_hasil_yang_gagal(agen, monkeypatch):
    percobaan = []

    def selesai(i):
        percobaan.append(i)
        if len(percobaan) < 3:
            raise RuntimeError("jaringan putus")

    monkeypatch.setattr(thermal_printer, "kirim", lambda d: None)
    monkeypatch.setattr(antrean_cetak, "selesai", selesai)
    agen.proses(_baris())
    assert percobaan == [9, 9, 9]
