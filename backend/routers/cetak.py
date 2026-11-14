import base64
import binascii
import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import thermal_printer

router = APIRouter(prefix="/api/print")
logger = logging.getLogger(__name__)

Baris = Annotated[str, Field(max_length=48)]
Teks = Annotated[str, Field(max_length=200)]


class FotoCetak(BaseModel):
    """Bitmap 1-bit hasil dither di browser: bit 1 = titik hitam, tiap baris dibulatkan ke byte."""

    lebar: int = Field(ge=8, le=thermal_printer.LEBAR_MAKS_DOT, multiple_of=8)
    tinggi: int = Field(ge=1, le=thermal_printer.TINGGI_MAKS_DOT)
    bits_b64: str = Field(max_length=thermal_printer.LEBAR_MAKS_DOT // 8 * thermal_printer.TINGGI_MAKS_DOT * 4 // 3 + 8)
    baris: list[Baris] = Field(default_factory=list, max_length=10)


@router.post("/foto")
def cetak_foto(body: FotoCetak) -> dict[str, str]:
    """Cetak foto kamera ke printer thermal yang terhubung ke komputer backend."""
    try:
        bits = base64.b64decode(body.bits_b64, validate=True)
        data = thermal_printer.susun_escpos(body.lebar, body.tinggi, bits, body.baris)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Bitmap tidak valid") from exc
    try:
        thermal_printer.kirim(data)
    except thermal_printer.PrinterGagal as exc:
        logger.warning("cetak foto gagal: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "ok"}


class BarisTiket(BaseModel):
    teks: Teks = ""
    kanan: Teks = ""
    tebal: bool = False
    besar: bool = False
    tengah: bool = False
    garis: bool = False


class TiketCetak(BaseModel):
    """Isi tiket sebagai baris teks; tata letak kolom dikerjakan di backend."""

    baris: list[BarisTiket] = Field(min_length=1, max_length=80)


@router.post("/tiket")
def cetak_tiket(body: TiketCetak) -> dict[str, str]:
    """Cetak tiket rencana perjalanan ke printer thermal yang terhubung ke komputer backend."""
    data = thermal_printer.susun_escpos_teks([thermal_printer.BarisTeks(**b.model_dump()) for b in body.baris])
    try:
        thermal_printer.kirim(data)
    except thermal_printer.PrinterGagal as exc:
        logger.warning("cetak tiket gagal: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "ok"}
