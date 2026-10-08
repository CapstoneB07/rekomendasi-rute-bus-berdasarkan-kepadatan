"""Posisi bus real-time dari MQTT TransJakarta (broker anonim, hanya baca).

Payload MQTT tidak membawa kepadatan (`passengers_status` selalu kosong), jadi bus
live hanya punya posisi, arah, dan ETA halte berikutnya.
"""

from __future__ import annotations

import json
import logging
import ssl
import threading
import time
from typing import Callable

logger = logging.getLogger(__name__)

MQTT_HOST = "mqtt.tj.co.id"
MQTT_PORT = 8084
MQTT_PATH = "/mqtt"
MQTT_TOPIC_PREFIX = "/mobile_armada"
# Tiap bus mengirim pesan kira-kira tiap 30 detik; lewat batas ini dianggap sudah tidak aktif.
MAX_AGE_DETIK = 120.0


def topik_langganan(route_codes) -> list[str]:
    """Topik broker per route_code: /mobile_armada/<koridor>/<route_code>/<trip>/<bus>.

    Berlangganan hanya ke koridor yang dipakai membuat broker yang menyaring (±3% dari
    seluruh trafik), bukan proses ini yang mem-parse JSON ribuan bus yang tidak terpakai.
    """
    return [f"{MQTT_TOPIC_PREFIX}/+/{kode}/#" for kode in sorted(route_codes)]


def parse_pesan(payload: bytes, route_to_koridor: dict[str, int]) -> dict | None:
    """Ubah satu payload MQTT jadi record bus, atau None bila bukan bus koridor yang dikenal."""
    try:
        data = json.loads(payload)
        koridor_id = route_to_koridor.get(str(data["route_code"]))
        if koridor_id is None:
            return None
        stops = data.get("stops") or []
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
    """Menyimpan pesan terakhir tiap bus; subscriber MQTT jalan di thread paho."""

    def __init__(
        self,
        route_to_koridor: dict[str, int],
        max_age: float = MAX_AGE_DETIK,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._route_to_koridor = route_to_koridor
        self._max_age = max_age
        self._clock = clock
        self._lock = threading.Lock()
        self._buses: dict[str, tuple[float, dict]] = {}
        self._connected = False
        self._client = None

    @property
    def connected(self) -> bool:
        return self._connected

    def terima(self, payload: bytes) -> None:
        bus = parse_pesan(payload, self._route_to_koridor)
        if bus is None:
            return
        with self._lock:
            self._buses[bus["bus_id"]] = (self._clock(), bus)

    def snapshot(self) -> list[dict]:
        """Bus yang pesannya masih segar; yang basi dibuang dari memori."""
        batas = self._clock() - self._max_age
        with self._lock:
            self._buses = {k: v for k, v in self._buses.items() if v[0] >= batas}
            return [bus for _, bus in self._buses.values()]

    def start(self) -> None:
        import paho.mqtt.client as mqtt

        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, transport="websockets", protocol=mqtt.MQTTv311
        )
        client.ws_set_options(path=MQTT_PATH)
        client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
        client.reconnect_delay_set(min_delay=1, max_delay=30)

        def on_connect(c, _userdata, _flags, reason_code, _props=None):
            self._connected = not reason_code.is_failure
            if self._connected:
                c.subscribe([(topik, 0) for topik in topik_langganan(self._route_to_koridor)])
            else:
                logger.warning("MQTT TransJakarta menolak koneksi: %s", reason_code)

        def on_disconnect(_c, _userdata, _flags, reason_code, _props=None):
            self._connected = False
            logger.warning("MQTT TransJakarta terputus: %s", reason_code)

        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.on_message = lambda _c, _u, msg: self.terima(msg.payload)
        # connect_async: server tetap start walau broker tidak terjangkau; paho mencoba lagi sendiri.
        client.connect_async(MQTT_HOST, MQTT_PORT)
        client.loop_start()
        self._client = client

    def stop(self) -> None:
        if self._client is not None:
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None
        self._connected = False
