import logging
from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError

from services.camera_frames import BusTidakDikenal, FrameBasi, frame_terbaru
from services.gtfs_simulation import kepadatan_bus_live
from services.live_crowding import LIVE_CV_BUS_ID

router = APIRouter(prefix="/api/live")
logger = logging.getLogger(__name__)

WIB = ZoneInfo("Asia/Jakarta")
KEPADATAN_KOSONG = {
    "trip_load_factor": None,
    "label_kepadatan": None,
    "estimated_passengers": None,
    "capacity": None,
}


Teks = Field(max_length=200)


class HalteRelay(BaseModel):
    name: str = Teks
    stop_id: str = Teks
    parent_stop_id: str | None = Field(default=None, max_length=200)
    # Halte yang sedang/sudah disinggahi tidak punya eta.
    eta: int | None = Field(default=None, ge=0, le=24 * 60)


class PesanBusRelay(BaseModel):
    """Subset pesan MQTT /mobile_armada yang dipakai backend; field lain diabaikan."""

    route_code: str = Teks
    bus_body_no: str = Teks
    trip_id: str | None = Field(default=None, max_length=200)
    # Kotak luas sekitar Jabodetabek; koordinat di luar ini bukan bus TransJakarta.
    latitude: float = Field(ge=-7.0, le=-5.8)
    longitude: float = Field(ge=106.2, le=107.4)
    bearing: int | None = Field(default=None, ge=0, le=360)
    eta: int | None = Field(default=None, ge=0, le=24 * 60)
    stops: list[HalteRelay] = Field(default_factory=list, max_length=200)


class LaporanRelay(BaseModel):
    status: Literal["tersambung", "ditolak", "terputus"]
    # Divalidasi per bus (PesanBusRelay): satu pesan rusak, mis. bus tanpa GPS di (0, 0),
    # tidak boleh membuat bus lain dalam laporan yang sama ikut ditolak.
    buses: list[Any] = Field(default_factory=list, max_length=2000)


@router.get("/koridor")
def get_route_codes(request: Request):
    """route_code MQTT yang perlu dilanggan browser relay (koridor yang ada di data statis)."""
    return {"route_codes": request.app.state.live_buses.route_codes}


@router.put("/buses")
def put_live_buses(request: Request, body: LaporanRelay):
    """Laporan browser relay: status koneksinya ke broker TJ dan pesan bus terbaru.

    Backend tidak bisa berlangganan sendiri karena IP VPS diblokir broker; lihat
    services/live_buses.py. Endpoint ini terbuka tanpa login seperti PUT /api/waktu,
    jadi isinya divalidasi ketat (tipe, rentang, batas jumlah).
    """
    valid = []
    for pesan in body.buses:
        try:
            valid.append(PesanBusRelay.model_validate(pesan).model_dump())
        except ValidationError:
            continue
    diterima = request.app.state.live_buses.terima_relay(body.status, valid)
    return {"diterima": diterima, "ditolak": len(body.buses) - len(valid)}


@router.get("/positions")
def get_live_positions(request: Request):
    """Posisi bus asli (MQTT TransJakarta) untuk koridor yang ada di data statis.

    Bentuk properti mengikuti /api/simulation/positions. MQTT tidak membawa
    kepadatan, jadi kepadatan adalah PERKIRAAN dari trip simulasi yang setara
    (lihat kepadatan_bus_live); null untuk koridor di luar simulasi.
    """
    live = request.app.state.live_buses
    ctx = getattr(request.app.state, "simulation_context", None)
    now = datetime.now(WIB)
    detik = now.hour * 3600 + now.minute * 60 + now.second

    features = []
    for bus in live.snapshot():
        kepadatan = (
            kepadatan_bus_live(ctx, bus["bus_id"], bus["koridor_id"], detik) if ctx else None
        )
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [bus["lng"], bus["lat"]]},
            "properties": {
                "bus_id": bus["bus_id"],
                "koridor_id": bus["koridor_id"],
                "bearing": bus["bearing"],
                "next_stop": bus["next_stop"],
                "eta_minutes": bus["eta_minutes"],
                "trip_id": bus["trip_id"],
                "data_source": "tj_live",
                **(kepadatan or KEPADATAN_KOSONG),
            },
        })
    return {"type": "FeatureCollection", "status": live.status, "features": features}


@router.get("/camera")
def get_live_camera_cv(request: Request):
    """Frame kamera bus fisik yang dikonfigurasi (LIVE_CV_BUS_ID), untuk halaman operator."""
    if not LIVE_CV_BUS_ID:
        raise HTTPException(status_code=404, detail="Kamera bus belum dikonfigurasi")
    return get_live_camera(LIVE_CV_BUS_ID, request)


@router.get("/camera/{bus_id}")
def get_live_camera(bus_id: str, request: Request):
    """Frame kamera terbaru bus + bounding box deteksi (URL bertanda tangan, berumur pendek).

    404 bila bus belum pernah mengirim frame; 410 bila frame terakhir sudah
    melewati LIVE_CV_TTL_SECONDS. 503 bila Supabase gagal (tabel/bucket belum ada,
    jaringan, kredensial), supaya bisa dibedakan dari kamera yang memang offline.
    """
    try:
        return frame_terbaru(request.app.state.supabase, bus_id)
    except BusTidakDikenal:
        raise HTTPException(status_code=404, detail="Bus tidak dikenal")
    except FrameBasi:
        raise HTTPException(status_code=410, detail="Frame kamera basi")
    except Exception:
        logger.exception("Gagal membaca frame kamera bus %s dari Supabase", bus_id)
        raise HTTPException(status_code=503, detail="Layanan kamera tidak tersedia")
