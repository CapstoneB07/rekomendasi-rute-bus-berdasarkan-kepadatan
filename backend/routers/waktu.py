"""Jam simulasi bersama untuk demo multi-perangkat: operator menulis, kiosk membaca."""

import time

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from routers.rute import MAX_SIM_TIME_DETIK

router = APIRouter(prefix="/api/waktu")


class KeadaanWaktu(BaseModel):
    """Jangkar jam: `sim_time` (detik dalam hari) berlaku pada `ts` (epoch ms, diberi stempel server)."""

    is_live: bool = True
    is_playing: bool = True
    kecepatan: int = Field(default=1, ge=1, le=600)
    sim_time: int = Field(default=0, ge=0, le=MAX_SIM_TIME_DETIK)
    ts: int = 0


class KeadaanWaktuInput(BaseModel):
    is_live: bool
    is_playing: bool
    kecepatan: int = Field(ge=1, le=600)
    sim_time: int = Field(ge=0, le=MAX_SIM_TIME_DETIK)


def _sekarang_ms() -> int:
    return int(time.time() * 1000)


@router.get("")
def baca_waktu(request: Request):
    """Keadaan jam terakhir plus jam server, supaya klien menghitung selisih jamnya sendiri."""
    keadaan = getattr(request.app.state, "waktu", None) or KeadaanWaktu()
    return {"keadaan": keadaan, "server_now": _sekarang_ms()}


@router.put("")
def atur_waktu(request: Request, body: KeadaanWaktuInput):
    keadaan = KeadaanWaktu(**body.model_dump(), ts=_sekarang_ms())
    request.app.state.waktu = keadaan
    return {"keadaan": keadaan, "server_now": keadaan.ts}
