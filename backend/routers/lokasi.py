"""Halte lokasi kiosk yang dipilih operator, dibagikan ke halaman beranda: operator menulis, kiosk membaca."""

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/lokasi")


class LokasiInput(BaseModel):
    halte_id: str = Field(min_length=1, max_length=64)


@router.get("")
def baca_lokasi(request: Request):
    return {"lokasi": getattr(request.app.state, "lokasi", None)}


@router.put("")
def atur_lokasi(request: Request, body: LokasiInput):
    request.app.state.lokasi = body
    return {"lokasi": body}
