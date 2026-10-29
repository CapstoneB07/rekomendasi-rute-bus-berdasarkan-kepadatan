import { readFileSync } from 'node:fs';

import { describe, expect, it } from 'vitest';

import { bearingNaikDiAtas, potongGarisRute, statusBusAsli, WARNA_KEPADATAN, type PosisiBusAsliResponse, type StatusBroker } from './route-utils';

describe('WARNA_KEPADATAN', () => {
  // Peta (MapLibre) butuh nilai warna di JS, kelas Tailwind butuh token CSS; keduanya harus satu palet.
  it('sama dengan token --color-tj-* di globals.css', () => {
    const css = readFileSync(new URL('../app/globals.css', import.meta.url), 'utf8');
    for (const [nama, warna] of Object.entries(WARNA_KEPADATAN)) {
      expect(css).toMatch(new RegExp(`--color-tj-${nama}:\\s*${warna};`, 'i'));
    }
  });
});

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

describe('potongGarisRute', () => {
  const fitur = (koordinat: number[][]): GeoJSON.Feature<GeoJSON.LineString> => ({
    type: 'Feature',
    geometry: { type: 'LineString', coordinates: koordinat },
    properties: {},
  });
  // Dua garis di khatulistiwa masing-masing sepanjang 1 derajat, bersambung: total 2.
  const garis: GeoJSON.FeatureCollection<GeoJSON.LineString> = {
    type: 'FeatureCollection',
    features: [fitur([[0, 0], [1, 0]]), fitur([[1, 0], [2, 0]])],
  };

  it('0 kosong dan 1 utuh', () => {
    expect(potongGarisRute(garis, 0).features).toHaveLength(0);
    expect(potongGarisRute(garis, 1)).toEqual(garis);
  });

  it('memangkas fitur yang terpotong tepat di titik fraksinya', () => {
    const [satu, dua] = potongGarisRute(garis, 0.75).features;
    expect(satu).toEqual(garis.features[0]);
    expect(dua.geometry.coordinates[0]).toEqual([1, 0]);
    expect(dua.geometry.coordinates.at(-1)![0]).toBeCloseTo(1.5);
  });

  it('fraksi di luar rentang dijepit', () => {
    expect(potongGarisRute(garis, 5)).toEqual(garis);
    expect(potongGarisRute(garis, -1).features).toHaveLength(0);
  });
});

describe('bearingNaikDiAtas', () => {
  const asal = { lng: 106.8, lat: -6.2 };
  it('NAIK sudah di utara TURUN: peta tidak perlu diputar', () => {
    expect(bearingNaikDiAtas({ ...asal, lat: -6.1 }, asal)).toBeCloseTo(0);
  });
  it('TURUN di utara NAIK: peta dibalik 180 derajat', () => {
    expect(bearingNaikDiAtas(asal, { ...asal, lat: -6.1 })).toBeCloseTo(180);
  });
  it('TURUN di timur NAIK: peta menghadap barat (270) supaya NAIK di atas', () => {
    expect(bearingNaikDiAtas(asal, { ...asal, lng: 106.9 })).toBeCloseTo(270);
  });
  it('halte berimpit tidak memutar peta', () => {
    expect(bearingNaikDiAtas(asal, asal)).toBe(0);
  });
});
