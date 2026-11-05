"""Kirim headcount dan frame kamera ke Supabase untuk backend aplikasi.

Headcount: tabel `kepadatan_live`, satu baris per bus fisik (upsert). Backend
memolling baris ini dan memakainya sebagai kepadatan satu bus; lihat
backend/sql/kepadatan_live.sql di root monorepo untuk skema tabelnya.

Frame: JPEG terbaru diunggah ke bucket `kamera-frames` di path uniknya sendiri,
lalu path dan bbox deteksinya di-upsert ke `kamera_live`
(backend/sql/kamera_live.sql) untuk panel kamera dan photobox di halaman
operator. Path unik membuat frame_path di baris selalu menunjuk gambar yang
berpasangan dengan bbox-nya (menimpa satu objek akan membuat gambar sempat
lebih baru daripada bbox). FRAME_RETENTION frame terakhir disimpan supaya
signed URL / unduhan yang sedang berjalan tidak kehilangan filenya. Sisa file
proses sebelumnya (restart worker) dihapus sekali setelah upsert pertama.

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
CAMERA_TABLE = "kamera_live"
FRAME_BUCKET = "kamera-frames"
PUSH_INTERVAL_SECONDS = 3.0
FRAME_INTERVAL_SECONDS = 0.3
MEDIAN_WINDOW = 5
# Cukup untuk beberapa detik: polling operator 2 dtk + jeda klik foto.
FRAME_RETENTION = 10
REQUEST_TIMEOUT_SECONDS = 5.0


def _log(level, message):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] [{level}] {message}")


class LivePusher:
    def __init__(self, bus_id, supabase_url, service_key):
        self.bus_id = bus_id
        base = supabase_url.rstrip("/")
        self._endpoint = f"{base}/rest/v1/{LIVE_TABLE}?on_conflict=bus_id"
        self._camera_endpoint = f"{base}/rest/v1/{CAMERA_TABLE}?on_conflict=bus_id"
        self._object_base = f"{base}/storage/v1/object/{FRAME_BUCKET}"
        self._list_endpoint = f"{base}/storage/v1/object/list/{FRAME_BUCKET}"
        # Cap waktu mulai membuat nama tidak bentrok dengan sisa proses sebelumnya.
        self._frame_epoch = int(time.time() * 1000)
        self._frame_seq = 0
        self._frame_paths = deque()
        # Sisa file proses sebelumnya dibersihkan sekali, setelah upsert pertama berhasil.
        self._sisa_dibersihkan = False
        self._headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }
        self._counts = deque(maxlen=MEDIAN_WINDOW)
        self._last_push = float("-inf")
        self._in_flight = threading.Lock()
        self._last_frame_push = float("-inf")
        self._frame_in_flight = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=2)

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

    def submit_frame(self, jpeg_bytes, bboxes):
        """Unggah frame beserta bbox-nya bila interval sudah lewat."""
        now = time.monotonic()
        if now - self._last_frame_push < FRAME_INTERVAL_SECONDS:
            return
        if not self._frame_in_flight.acquire(blocking=False):
            return  # unggahan sebelumnya belum selesai
        self._last_frame_push = now
        self._executor.submit(self._upload_frame, jpeg_bytes, bboxes)

    def _upload_frame(self, jpeg_bytes, bboxes):
        try:
            self._frame_seq += 1
            frame_path = f"{self.bus_id}/{self._frame_epoch}-{self._frame_seq}.jpg"
            response = requests.post(
                f"{self._object_base}/{frame_path}",
                data=jpeg_bytes,
                headers={
                    **self._headers,
                    "Content-Type": "image/jpeg",
                    "cache-control": "max-age=0",
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            # Dicatat sebelum upsert baris: bila upsert gagal, file ini tetap ikut dibersihkan.
            self._frame_paths.append(frame_path)
            response = requests.post(
                self._camera_endpoint,
                json={"bus_id": self.bus_id, "frame_path": frame_path, "bboxes": bboxes},
                headers=self._headers,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            _log("LIVE", f"upsert {CAMERA_TABLE} bbox={len(bboxes)}")
            self._prune_frames()
            if not self._sisa_dibersihkan:
                self._bersihkan_sisa()
        except Exception as e:
            _log("LIVE ERROR", f"gagal unggah frame: {type(e).__name__}: {e}")
        finally:
            self._frame_in_flight.release()

    def _prune_frames(self):
        """Hapus frame lama di luar FRAME_RETENTION; gagal hapus hanya dicatat (file akan tersisa)."""
        while len(self._frame_paths) > FRAME_RETENTION:
            lama = self._frame_paths.popleft()
            try:
                requests.delete(
                    f"{self._object_base}/{lama}",
                    headers=self._headers,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                ).raise_for_status()
            except Exception as e:
                _log("LIVE ERROR", f"gagal hapus frame lama {lama}: {type(e).__name__}: {e}")

    def _bersihkan_sisa(self):
        """Hapus file bus ini di bucket yang bukan milik proses ini (sisa restart, atau latest.jpg versi lama).

        Dijalankan setelah upsert baris pertama berhasil, jadi baris kamera_live tidak
        pernah menunjuk file yang dihapus. Gagal hanya dicatat dan dicoba lagi di frame berikutnya.
        """
        try:
            punyaku = {p.rsplit("/", 1)[-1] for p in self._frame_paths}
            for _ in range(10):  # 1000 file per putaran; sisa lebih banyak dari itu diselesaikan putaran berikutnya
                response = requests.post(
                    f"{self._list_endpoint}",
                    json={"prefix": self.bus_id, "limit": 1000, "offset": 0},
                    headers=self._headers,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                sisa = [f"{self.bus_id}/{o['name']}" for o in response.json() if o["name"] not in punyaku]
                if not sisa:
                    break
                response = requests.delete(
                    self._object_base,
                    json={"prefixes": sisa},
                    headers=self._headers,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                _log("LIVE", f"hapus {len(sisa)} frame sisa dari {FRAME_BUCKET}/{self.bus_id}")
            self._sisa_dibersihkan = True
        except Exception as e:
            _log("LIVE ERROR", f"gagal membersihkan frame sisa: {type(e).__name__}: {e}")
