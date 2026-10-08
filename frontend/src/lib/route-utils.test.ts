import { describe, expect, it } from 'vitest';

import { statusBusAsli, type PosisiBusAsliResponse } from './route-utils';

const respons = (connected: boolean, n: number): PosisiBusAsliResponse => ({
  type: 'FeatureCollection',
  connected,
  features: Array.from({ length: n }, () => ({
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [106.8, -6.2] },
    properties: {
      bus_id: 'TJ-1',
      koridor_id: 1,
      bearing: 0,
      next_stop: 'Halte',
      eta_minutes: 1,
      data_source: 'tj_live',
      trip_load_factor: null,
      label_kepadatan: null,
      estimated_passengers: null,
      capacity: null,
    },
  })),
});

describe('statusBusAsli', () => {
  it('error menang atas data lama', () => {
    expect(statusBusAsli(respons(true, 3), true)).toMatch(/tidak dapat dimuat/);
  });

  it('belum ada data = memuat', () => {
    expect(statusBusAsli(undefined, false)).toMatch(/Memuat/);
  });

  it('broker belum tersambung', () => {
    expect(statusBusAsli(respons(false, 0), false)).toMatch(/Menyambung/);
  });

  it('menampilkan jumlah bus', () => {
    expect(statusBusAsli(respons(true, 42), false)).toBe('42 bus asli di peta');
  });
});
