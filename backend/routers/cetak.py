import base64
import binascii
import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Response
from pydantic import BaseModel, Field

from services import antrean_cetak, thermal_printer

router = APIRouter(prefix="/api/print")
logger = logging.getLogger(__name__)

Baris = Annotated[str, Field(max_length=48)]
Teks = Annotated[str, Field(max_length=200)]


def _cetak(jenis: str, data: bytes, response: Response) -> dict[str, str | int]:
    """Cetak langsung ke printer komputer ini, atau (PRINT_MODE=antrean) titipkan ke agen cetak."""
    if antrean_cetak.aktif():
        try:
            id_cetak = antrean_cetak.antre(jenis, data)
        except antrean_cetak.AntreanGagal as exc:
            logger.warning("antre cetak %s gagal: %s", jenis, exc)
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        response.status_code = 202
        return {"status": "antre", "id": id_cetak}
    try:
        thermal_printer.kirim(data)
    except thermal_printer.PrinterGagal as exc:
        logger.warning("cetak %s gagal: %s", jenis, exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "ok"}


class FotoCetak(BaseModel):
    """Bitmap 1-bit hasil dither di browser: bit 1 = titik hitam, tiap baris dibulatkan ke byte."""

    lebar: int = Field(ge=8, le=thermal_printer.LEBAR_MAKS_DOT, multiple_of=8)
    tinggi: int = Field(ge=1, le=thermal_printer.TINGGI_MAKS_DOT)
    bits_b64: str = Field(max_length=thermal_printer.LEBAR_MAKS_DOT // 8 * thermal_printer.TINGGI_MAKS_DOT * 4 // 3 + 8)
    baris: list[Baris] = Field(default_factory=list, max_length=10)


@router.post("/foto")
def cetak_foto(body: FotoCetak, response: Response) -> dict[str, str | int]:
    """Cetak foto kamera ke printer thermal (langsung, atau lewat antrean cetak bila PRINT_MODE=antrean)."""
    try:
        bits = base64.b64decode(body.bits_b64, validate=True)
        data = thermal_printer.susun_escpos(body.lebar, body.tinggi, bits, body.baris)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Bitmap tidak valid") from exc
    return _cetak("foto", data, response)


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
def cetak_tiket(body: TiketCetak, response: Response) -> dict[str, str | int]:
    """Cetak tiket rencana perjalanan ke printer thermal (langsung, atau lewat antrean bila PRINT_MODE=antrean)."""
    data = thermal_printer.susun_escpos_teks([thermal_printer.BarisTeks(**b.model_dump()) for b in body.baris])
    return _cetak("tiket", data, response)


@router.get("/antrean/{id_cetak}")
def status_antrean(id_cetak: Annotated[int, Path(ge=1, le=9_223_372_036_854_775_807)]) -> dict[str, str | None]:
    """Status satu cetakan di antrean: menunggu | mencetak | selesai | gagal (+ galat)."""
    if not antrean_cetak.aktif():
        raise HTTPException(status_code=404, detail="Antrean cetak tidak aktif")
    try:
        baris = antrean_cetak.status(id_cetak)
    except antrean_cetak.AntreanGagal as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if baris is None:
        raise HTTPException(status_code=404, detail="Cetakan tidak ditemukan")
    return {"status": baris["status"], "galat": baris["galat"]}
