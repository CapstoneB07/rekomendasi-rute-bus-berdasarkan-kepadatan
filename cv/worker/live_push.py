"""Kirim headcount ke tabel Supabase `kepadatan_live` untuk backend transjakarta-app.

Satu baris per bus fisik (upsert). Backend memolling baris ini dan memakainya
sebagai kepadatan satu bus; lihat backend/sql/kepadatan_live.sql di repo
transjakarta-app untuk skema tabelnya.

Hitungan YOLO per frame berfluktuasi, jadi yang dikirim adalah median dari
beberapa frame terakhir, paling sering sekali per PUSH_INTERVAL_SECONDS.
Upload berjalan di thread terpisah supaya jaringan lambat tidak menahan
antrean Redis.
"""

import os
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from statistics import median

import requests
from dotenv import load_dotenv

LIVE_TABLE = "kepadatan_live"
PUSH_INTERVAL_SECONDS = 3.0
MEDIAN_WINDOW = 5
REQUEST_TIMEOUT_SECONDS = 5.0


def _log(level, message):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] [{level}] {message}")


class LivePusher:
    def __init__(self, bus_id, supabase_url, service_key):
        self.bus_id = bus_id
        self._endpoint = f"{supabase_url.rstrip('/')}/rest/v1/{LIVE_TABLE}?on_conflict=bus_id"
        self._headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }
        self._counts = deque(maxlen=MEDIAN_WINDOW)
        self._last_push = float("-inf")
        self._in_flight = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1)

    @classmethod
    def from_env(cls, bus_id):
        """None bila kredensial tidak ada; worker tetap jalan tanpa upload."""
        load_dotenv()
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            _log("WARNING", "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY belum diset; upload ke Supabase dimatikan.")
            return None
        return cls(bus_id, url, key)

    def submit(self, headcount):
        """Catat headcount frame ini; kirim median bila interval sudah lewat."""
        self._counts.append(headcount)
        now = time.monotonic()
        if now - self._last_push < PUSH_INTERVAL_SECONDS:
            return
        if not self._in_flight.acquire(blocking=False):
            return  # upload sebelumnya belum selesai
        self._last_push = now
        payload = {
            "bus_id": self.bus_id,
            "jumlah_penumpang": int(round(median(self._counts))),
        }
        self._executor.submit(self._upsert, payload)

    def _upsert(self, payload):
        try:
            response = requests.post(
                self._endpoint,
                json=payload,
                headers=self._headers,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            _log("LIVE", f"upsert {LIVE_TABLE} {payload}")
        except Exception as e:
            _log("LIVE ERROR", f"gagal upsert {LIVE_TABLE}: {type(e).__name__}: {e}")
        finally:
            self._in_flight.release()
