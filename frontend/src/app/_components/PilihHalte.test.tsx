// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { HalteOpsi } from '@/lib/route-utils';

import { PilihHalte } from './PilihHalte';

const halte = (halte_id: string, nama: string, koridor_list = [1]): HalteOpsi =>
  ({ halte_id, nama, lat: 0, lng: 0, koridor_list }) as HalteOpsi;

const DAFTAR = [
  halte('H1', 'Harmoni', [1, 2]),
  halte('H2', 'Monas', [1, 2]),
  halte('H3', 'Blok M'),
  halte('H4', 'Bundaran HI'),
  halte('H5', 'Halimun'),
];

function tampilkan(ubah: Partial<Parameters<typeof PilihHalte>[0]> = {}) {
  const props = { judul: 'Pilih tujuan', halteList: DAFTAR, onPilih: vi.fn(), onTutup: vi.fn(), ...ubah };
  render(<PilihHalte {...props} />);
  return props;
}

const kartu = (nama: string) => screen.getByRole('button', { name: new RegExp(`^${nama}`) });

afterEach(cleanup);

describe('PilihHalte', () => {
  it('dibuka di kelompok utama (halte transit) dan memilih halte memanggil onPilih', () => {
    const p = tampilkan();
    expect(screen.getByRole('tab', { name: '★ Utama' }).getAttribute('aria-selected')).toBe('true');
    expect(screen.queryByRole('button', { name: 'Blok M' })).toBeNull();
    fireEvent.click(kartu('Monas'));
    expect(p.onPilih).toHaveBeenCalledWith('H2');
  });

  it('tab huruf menyaring halte berdasarkan huruf awal', () => {
    tampilkan();
    fireEvent.click(screen.getByRole('tab', { name: 'B' }));
    expect(kartu('Blok M')).toBeTruthy();
    expect(kartu('Bundaran HI')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Harmoni' })).toBeNull();
  });

  it('halte lawan nonaktif dan menampilkan alasannya', () => {
    const p = tampilkan({ nonaktifNama: 'Harmoni', nonaktifAlasan: 'Halte asal' });
    const harmoni = kartu('Harmoni') as HTMLButtonElement;
    expect(harmoni.disabled).toBe(true);
    expect(harmoni.textContent).toContain('Halte asal');
    fireEvent.click(harmoni);
    expect(p.onPilih).not.toHaveBeenCalled();
  });

  it('paging membagi halte per 12 dan menonaktifkan tombol di ujung', () => {
    const banyak = Array.from({ length: 14 }, (_, i) => halte(`S${i}`, `Senen ${String(i).padStart(2, '0')}`));
    tampilkan({ halteList: banyak });
    expect(screen.getByText('Halaman 1 dari 2')).toBeTruthy();
    const sebelumnya = screen.getByRole('button', { name: 'Sebelumnya' }) as HTMLButtonElement;
    expect(sebelumnya.disabled).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Berikutnya' }));
    expect(screen.getByText('Halaman 2 dari 2')).toBeTruthy();
    expect(kartu('Senen 13')).toBeTruthy();
    expect((screen.getByRole('button', { name: 'Berikutnya' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('Kembali dan Escape menutup pemilih', () => {
    const p = tampilkan();
    fireEvent.click(screen.getByRole('button', { name: 'Kembali' }));
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(p.onTutup).toHaveBeenCalledTimes(2);
  });
});
