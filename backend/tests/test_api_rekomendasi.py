"""Test API /api/rute/rekomendasi terhadap data nyata (Supabase).

Dilewati otomatis jika kredensial Supabase tidak tersedia. MQTT dimatikan
agar test tidak membuka koneksi keluar selain Supabase.

Gate latensi (p95 < 100 ms) ada di test_latensi_rute.py (graf offline, dijalankan CI).
TC-PERF-03 di sini hanya mencetak profil waktu per tahap terhadap data nyata.
"""

import os

import pytest
from dotenv import load_dotenv

load_dotenv()

pytestmark = pytest.mark.skipif(
    not (os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY")),
    reason="kredensial Supabase tidak tersedia",
)


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from services.live_buses import LiveBuses

    LiveBuses.start = lambda self: None
    LiveBuses.stop = lambda self: None
    import main

    with TestClient(main.app) as c:
        yield c


@pytest.fixture(scope="module")
def pasangan(client):
    """Beberapa pasangan halte berbeda yang rutenya ada, dipilih dari data nyata."""
    halte = client.app.state.graph_data["halte"]
    import random

    ids = sorted(halte)
    rng = random.Random(42)
    kandidat = [tuple(rng.sample(ids, 2)) for _ in range(60)]
    hasil = []
    for a, b in kandidat:
        if a == b:
            continue
        r = client.post("/api/rute/rekomendasi", json={"halte_asal": a, "halte_tujuan": b, "jam": 9})
        if r.status_code == 200 and r.json():
            hasil.append((a, b))
        if len(hasil) >= 8:
            break
    assert hasil, "tidak ada pasangan halte yang menghasilkan rute"
    return hasil


# ---- Fungsional -------------------------------------------------------

def test_tc_api_01_halte_asal_tidak_ada(client):
    r = client.post("/api/rute/rekomendasi", json={"halte_asal": "NOPE", "halte_tujuan": "NOPE2"})
    assert r.status_code == 404


def test_tc_api_02_halte_sama(client):
    h = next(iter(client.app.state.graph_data["halte"]))
    r = client.post("/api/rute/rekomendasi", json={"halte_asal": h, "halte_tujuan": h})
    assert r.status_code == 400


@pytest.mark.parametrize("jam", [-1, 24])
def test_tc_api_03_jam_di_luar_rentang(client, jam):
    r = client.post("/api/rute/rekomendasi", json={"halte_asal": "a", "halte_tujuan": "b", "jam": jam})
    assert r.status_code == 422


def test_tc_api_04_hari_tipe_tidak_valid(client):
    r = client.post("/api/rute/rekomendasi", json={"halte_asal": "a", "halte_tujuan": "b", "hari_tipe": "libur"})
    assert r.status_code == 422


def test_tc_api_05_field_wajib_kurang(client):
    assert client.post("/api/rute/rekomendasi", json={"halte_asal": "a"}).status_code == 422


def test_tc_api_06_sim_time_di_atas_sehari(client, pasangan):
    """sim_time hanya divalidasi ge=0; nilai > 86400 sebaiknya ditolak."""
    a, b = pasangan[0]
    r = client.post(
        "/api/rute/rekomendasi",
        json={"halte_asal": a, "halte_tujuan": b, "sim_time": 10**9},
    )
    assert r.status_code == 422, f"diterima dengan status {r.status_code}"


def test_tc_api_07_struktur_respons(client, pasangan):
    a, b = pasangan[0]
    r = client.post("/api/rute/rekomendasi", json={"halte_asal": a, "halte_tujuan": b, "jam": 9})
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list) and data
    assert all(isinstance(x, dict) for x in data)
    print("kunci respons:", sorted(data[0]))


def test_tc_api_08_deterministik_untuk_request_sama(client, pasangan):
    a, b = pasangan[0]
    body = {"halte_asal": a, "halte_tujuan": b, "jam": 9, "sim_time": 32400, "simulation_run_id": "t"}
    r1 = client.post("/api/rute/rekomendasi", json=body).json()
    r2 = client.post("/api/rute/rekomendasi", json=body).json()
    assert r1 == r2


def test_tc_api_09_mode_live(client, pasangan):
    a, b = pasangan[0]
    r = client.post("/api/rute/rekomendasi", json={"halte_asal": a, "halte_tujuan": b, "live": True})
    assert r.status_code in (200, 404)


def test_tc_api_10_endpoint_simulasi_dan_live(client):
    assert client.get("/api/simulation/halte").status_code == 200
    assert client.get("/api/simulation/shapes").status_code == 200
    assert client.get("/api/simulation/positions", params={"sim_time": 32400}).status_code == 200
    assert client.get("/api/live/positions").status_code == 200


# ---- Profil (informasi) ------------------------------------------

def test_tc_perf_03_profil_tahap(client, pasangan):
    """Informasi saja: rincian waktu per tahap untuk satu pasangan."""
    import cProfile
    import io
    import pstats

    a, b = pasangan[0]
    body = {"halte_asal": a, "halte_tujuan": b, "jam": 9}
    client.post("/api/rute/rekomendasi", json=body)
    pr = cProfile.Profile()
    pr.enable()
    client.post("/api/rute/rekomendasi", json=body)
    pr.disable()
    s = io.StringIO()
    pstats.Stats(pr, stream=s).sort_stats("cumulative").print_stats(18)
    print(s.getvalue())
