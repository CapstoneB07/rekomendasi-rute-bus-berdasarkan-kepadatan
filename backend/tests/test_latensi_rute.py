"""Gate latensi rute (offline, tanpa Supabase).

Graf sintetis berskala mendekati data produksi: 12 koridor lurus (24 halte
dua arah, kisi 288 halte) yang berpotongan di halte bersama, sehingga ada transit nyata.
Satu sampel = build_graph + dijkstra, yaitu kerja per request /rekomendasi
di luar I/O. Ambang p95 < 100 ms dari issue #13.
"""

import statistics
import time

from services.dijkstra import build_graph, dijkstra

AMBANG_P95_DETIK = 0.100
JUMLAH_SAMPEL = 30
N_KORIDOR = 12
N_HALTE = 24


def _graph_data_offline() -> dict:
    """Koridor ke-c melintang pada baris c; koridor lain memotongnya di kolom
    yang sama (halte `H{baris}_{kolom}` dipakai bersama oleh koridor baris
    dan koridor kolom), jadi graf berbentuk kisi dengan transit di persimpangan."""
    halte, segmen, halte_to_koridor = {}, [], {}

    def tambah_halte(hid, lat, lng, koridor_id):
        halte[hid] = {"halte_id": hid, "nama": hid, "lat": lat, "lng": lng}
        halte_to_koridor.setdefault(hid, set()).add(koridor_id)

    def tambah_segmen(koridor_id, urutan, asal, tujuan):
        segmen.append({
            "segmen_id": f"K{koridor_id}_{asal}_{tujuan}", "koridor_id": koridor_id,
            "halte_asal": asal, "halte_tujuan": tujuan, "urutan": urutan,
            "waktu_tempuh_detik": 120 + 7 * (urutan % 5),
        })

    for r in range(N_KORIDOR):
        for c in range(N_HALTE):
            tambah_halte(f"H{r}_{c}", r * 0.004, c * 0.004, r + 1)
    for c in range(N_KORIDOR):
        for r in range(N_HALTE):
            hid = f"H{r}_{c}"
            if hid in halte:
                halte_to_koridor[hid].add(100 + c)
            else:
                tambah_halte(hid, r * 0.004, c * 0.004, 100 + c)

    for r in range(N_KORIDOR):
        for c in range(N_HALTE - 1):
            tambah_segmen(r + 1, c, f"H{r}_{c}", f"H{r}_{c + 1}")
            tambah_segmen(r + 1, c, f"H{r}_{c + 1}", f"H{r}_{c}")
    for c in range(N_KORIDOR):
        for r in range(N_HALTE - 1):
            tambah_segmen(100 + c, r, f"H{r}_{c}", f"H{r + 1}_{c}")
            tambah_segmen(100 + c, r, f"H{r + 1}_{c}", f"H{r}_{c}")

    koridor_ids = list(range(1, N_KORIDOR + 1)) + [100 + c for c in range(N_KORIDOR)]
    return {
        "segmen": segmen,
        "kepadatan_bus": [
            {"bus_id": f"B{k}", "koridor_id": k, "jam": 8, "hari_tipe": "weekday",
             "kepadatan": 0.2 + 0.03 * (k % 10)}
            for k in koridor_ids
        ],
        "halte": halte,
        "koridor_halte": [],
        "koridor": {k: {"koridor_id": k, "nama_pendek": f"K{k}", "nama_panjang": f"Koridor {k}"}
                    for k in koridor_ids},
        "halte_to_koridor": halte_to_koridor,
    }


def test_p95_latensi_rekomendasi_rute_di_bawah_ambang():
    data = _graph_data_offline()
    asal, tujuan = "H0_0", f"H{N_HALTE - 1}_{N_KORIDOR - 1}"  # butuh transit

    def satu_request():
        graph = build_graph(data, jam=8, hari_tipe="weekday")
        return dijkstra(graph, asal, tujuan, k=3)

    assert satu_request(), "fixture offline harus menghasilkan rute"  # warm-up

    durasi = []
    for _ in range(JUMLAH_SAMPEL):
        mulai = time.perf_counter()
        satu_request()
        durasi.append(time.perf_counter() - mulai)

    p95 = statistics.quantiles(durasi, n=20)[-1]
    assert p95 < AMBANG_P95_DETIK, f"p95 {p95 * 1000:.1f} ms >= {AMBANG_P95_DETIK * 1000:.0f} ms"
