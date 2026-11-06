// Cetak ke printer thermal. Foto (photobox) dan tiket rencana perjalanan memakai jalur yang sama.
// Di browser dengan Web Bluetooth, ESC/POS disusun di sini dan dikirim langsung ke printer lewat BLE
// (jalan dari perangkat mana pun). Selain itu dikirim ke backend (POST /api/print/*) yang menulis
// ke printer di komputernya. Bila backend tidak berada di komputer printer (produksi), ia hanya
// menaruh cetakan di antrean (jawaban "antre"); agen cetak di komputer printer yang mencetaknya,
// dan di sini kita menunggu hasilnya.

import { API_BASE, GalatApi } from '@/lib/api';
import { susunEscposFoto, susunEscposTeks } from '@/lib/escpos';
import { bleDidukung, GalatBle, kirimBle } from '@/lib/printer-ble';
import type { BarisCetak } from '@/lib/tiket';

type IsiFoto = { lebar: number; tinggi: number; bits_b64: string; baris: string[] };

function bytesDariBase64(b64: string): Uint8Array {
  const bin = atob(b64);
  return Uint8Array.from(bin, (c) => c.charCodeAt(0));
}

// Database menggugurkan cetakan yang tidak diambil agen dalam 30 dtk; batas ini sedikit di atasnya
// plus waktu cetak foto.
const JEDA_POLLING_MS = 1000;
const BATAS_TUNGGU_MS = 40_000;

async function tungguCetakSelesai(id: number): Promise<void> {
  const batas = Date.now() + BATAS_TUNGGU_MS;
  while (Date.now() < batas) {
    await new Promise((r) => setTimeout(r, JEDA_POLLING_MS));
    // Jaringan putus-sambung atau 5xx sesaat tidak berarti cetakan gagal: lanjut menunggu sampai batas.
    const r = await fetch(`${API_BASE}/api/print/antrean/${id}`, { cache: 'no-store' }).catch(() => null);
    if (!r || r.status >= 500) continue;
    if (!r.ok) throw new GalatApi(r.status, '');
    const { status, galat } = (await r.json()) as { status: string; galat: string | null };
    if (status === 'selesai') return;
    if (status === 'gagal') throw new GalatApi(503, galat ?? '');
  }
  throw new GalatApi(503, 'Printer tidak merespons');
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
  const hasil = await r.json().catch(() => null);
  if (hasil?.status === 'antre' && typeof hasil.id === 'number') await tungguCetakSelesai(hasil.id);
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
