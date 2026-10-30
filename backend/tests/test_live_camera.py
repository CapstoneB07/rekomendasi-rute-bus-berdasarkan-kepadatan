from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import live

BBOXES = [{"x": 10, "y": 20, "w": 30, "h": 40, "kelas": "person", "skor": 0.9}]


class _FakeSupabase:
    def __init__(self, rows: dict[str, dict]):
        self._rows = rows
        self._bus_id = None
        self.storage = SimpleNamespace(from_=lambda bucket: self)

    def table(self, name):
        assert name == "kamera_live"
        return self

    def select(self, _cols):
        return self

    def eq(self, _col, bus_id):
        self._bus_id = bus_id
        return self

    def limit(self, _n):
        return self

    def execute(self):
        row = self._rows.get(self._bus_id)
        return SimpleNamespace(data=[row] if row else [])

    def create_signed_url(self, path, expires_in):
        return {"signedURL": f"https://storage.test/{path}?exp={expires_in}"}


def _client(rows: dict[str, dict]) -> TestClient:
    app = FastAPI()
    app.include_router(live.router)
    app.state.supabase = _FakeSupabase(rows)
    return TestClient(app)


def _row(age_seconds: float) -> dict:
    ts = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    return {"frame_path": "CV-1/latest.jpg", "bboxes": BBOXES, "updated_at": ts.isoformat()}


def test_camera_ada_data():
    res = _client({"CV-1": _row(10)}).get("/api/live/camera/CV-1")
    assert res.status_code == 200
    body = res.json()
    assert body["bus_id"] == "CV-1"
    assert body["frame_url"].startswith("https://storage.test/CV-1/latest.jpg")
    assert body["bboxes"] == BBOXES
    assert body["updated_at"]


def test_camera_frame_basi():
    res = _client({"CV-1": _row(500)}).get("/api/live/camera/CV-1")
    assert res.status_code == 410


def test_camera_bus_tidak_dikenal():
    res = _client({"CV-1": _row(10)}).get("/api/live/camera/XX-9")
    assert res.status_code == 404


def test_camera_bus_terkonfigurasi(monkeypatch):
    monkeypatch.setattr(live, "LIVE_CV_BUS_ID", "CV-1")
    res = _client({"CV-1": _row(10)}).get("/api/live/camera")
    assert res.status_code == 200
    assert res.json()["bus_id"] == "CV-1"


def test_camera_bus_belum_dikonfigurasi(monkeypatch):
    monkeypatch.setattr(live, "LIVE_CV_BUS_ID", None)
    res = _client({"CV-1": _row(10)}).get("/api/live/camera")
    assert res.status_code == 404


def test_camera_supabase_gagal_jadi_503():
    class _Rusak(_FakeSupabase):
        def execute(self):
            raise RuntimeError("Could not find the table 'kamera_live'")

    app = FastAPI()
    app.include_router(live.router)
    app.state.supabase = _Rusak({})
    res = TestClient(app, raise_server_exceptions=False).get("/api/live/camera/CV-1")
    assert res.status_code == 503
    assert res.json()["detail"] == "Layanan kamera tidak tersedia"
