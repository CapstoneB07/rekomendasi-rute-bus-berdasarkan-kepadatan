from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import waktu

app = FastAPI()
app.include_router(waktu.router)
client = TestClient(app)

_BODY = {"is_live": False, "is_playing": True, "kecepatan": 10, "sim_time": 28800}


def test_default_live_sebelum_operator_menulis():
    app.state.waktu = None
    r = client.get("/api/waktu").json()
    assert r["keadaan"]["is_live"] is True
    assert r["server_now"] > 0


def test_put_lalu_get_mengembalikan_jangkar_dengan_stempel_server():
    r = client.put("/api/waktu", json=_BODY)
    assert r.status_code == 200
    g = client.get("/api/waktu").json()
    assert g["keadaan"]["sim_time"] == 28800
    assert g["keadaan"]["kecepatan"] == 10
    assert 0 < g["keadaan"]["ts"] <= g["server_now"]


def test_nilai_di_luar_rentang_ditolak():
    for ubah in ({"sim_time": 86400}, {"sim_time": -1}, {"kecepatan": 0}, {"kecepatan": 601}):
        assert client.put("/api/waktu", json={**_BODY, **ubah}).status_code == 422
