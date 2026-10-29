"""Pencarian rute terakhir di kiosk, dibagikan ke halaman operator untuk animasi rute: kiosk menulis, operator membaca."""

import time

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/pencarian")


class PencarianInput(BaseModel):
    halte_asal: str = Field(min_length=1, max_length=64)
    halte_tujuan: str = Field(min_length=1, max_length=64)
    # Rencana yang sedang dipilih di kartu daftar rencana kiosk.
    aktif_idx: int = Field(default=0, ge=0, le=20)


class Pencarian(PencarianInput):
    """`ts` (epoch ms, stempel server) berganti tiap pembaruan, jadi operator bisa memutar ulang animasinya."""

    ts: int


@router.get("")
def baca_pencarian(request: Request):
    return {"pencarian": getattr(request.app.state, "pencarian", None)}


@router.put("")
def atur_pencarian(request: Request, body: PencarianInput):
    pencarian = Pencarian(**body.model_dump(), ts=int(time.time() * 1000))
    request.app.state.pencarian = pencarian
    return {"pencarian": pencarian}


@router.delete("")
def hapus_pencarian(request: Request):
    request.app.state.pencarian = None
    return {"pencarian": None}
