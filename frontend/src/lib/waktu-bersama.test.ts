import { describe, expect, it } from 'vitest';

import { hitungSimTime, JAM_MULAI, JAM_SELESAI, type KeadaanWaktu } from './use-waktu-simulasi';

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
  it('selisih jam perangkat dengan server dikoreksi lewat parameter waktu', () => {
    const selisih = 5_000; // jam perangkat tertinggal 5 detik dari server
    expect(hitungSimTime(dasar, dasar.ts + 30_000 - 0 + selisih)).toBe(8 * 3600 + 350);
  });
  it('live memakai jam nyata WIB', () => {
    const t = Date.UTC(2026, 0, 5, 1, 0, 0); // 08.00 WIB
    expect(hitungSimTime({ ...dasar, isLive: true }, t)).toBe(8 * 3600);
  });
});
