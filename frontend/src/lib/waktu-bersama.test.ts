import { describe, expect, it } from 'vitest';

import { bacaKeadaanWaktu, hitungSimTime, JAM_MULAI, JAM_SELESAI, type KeadaanWaktu } from './use-waktu-simulasi';

const dasar: KeadaanWaktu = { isLive: false, isPlaying: true, kecepatan: 10, simTime: 8 * 3600, ts: 1_000_000 };

describe('hitungSimTime', () => {
  it('maju sesuai waktu dinding x kecepatan sejak jangkar', () => {
    expect(hitungSimTime(dasar, dasar.ts + 30_000)).toBe(8 * 3600 + 300);
  });
  it('diam saat dijeda', () => {
    expect(hitungSimTime({ ...dasar, isPlaying: false }, dasar.ts + 60_000)).toBe(8 * 3600);
  });
  it('kembali ke jam mulai setelah melewati jam selesai', () => {
    const k = { ...dasar, simTime: JAM_SELESAI - 5, kecepatan: 1 };
    expect(hitungSimTime(k, k.ts + 10_000)).toBe(JAM_MULAI + 5);
  });
  it('live memakai jam nyata WIB', () => {
    const t = Date.UTC(2026, 0, 5, 1, 0, 0); // 08.00 WIB
    expect(hitungSimTime({ ...dasar, isLive: true }, t)).toBe(8 * 3600);
  });
});

describe('bacaKeadaanWaktu', () => {
  it('membaca keadaan valid', () => {
    expect(bacaKeadaanWaktu(JSON.stringify(dasar))).toEqual(dasar);
  });
  it.each([null, '', 'bukan json', '{"isLive":1}'])('jatuh ke live untuk %j', (mentah) => {
    expect(bacaKeadaanWaktu(mentah).isLive).toBe(true);
  });
});
