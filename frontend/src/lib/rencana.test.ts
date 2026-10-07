import { describe, expect, it } from 'vitest';

import { jumlahTransit, labelRencana } from './rencana';
import type { Rute } from './route-utils';

const rute = (estimasi_menit: number, rata_kepadatan: number, naik = 1): Rute =>
  ({
    estimasi_menit,
    rata_kepadatan,
    segmen: Array.from({ length: naik }, () => ({ tipe: 'naik' })),
  }) as unknown as Rute;

describe('labelRencana', () => {
  it('tanpa label bila hanya ada satu rencana', () => {
    expect(labelRencana([rute(20, 0.5)])).toEqual([[]]);
  });

  it('menandai tercepat dan paling lega pada rencana berbeda', () => {
    expect(labelRencana([rute(30, 0.2), rute(20, 0.8)])).toEqual([['Paling lega'], ['Tercepat']]);
  });

  it('satu rencana bisa memegang dua label; seri jatuh ke yang pertama', () => {
    expect(labelRencana([rute(20, 0.3), rute(20, 0.3)])).toEqual([['Tercepat', 'Paling lega'], []]);
  });
});

describe('jumlahTransit', () => {
  it('jumlah naik dikurangi satu, tidak negatif', () => {
    expect(jumlahTransit(rute(10, 0, 3))).toBe(2);
    expect(jumlahTransit(rute(10, 0, 1))).toBe(0);
    expect(jumlahTransit(rute(10, 0, 0))).toBe(0);
  });
});
