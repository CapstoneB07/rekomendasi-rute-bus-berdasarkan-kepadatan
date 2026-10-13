// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { JAM_MULAI, type WaktuSimulasi } from '@/lib/use-waktu-simulasi';

import { WaktuKontrol } from './WaktuKontrol';

function buatWaktu(ubah: Partial<WaktuSimulasi> = {}): WaktuSimulasi {
  return {
    simTime: JAM_MULAI,
    isLive: false,
    isPlaying: true,
    kecepatan: 1,
    aturJam: vi.fn(),
    togglePlay: vi.fn(),
    aturKecepatan: vi.fn(),
    kembaliKeLive: vi.fn(),
    ...ubah,
  };
}

afterEach(cleanup);

describe('WaktuKontrol', () => {
  it('menggeser slider mengatur jam simulasi', () => {
    const waktu = buatWaktu();
    render(<WaktuKontrol waktu={waktu} />);
    fireEvent.change(screen.getByLabelText('Geser jam simulasi'), { target: { value: '28800' } });
    expect(waktu.aturJam).toHaveBeenCalledWith(28800);
  });

  it('tombol mainkan/jeda memanggil togglePlay dan labelnya mengikuti status', () => {
    const waktu = buatWaktu({ isPlaying: false });
    render(<WaktuKontrol waktu={waktu} />);
    fireEvent.click(screen.getByRole('button', { name: 'Jalankan jam' }));
    expect(waktu.togglePlay).toHaveBeenCalledOnce();
    cleanup();
    render(<WaktuKontrol waktu={buatWaktu({ isPlaying: true })} />);
    expect(screen.getByRole('button', { name: 'Jeda jam' })).toBeTruthy();
  });

  it('memilih kecepatan memanggil aturKecepatan dan menandai kecepatan aktif', () => {
    const waktu = buatWaktu({ kecepatan: 10 });
    render(<WaktuKontrol waktu={waktu} />);
    fireEvent.click(screen.getByRole('button', { name: '60×' }));
    expect(waktu.aturKecepatan).toHaveBeenCalledWith(60);
    expect(screen.getByRole('button', { name: '10×' }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByRole('button', { name: '5×' }).getAttribute('aria-pressed')).toBe('false');
  });

  it('tombol waktu nyata aktif saat simulasi dan kembali ke live saat diklik', () => {
    const waktu = buatWaktu();
    render(<WaktuKontrol waktu={waktu} />);
    fireEvent.click(screen.getByRole('button', { name: 'Waktu nyata' }));
    expect(waktu.kembaliKeLive).toHaveBeenCalledOnce();
    cleanup();
    render(<WaktuKontrol waktu={buatWaktu({ isLive: true })} />);
    expect((screen.getByRole('button', { name: '● Waktu nyata' }) as HTMLButtonElement).disabled).toBe(true);
  });
});
