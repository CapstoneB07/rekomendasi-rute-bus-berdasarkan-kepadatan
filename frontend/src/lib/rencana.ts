import type { Rute } from './route-utils';

export type LabelRencana = 'Tercepat' | 'Paling lega';

// Label pembeda antar rencana. Hanya bermakna bila ada lebih dari satu rencana; seri jatuh ke yang pertama.
export function labelRencana(daftar: Rute[]): LabelRencana[][] {
  const hasil: LabelRencana[][] = daftar.map(() => []);
  if (daftar.length < 2) return hasil;
  const terkecil = (nilai: (r: Rute) => number) =>
    daftar.reduce((best, r, i) => (nilai(r) < nilai(daftar[best]) ? i : best), 0);
  hasil[terkecil((r) => r.estimasi_menit)].push('Tercepat');
  hasil[terkecil((r) => r.rata_kepadatan)].push('Paling lega');
  return hasil;
}

export function jumlahTransit(rute: Rute): number {
  return Math.max(0, rute.segmen.filter((s) => s.tipe === 'naik').length - 1);
}
