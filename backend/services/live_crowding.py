"""Kepadatan bus nyata dari CV worker, dibaca dari Supabase.

CV worker (repo kepadatan-bus-cv) meng-upsert satu baris per bus fisik ke tabel
`kepadatan_live`. Modul ini memolling baris milik bus fisik yang dikonfigurasi
(`LIVE_CV_BUS_ID`) dan menyimpannya di memori. Pembacaan yang umurnya melewati
TTL dianggap tidak ada, sehingga bus kembali memakai data generated saat kamera
atau worker mati.

Pemetaan ke bus simulasi ada di services/gtfs_simulation.py
(`live_trip_instance_id`); modul ini hanya tahu sumber datanya.
"""

from __future__ import annotations

import asyncio
import os
import re
import threading
from datetime import datetime, timezone

LIVE_TABLE = "kepadatan_live"
LIVE_CV_BUS_ID = os.getenv("LIVE_CV_BUS_ID") or None
LIVE_CV_TTL_SECONDS = float(os.getenv("LIVE_CV_TTL_SECONDS", "120") or 120)
LIVE_CV_POLL_SECONDS = float(os.getenv("LIVE_CV_POLL_SECONDS", "5") or 5)

_FRACTION = re.compile(r"\.(\d+)")


def _parse_timestamp(value: str) -> datetime:
    """ISO-8601 dari Supabase -> datetime aware.

    Python 3.10 `fromisoformat` hanya menerima pecahan detik 3 atau 6 digit,
    sedangkan Postgres membuang nol di belakang (mis. 5 digit).
    """
    text = value.strip().replace("Z", "+00:00")
    text = _FRACTION.sub(lambda m: "." + m.group(1)[:6].ljust(6, "0"), text, count=1)
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class LiveCrowding:
    def __init__(
        self,
        supabase,
        cv_bus_id: str,
        ttl_seconds: float = LIVE_CV_TTL_SECONDS,
        poll_seconds: float = LIVE_CV_POLL_SECONDS,
    ):
        self._supabase = supabase
        self.cv_bus_id = cv_bus_id
        self.ttl_seconds = ttl_seconds
        self.poll_seconds = poll_seconds
        self._lock = threading.Lock()
        self._reading: dict | None = None

    def update(self, row: dict) -> None:
        """Simpan baris tabel (`jumlah_penumpang`, `updated_at`) sebagai pembacaan terbaru."""
        reading = {
            "jumlah_penumpang": max(0, int(row["jumlah_penumpang"])),
            "updated_at": _parse_timestamp(str(row["updated_at"])),
        }
        with self._lock:
            self._reading = reading

    def latest(self, now: datetime | None = None) -> dict | None:
        """Pembacaan terbaru, atau None bila belum ada / sudah lewat TTL."""
        with self._lock:
            reading = self._reading
        if reading is None:
            return None
        now = now or datetime.now(timezone.utc)
        if (now - reading["updated_at"]).total_seconds() > self.ttl_seconds:
            return None
        return reading

    def refresh(self) -> None:
        try:
            rows = (
                self._supabase.table(LIVE_TABLE)
                .select("jumlah_penumpang, updated_at")
                .eq("bus_id", self.cv_bus_id)
                .limit(1)
                .execute()
                .data
            )
            if rows:
                self.update(rows[0])
        except Exception as e:
            # Pembacaan lama tetap dipakai sampai TTL habis.
            print(f"[live_crowding] WARNING: gagal baca '{LIVE_TABLE}' ({e!r})")

    async def run(self) -> None:
        while True:
            await asyncio.to_thread(self.refresh)
            await asyncio.sleep(self.poll_seconds)
