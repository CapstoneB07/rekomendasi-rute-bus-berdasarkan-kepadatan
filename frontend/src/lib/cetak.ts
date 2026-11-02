// Cetak ke printer thermal yang terpasang di komputer backend (POST /api/print/*).
// Foto (photobox) dan tiket rencana perjalanan memakai printer dan jalur yang sama.

import { API_BASE, GalatApi } from '@/lib/api';

export async function kirimKePrinter(jalur: '/api/print/foto' | '/api/print/tiket', isi: unknown): Promise<void> {
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
  if (err instanceof GalatApi && err.status === 503) return 'Printer tidak dapat dihubungi. Pastikan printer menyala dan sudah ter-pairing, lalu ulangi.';
  return `${objek} gagal dicetak. Pastikan server backend berjalan, lalu ulangi.`;
}
