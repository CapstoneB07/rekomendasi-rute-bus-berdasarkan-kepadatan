from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import pencarian

app = FastAPI()
app.include_router(pencarian.router)
client = TestClient(app)

_BODY = {"halte_asal": "G00100", "halte_tujuan": "G00200", "aktif_idx": 1}


def test_kosong_sebelum_kiosk_mencari():
    app.state.pencarian = None
    assert client.get("/api/pencarian").json() == {"pencarian": None}


def test_put_lalu_get_dengan_stempel_server():
    assert client.put("/api/pencarian", json=_BODY).status_code == 200
    p = client.get("/api/pencarian").json()["pencarian"]
    assert (p["halte_asal"], p["halte_tujuan"], p["aktif_idx"]) == ("G00100", "G00200", 1)
    assert p["ts"] > 0


def test_delete_menghapus_pencarian():
    client.put("/api/pencarian", json=_BODY)
    assert client.delete("/api/pencarian").status_code == 200
    assert client.get("/api/pencarian").json() == {"pencarian": None}


def test_masukan_tidak_valid_ditolak():
    for ubah in ({"halte_asal": ""}, {"halte_tujuan": "x" * 65}, {"aktif_idx": -1}):
        assert client.put("/api/pencarian", json={**_BODY, **ubah}).status_code == 422
