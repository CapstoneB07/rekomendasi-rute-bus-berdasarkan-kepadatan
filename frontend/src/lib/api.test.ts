import { describe, expect, it } from 'vitest';

import { GalatApi, galatRute, waktuWib } from './api';

describe('waktuWib', () => {
  it('mengonversi UTC ke WIB (UTC+7) dalam detik sejak tengah malam', () => {
    // Rabu 2026-10-07 02:30:15 UTC = 09:30:15 WIB
    const w = waktuWib(new Date('2026-10-07T02:30:15Z'));
    expect(w.jam).toBe(9);
    expect(w.detik).toBe(9 * 3600 + 30 * 60 + 15);
    expect(w.label).toBe('09:30');
    expect(w.hariTipe).toBe('weekday');
  });

  it('memakai hari WIB, bukan UTC, untuk weekend', () => {
    // Jumat 2026-10-09 18:00 UTC = Sabtu 01:00 WIB
    expect(waktuWib(new Date('2026-10-09T18:00:00Z')).hariTipe).toBe('weekend');
  });
});

describe('galatRute', () => {
  it('menampilkan pesan backend untuk 404 dan tidak menawarkan coba lagi', () => {
    const g = galatRute(new GalatApi(404, 'Tidak ditemukan rute dari A ke B'));
    expect(g.judul).toBe('Rute tidak ditemukan');
    expect(g.pesan).toBe('Tidak ditemukan rute dari A ke B');
    expect(g.bisaCoba).toBe(false);
  });

  it('memakai pesan bawaan bila detail kosong', () => {
    expect(galatRute(new GalatApi(404, '')).pesan).toMatch(/Tidak ada rute/);
  });

  it('menawarkan coba lagi untuk 5xx dan jaringan putus', () => {
    expect(galatRute(new GalatApi(503, 'x')).bisaCoba).toBe(true);
    const jaringan = galatRute(new TypeError('Failed to fetch'));
    expect(jaringan.judul).toBe('Layanan sedang bermasalah');
    expect(jaringan.bisaCoba).toBe(true);
  });
});
