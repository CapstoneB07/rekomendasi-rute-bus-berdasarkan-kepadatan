// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { Rute } from '@/lib/route-utils';

import { DetailRencana } from './DetailRencana';

const JAM_8 = 8 * 3600;

const RUTE = {
  estimasi_menit: 35,
  segmen: [
    {
      tipe: 'naik',
      koridor_id: 1,
      naik_di: 'Harmoni',
      turun_di: 'Monas',
      waktu_menit: 6,
      bus_rekomendasi: { bus_id: 'TJ-101', eta_menit: 4, leg_clock_detik: JAM_8, label_kepadatan: 'Sepi' },
    },
    { tipe: 'transit', transit_di: 'Monas', ke_koridor: 13 },
    { tipe: 'naik', koridor_id: 13, naik_di: 'Monas', turun_di: 'Blok M', waktu_menit: 20, bus_rekomendasi: null },
  ],
} as unknown as Rute;

function tampilkan() {
  const onKembali = vi.fn();
  render(<DetailRencana rute={RUTE} asal="Harmoni" tujuan="Blok M" simTime={JAM_8} onKembali={onKembali} />);
  return { onKembali };
}

afterEach(cleanup);

describe('DetailRencana', () => {
  it('menampilkan tiap leg dengan bus, jam naik/turun, dan transit', () => {
    tampilkan();
    expect(screen.getByText('Ke Blok M')).toBeTruthy();
    expect(screen.getByText('TJ-101')).toBeTruthy();
    expect(screen.getByText('08.04')).toBeTruthy();
    expect(screen.getByText('· 6 menit')).toBeTruthy();
    expect(screen.getByText('08.10')).toBeTruthy();
    expect(screen.getByText('Sepi')).toBeTruthy();
    expect(screen.getByText(/Pindah bus di/).textContent).toBe('Pindah bus di Monas ke koridor 13');
    expect(screen.getByText('Belum ada bus terjadwal')).toBeTruthy();
  });

  it('tombol Kembali memanggil onKembali', () => {
    const { onKembali } = tampilkan();
    fireEvent.click(screen.getByRole('button', { name: 'Kembali' }));
    expect(onKembali).toHaveBeenCalledOnce();
  });

  it('Cetak Informasi membuka pratinjau tiket; Cetak memanggil print, Tutup menutupnya', () => {
    const print = vi.spyOn(window, 'print').mockImplementation(() => {});
    tampilkan();
    fireEvent.click(screen.getByRole('button', { name: 'Cetak Informasi' }));

    const tiket = within(screen.getByRole('dialog', { name: 'Tiket perjalanan' }));
    expect(tiket.getByText(/^TJ-\d{6}-\d{6}-[0-9A-F]{4}$/)).toBeTruthy();
    expect(tiket.getByText('Harmoni')).toBeTruthy();
    expect(tiket.getByText('35 menit')).toBeTruthy();
    expect(tiket.getByText('Pindah di Monas ke koridor 13')).toBeTruthy();

    fireEvent.click(tiket.getByRole('button', { name: 'Cetak' }));
    expect(print).toHaveBeenCalledOnce();

    fireEvent.click(tiket.getByRole('button', { name: 'Tutup' }));
    expect(screen.queryByRole('dialog')).toBeNull();
    print.mockRestore();
  });
});
