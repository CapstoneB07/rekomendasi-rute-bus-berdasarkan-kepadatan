from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import lokasi

app = FastAPI()
app.include_router(lokasi.router)
client = TestClient(app)


def test_kosong_sebelum_operator_memilih():
    app.state.lokasi = None
    assert client.get("/api/lokasi").json() == {"lokasi": None}


def test_put_lalu_get():
    assert client.put("/api/lokasi", json={"halte_id": "G00100"}).status_code == 200
    assert client.get("/api/lokasi").json() == {"lokasi": {"halte_id": "G00100"}}


def test_masukan_tidak_valid_ditolak():
    for body in ({"halte_id": ""}, {"halte_id": "x" * 65}, {}):
        assert client.put("/api/lokasi", json=body).status_code == 422
