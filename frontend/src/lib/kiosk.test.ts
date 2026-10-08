import { describe, expect, it } from 'vitest';

import { arahDerajat } from './animasi-bus';
import { formatJam, formatKm, formatRupiah, formatTanggal, warnaKoridor } from './koridor';
import { daftarKelompok, filterKelompok, halaman, KELOMPOK_UTAMA } from './pilih-halte';
import type { HalteOpsi } from './route-utils';

const h = (id: string, nama: string, koridor: number[]): HalteOpsi => ({
  halte_id: id,
  nama,
  lat: 0,
  lng: 0,
  koridor_list: koridor,
});

describe('format kiosk', () => {
  it('jam memakai titik dan membungkus 24 jam', () => {
    expect(formatJam(14 * 3600 + 7 * 60 + 59)).toBe('14.07');
    expect(formatJam(5 * 3600)).toBe('05.00');
    expect(formatJam(24 * 3600 + 90)).toBe('00.01');
  });

  it('tanggal Indonesia lengkap dengan hari (WIB)', () => {
    expect(formatTanggal(new Date('2026-06-08T07:00:00Z'))).toBe('Senin, 8 Juni 2026');
  });

  it('rupiah dan km', () => {
    expect(formatRupiah(3500)).toBe('Rp3.500');
    expect(formatKm(3500)).toBe('3.5 km');
    expect(formatKm(undefined)).toBeNull();
  });

  it('warna koridor dikenal dan cadangan abu-abu', () => {
    expect(warnaKoridor(1).bg).toBe('#D62126');
    expect(warnaKoridor('12').teks).toBe('#000000');
    expect(warnaKoridor(99).bg).toBe('#6B7280');
  });
});

describe('arahDerajat', () => {
  it('utara, timur, selatan, barat', () => {
    expect(arahDerajat([106, -6], [106, -5.99])).toBe(0);
    expect(arahDerajat([106, -6], [106.01, -6])).toBe(90);
    expect(arahDerajat([106, -6], [106, -6.01])).toBe(180);
    expect(arahDerajat([106, -6], [105.99, -6])).toBe(270);
  });

  it('praktis diam = null', () => {
    expect(arahDerajat([106, -6], [106, -6])).toBeNull();
  });
});

describe('pilih halte', () => {
  const list = [
    h('1', 'Monas', [1, 2]),
    h('2', 'Glodok', [1]),
    h('3', 'Harmoni', [1]),
    h('4', 'Gambir', [2, 3]),
  ];

  it('kelompok: utama dulu bila ada transit, lalu huruf terurut', () => {
    expect(daftarKelompok(list)).toEqual([KELOMPOK_UTAMA, 'G', 'H', 'M']);
    expect(daftarKelompok([h('1', 'Glodok', [1])])).toEqual(['G']);
  });

  it('filter per kelompok terurut nama', () => {
    expect(filterKelompok(list, 'G').map((x) => x.nama)).toEqual(['Gambir', 'Glodok']);
    expect(filterKelompok(list, KELOMPOK_UTAMA).map((x) => x.nama)).toEqual(['Gambir', 'Monas']);
  });

  it('peron kembar bernama sama ditampilkan satu (id terkecil)', () => {
    const kembar = [h('G2', 'Gunung Sahari', [5]), h('G1', 'Gunung Sahari', [5]), h('G3', 'Glodok', [1])];
    expect(filterKelompok(kembar, 'G').map((x) => x.halte_id)).toEqual(['G3', 'G1']);
  });

  it('halaman dijepit dan tidak pernah kosong', () => {
    const items = Array.from({ length: 25 }, (_, i) => i);
    expect(halaman(items, 0, 12)).toMatchObject({ jumlah: 3, idx: 0, items: items.slice(0, 12) });
    expect(halaman(items, 99, 12)).toMatchObject({ idx: 2, items: [24] });
    expect(halaman(items, -5, 12).idx).toBe(0);
    expect(halaman([], 0, 12)).toMatchObject({ jumlah: 1, idx: 0, items: [] });
  });
});
