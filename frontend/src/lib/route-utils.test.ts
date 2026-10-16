import { describe, expect, it } from 'vitest';

import { statusBusAsli, type PosisiBusAsliResponse, type StatusBroker } from './route-utils';

const respons = (status: StatusBroker, n: number): PosisiBusAsliResponse => ({
  type: 'FeatureCollection',
  status,
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
    expect(statusBusAsli(respons('tersambung', 3), true)).toMatch(/tidak dapat dimuat/);
  });

  it('belum ada data = memuat', () => {
    expect(statusBusAsli(undefined, false)).toMatch(/Memuat/);
  });

  it('broker belum tersambung', () => {
    expect(statusBusAsli(respons('menyambung', 0), false)).toMatch(/Menyambung/);
  });

  it('broker menolak koneksi = bus asli tidak tersedia', () => {
    expect(statusBusAsli(respons('ditolak', 0), false)).toMatch(/menolak koneksi/);
  });

  it('koneksi broker terputus = mencoba lagi', () => {
    expect(statusBusAsli(respons('terputus', 0), false)).toMatch(/terputus/);
  });

  it('menampilkan jumlah bus', () => {
    expect(statusBusAsli(respons('tersambung', 42), false)).toBe('42 bus asli di peta');
  });
});
