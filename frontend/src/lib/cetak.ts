// Cetak ke printer thermal. Foto (photobox) dan tiket rencana perjalanan memakai jalur yang sama.
// Di browser dengan Web Bluetooth, ESC/POS disusun di sini dan dikirim langsung ke printer lewat BLE
// (jalan dari perangkat mana pun). Selain itu dikirim ke backend (POST /api/print/*) yang menulis
// ke printer di komputernya.

import { API_BASE, GalatApi } from '@/lib/api';
import { susunEscposFoto, susunEscposTeks } from '@/lib/escpos';
import { bleDidukung, GalatBle, kirimBle } from '@/lib/printer-ble';
import type { BarisCetak } from '@/lib/tiket';

type IsiFoto = { lebar: number; tinggi: number; bits_b64: string; baris: string[] };

function bytesDariBase64(b64: string): Uint8Array {
  const bin = atob(b64);
  return Uint8Array.from(bin, (c) => c.charCodeAt(0));
}

export async function kirimKePrinter(jalur: '/api/print/foto' | '/api/print/tiket', isi: unknown): Promise<void> {
  if (bleDidukung()) {
    // Disusun sinkron sebelum dialog pemilihan printer, supaya klik pengguna masih berlaku.
    const data =
      jalur === '/api/print/tiket'
        ? susunEscposTeks((isi as { baris: BarisCetak[] }).baris)
        : susunEscposFoto((isi as IsiFoto).lebar, (isi as IsiFoto).tinggi, bytesDariBase64((isi as IsiFoto).bits_b64), (isi as IsiFoto).baris);
    return kirimBle(data);
  }
  const r = await fetch(`${API_BASE}${jalur}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(isi),
  });
  if (!r.ok) {
    const body = await r.json().catch(() => null);
    throw new GalatApi(r.status, typeof body?.detail === 'string' ? body.detail : '');
  }
}

// Pesan untuk operator/penumpang; 503 berarti printer tidak terjangkau, bukan server mati.
export function pesanGalatCetak(err: unknown, objek: 'Foto' | 'Tiket'): string {
  if (err instanceof GalatBle) {
    if (err.jenis === 'dibatalkan') return 'Pemilihan printer dibatalkan. Tekan cetak lagi dan pilih printer RPP02N.';
    return `Printer Bluetooth tidak dapat dihubungi (${err.message}). Pastikan printer menyala dan dekat, lalu ulangi.`;
  }
  if (err instanceof GalatApi && err.status === 503) return 'Printer tidak dapat dihubungi. Pastikan printer menyala dan sudah ter-pairing, lalu ulangi.';
  return `${objek} gagal dicetak. Pastikan server backend berjalan, lalu ulangi.`;
}
