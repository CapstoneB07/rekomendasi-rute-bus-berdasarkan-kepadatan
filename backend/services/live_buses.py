"""Posisi bus real-time TransJakarta, diteruskan (relay) oleh browser kiosk/operator.

Broker MQTT TransJakarta (wss://mqtt.tj.co.id:8084/mqtt, anonim) memblokir IP VPS, jadi
backend tidak berlangganan sendiri. Browser yang memakai IP biasa berlangganan lewat
mqtt.js (frontend/src/lib/relay-bus-tj.ts) lalu mengirim pesan bus ke PUT /api/live/buses.
Broker hanya menerima client ID berawalan `mqttjs_` (lihat github.com/BroNils/open-tj).

Payload MQTT tidak membawa kepadatan (`passengers_status` selalu kosong), jadi bus
live hanya punya posisi, arah, dan ETA halte berikutnya.
"""

from __future__ import annotations

import threading
import time
from typing import Callable

# Tiap bus mengirim pesan kira-kira tiap 30 detik; lewat batas ini dianggap sudah tidak aktif.
MAX_AGE_DETIK = 120.0
# Browser relay mengirim tiap ±5 detik; tanpa kiriman selama ini, relay dianggap mati.
RELAY_BASI_DETIK = 30.0

# Status koneksi broker (dilaporkan relay) yang dikirim ke frontend.
MENYAMBUNG = "menyambung"
TERSAMBUNG = "tersambung"
DITOLAK = "ditolak"  # broker menjawab tapi menolak (mis. client ID tidak diizinkan)
TERPUTUS = "terputus"  # koneksi relay ke broker putus, atau tidak ada relay yang aktif


def parse_pesan(data: dict, route_to_koridor: dict[str, int]) -> dict | None:
    """Ubah satu pesan bus MQTT jadi record bus, atau None bila bukan bus koridor yang dikenal."""
    try:
        koridor_id = route_to_koridor.get(str(data["route_code"]))
        if koridor_id is None:
            return None
        # Halte tanpa eta sudah/sedang disinggahi; yang tersisa adalah halte berikutnya.
        stops = [stop for stop in data.get("stops") or [] if stop.get("eta") is not None]
        return {
            "bus_id": str(data["bus_body_no"]),
            "koridor_id": koridor_id,
            "lat": float(data["latitude"]),
            "lng": float(data["longitude"]),
            "bearing": int(data.get("bearing") or 0),
            "next_stop": stops[0]["name"] if stops else "",
            "eta_minutes": int(data.get("eta") or 0),
            "trip_id": data.get("trip_id") or "",
            "stops": [
                {
                    "stop_id": stop["stop_id"],
                    "parent_stop_id": stop.get("parent_stop_id"),
                    "eta": int(stop["eta"]),
                }
                for stop in stops
            ],
        }
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


def bangun_jadwal_live(
    buses: list[dict], halte_ids: set[str], detik_sekarang: int
) -> dict[str, list[dict]]:
    """Ubah bus live jadi `jadwal` berbentuk app.state.jadwal untuk select_bus_per_segmen.

    Tiap bus membawa sisa halte perjalanannya dengan ETA (menit) dari sekarang.
    Halte dicocokkan ke halte_id statis lewat stop_id, lalu parent_stop_id; halte
    yang tidak dikenal dilewati. Bus tanpa halte yang cocok tidak dimasukkan.
    """
    jadwal: dict[str, list[dict]] = {}
    for bus in buses:
        stops = []
        for stop in bus["stops"]:
            halte_id = next(
                (i for i in (stop["stop_id"], stop["parent_stop_id"]) if i in halte_ids), None
            )
            if halte_id is None:
                continue
            stops.append({
                "halte_id": halte_id,
                "koridor_id": bus["koridor_id"],
                "waktu_tiba_detik": detik_sekarang + stop["eta"] * 60,
            })
        if stops:
            jadwal[bus["bus_id"]] = stops
    return jadwal


class LiveBuses:
    """Menyimpan pesan terakhir tiap bus dan status broker yang dilaporkan browser relay."""

    def __init__(
        self,
        route_to_koridor: dict[str, int],
        max_age: float = MAX_AGE_DETIK,
        relay_basi: float = RELAY_BASI_DETIK,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._route_to_koridor = route_to_koridor
        self._max_age = max_age
        self._relay_basi = relay_basi
        self._clock = clock
        self._lock = threading.Lock()
        self._buses: dict[str, tuple[float, dict]] = {}
        # Waktu laporan terakhir per status; relay yang tersambung menang atas relay lain yang gagal.
        self._laporan: dict[str, float] = {}

    @property
    def route_codes(self) -> list[str]:
        return sorted(self._route_to_koridor)

    @property
    def status(self) -> str:
        if not self._laporan:
            return MENYAMBUNG
        batas = self._clock() - self._relay_basi
        segar = {s: t for s, t in self._laporan.items() if t >= batas}
        if not segar:
            return TERPUTUS
        if TERSAMBUNG in segar:
            return TERSAMBUNG
        return max(segar, key=segar.get)

    def terima_relay(self, status: str, pesan: list[dict]) -> int:
        """Simpan laporan satu browser relay; kembalikan jumlah bus koridor dikenal yang diterima."""
        sekarang = self._clock()
        buses = [b for b in (parse_pesan(p, self._route_to_koridor) for p in pesan) if b is not None]
        with self._lock:
            self._laporan[status] = sekarang
            for bus in buses:
                self._buses[bus["bus_id"]] = (sekarang, bus)
        return len(buses)

    def snapshot(self) -> list[dict]:
        """Bus yang pesannya masih segar; yang basi dibuang dari memori."""
        batas = self._clock() - self._max_age
        with self._lock:
            self._buses = {k: v for k, v in self._buses.items() if v[0] >= batas}
            return [bus for _, bus in self._buses.values()]
