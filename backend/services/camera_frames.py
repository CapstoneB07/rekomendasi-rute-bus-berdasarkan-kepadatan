"""Frame kamera terbaru beserta bounding box deteksi, dibaca dari Supabase.

CV worker (repo kepadatan-bus-cv) mengunggah frame ke bucket Storage
`kamera-frames` dan meng-upsert satu baris per bus fisik ke tabel
`kamera_live` (path frame + daftar bbox). Berbeda dengan kepadatan, data ini
tidak dipolling: dibaca saat endpoint dipanggil, karena hanya dibutuhkan
sesekali oleh halaman bukti/diagnostik.
"""

from __future__ import annotations

from datetime import datetime, timezone

from services.live_crowding import LIVE_CV_TTL_SECONDS, _parse_timestamp

CAMERA_TABLE = "kamera_live"
FRAME_BUCKET = "kamera-frames"
SIGNED_URL_SECONDS = 300


class BusTidakDikenal(Exception):
    """Belum pernah ada frame untuk bus ini."""


class FrameBasi(Exception):
    """Frame terakhir bus ini sudah melewati TTL."""


def frame_terbaru(
    supabase,
    bus_id: str,
    now: datetime | None = None,
    ttl_seconds: float = LIVE_CV_TTL_SECONDS,
) -> dict:
    rows = (
        supabase.table(CAMERA_TABLE)
        .select("frame_path, bboxes, updated_at")
        .eq("bus_id", bus_id)
        .limit(1)
        .execute()
        .data
    )
    if not rows:
        raise BusTidakDikenal(bus_id)
    row = rows[0]

    updated_at = _parse_timestamp(str(row["updated_at"]))
    now = now or datetime.now(timezone.utc)
    if (now - updated_at).total_seconds() > ttl_seconds:
        raise FrameBasi(bus_id)

    signed = supabase.storage.from_(FRAME_BUCKET).create_signed_url(
        row["frame_path"], SIGNED_URL_SECONDS
    )
    return {
        "bus_id": bus_id,
        "frame_url": signed["signedURL"],
        "bboxes": row["bboxes"],
        "updated_at": updated_at.isoformat(),
    }
