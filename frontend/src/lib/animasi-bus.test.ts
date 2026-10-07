import { describe, expect, it } from 'vitest';

import {
  DURASI_MAKS_MS,
  DURASI_MIN_MS,
  LOMPAT_MAKS_DERAJAT,
  OPSI_BUS_SIMULASI,
  PenganimasiBus,
} from './animasi-bus';
import type { PosisiBusAsliResponse } from './route-utils';

const data = (...bus: Array<[string, number, number]>): PosisiBusAsliResponse => ({
  type: 'FeatureCollection',
  connected: true,
  features: bus.map(([id, lng, lat]) => ({
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [lng, lat] },
    properties: {
      bus_id: id,
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

const posisi = (a: PenganimasiBus, t: number, id = 'A') =>
  a.frame(t).features.find((f) => f.properties.bus_id === id)?.geometry.coordinates;

describe('PenganimasiBus', () => {
  it('bus baru langsung tampil di posisinya tanpa meluncur dari mana pun', () => {
    const a = new PenganimasiBus();
    a.perbarui(data(['A', 106.8, -6.2]), 0);
    expect(posisi(a, 0)).toEqual([106.8, -6.2]);
    expect(posisi(a, 10_000)).toEqual([106.8, -6.2]);
  });

  it('bergerak mulus ke posisi baru selama selisih waktu antar pembaruan', () => {
    const a = new PenganimasiBus();
    a.perbarui(data(['A', 106.0, -6.0]), 0);
    a.perbarui(data(['A', 106.01, -6.01]), 30_000); // selang 30 dtk -> durasi 30 dtk

    expect(posisi(a, 30_000)).toEqual([106.0, -6.0]); // belum bergerak
    const [lng, lat] = posisi(a, 45_000)!; // tepat separuh jalan
    expect(lng).toBeCloseTo(106.005);
    expect(lat).toBeCloseTo(-6.005);
    expect(posisi(a, 60_000)).toEqual([106.01, -6.01]);
    expect(posisi(a, 90_000)).toEqual([106.01, -6.01]); // berhenti di tujuan
  });

  it('pembaruan di tengah gerakan melanjutkan dari posisi yang sedang tampil (tanpa lompat)', () => {
    const a = new PenganimasiBus();
    a.perbarui(data(['A', 0, 0]), 0);
    a.perbarui(data(['A', 0.01, 0]), 20_000); // durasi 20 dtk
    const tengah = posisi(a, 30_000)![0]; // separuh jalan = 0.005
    a.perbarui(data(['A', 0.01, 0.01]), 30_000);

    expect(tengah).toBeCloseTo(0.005);
    expect(posisi(a, 30_000)).toEqual([tengah, 0]);
  });

  it('durasi dibatasi antara minimum dan maksimum', () => {
    const cepat = new PenganimasiBus();
    cepat.perbarui(data(['A', 0, 0]), 0);
    cepat.perbarui(data(['A', 0.01, 0]), 1_000); // selang 1 dtk -> dipaksa minimum
    expect(posisi(cepat, 1_000 + DURASI_MIN_MS)).toEqual([0.01, 0]);
    expect(posisi(cepat, 1_000 + DURASI_MIN_MS - 1)![0]).toBeLessThan(0.01);

    const lama = new PenganimasiBus();
    lama.perbarui(data(['A', 0, 0]), 0);
    lama.perbarui(data(['A', 0.01, 0]), 600_000); // selang 10 menit -> dipaksa maksimum
    expect(posisi(lama, 600_000 + DURASI_MAKS_MS)).toEqual([0.01, 0]);
    expect(posisi(lama, 600_000 + DURASI_MAKS_MS - 1)![0]).toBeLessThan(0.01);
  });

  it('bus yang hilang dari data dibuang, properti terbaru dipakai', () => {
    const a = new PenganimasiBus();
    a.perbarui(data(['A', 0, 0], ['B', 1, 1]), 0);
    const baru = data(['A', 0, 0]);
    baru.features[0].properties.next_stop = 'Halte Baru';
    a.perbarui(baru, 1_000);

    const frame = a.frame(1_000);
    expect(frame.features.map((f) => f.properties.bus_id)).toEqual(['A']);
    expect(frame.features[0].properties.next_stop).toBe('Halte Baru');
  });

  it('perpindahan jauh (geser jam, GPS loncat) langsung dipasang tanpa meluncur', () => {
    const a = new PenganimasiBus();
    a.perbarui(data(['A', 106.0, -6.0]), 0);
    a.perbarui(data(['A', 106.0 + LOMPAT_MAKS_DERAJAT * 2, -6.0]), 30_000);

    expect(posisi(a, 30_000)).toEqual([106.0 + LOMPAT_MAKS_DERAJAT * 2, -6.0]);
  });

  it('opsi simulasi memakai durasi pendek mengikuti interval pembaruan 1 detik', () => {
    const a = new PenganimasiBus(OPSI_BUS_SIMULASI);
    a.perbarui(data(['A', 0, 0]), 0);
    a.perbarui(data(['A', 0.01, 0]), 1_000); // selang 1 dtk -> durasi 1 dtk

    expect(posisi(a, 1_500)![0]).toBeCloseTo(0.005);
    expect(posisi(a, 2_000)).toEqual([0.01, 0]);
  });

  it('bergerak() false setelah semua bus sampai tujuan', () => {
    const a = new PenganimasiBus();
    a.perbarui(data(['A', 0, 0]), 0);
    a.perbarui(data(['A', 0.01, 0]), 10_000); // durasi 10 dtk

    expect(a.bergerak(15_000)).toBe(true);
    expect(a.bergerak(20_000)).toBe(false);
  });
});
