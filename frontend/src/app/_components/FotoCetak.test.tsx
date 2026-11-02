// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { GalatApi } from '@/lib/api';

import { FotoCetak } from './FotoCetak';
import { PanelKamera } from './PanelKamera';

const mocks = vi.hoisted(() => ({ ambilSnapshot: vi.fn(), buatFotoThermal: vi.fn() }));
vi.mock('@/lib/photobox', async (impor) => ({
  ...(await impor<typeof import('@/lib/photobox')>()),
  ambilSnapshot: mocks.ambilSnapshot,
  buatFotoThermal: mocks.buatFotoThermal,
}));

const SNAP = { bus_id: 'CV-1', frame_b64: 'AAAA', bboxes: [], updated_at: '2026-10-15T03:00:00+00:00' };
const FOTO = { dataUrl: 'data:image/png;base64,AAAA', lebar: 576, tinggi: 432, jumlahDeteksi: 7 };

beforeEach(() => {
  mocks.ambilSnapshot.mockReset();
  mocks.buatFotoThermal.mockReset();
  vi.stubGlobal('print', vi.fn());
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('FotoCetak', () => {
  it('menampilkan pratinjau, jumlah deteksi, dan baru bisa dicetak setelah foto siap', async () => {
    mocks.ambilSnapshot.mockResolvedValue(SNAP);
    mocks.buatFotoThermal.mockResolvedValue(FOTO);
    render(<FotoCetak onTutup={() => {}} />);

    expect((screen.getByRole('button', { name: /Cetak/ }) as HTMLButtonElement).disabled).toBe(true);
    expect(await screen.findByAltText(/Foto kamera bus/)).toBeTruthy();
    expect(screen.getByText('7 penumpang')).toBeTruthy();
    expect(screen.getByText('CV-1')).toBeTruthy();

    const cetak = screen.getByRole('button', { name: /Cetak/ }) as HTMLButtonElement;
    expect(cetak.disabled).toBe(false);
    fireEvent.click(cetak);
    expect(window.print).toHaveBeenCalledOnce();
  });

  it('menutup dialog setelah pencetakan selesai (afterprint)', async () => {
    mocks.ambilSnapshot.mockResolvedValue(SNAP);
    mocks.buatFotoThermal.mockResolvedValue(FOTO);
    const onTutup = vi.fn();
    render(<FotoCetak onTutup={onTutup} />);
    await screen.findByAltText(/Foto kamera bus/);

    fireEvent.click(screen.getByRole('button', { name: /Cetak/ }));
    expect(onTutup).not.toHaveBeenCalled();
    window.dispatchEvent(new Event('afterprint'));
    expect(onTutup).toHaveBeenCalledOnce();
  });

  it('frame basi: tampilkan pesan, cetak nonaktif, Ulangi mengambil snapshot lagi', async () => {
    mocks.ambilSnapshot.mockRejectedValueOnce(new GalatApi(410, 'Frame kamera basi')).mockResolvedValueOnce(SNAP);
    mocks.buatFotoThermal.mockResolvedValue(FOTO);
    render(<FotoCetak onTutup={() => {}} />);

    expect((await screen.findByRole('status')).textContent).toMatch(/basi/);
    expect((screen.getByRole('button', { name: /Cetak/ }) as HTMLButtonElement).disabled).toBe(true);

    fireEvent.click(screen.getByRole('button', { name: 'Ulangi' }));
    expect(await screen.findByAltText(/Foto kamera bus/)).toBeTruthy();
    expect(mocks.ambilSnapshot).toHaveBeenCalledTimes(2);
  });

  it('Escape menutup dialog', () => {
    mocks.ambilSnapshot.mockReturnValue(new Promise(() => {}));
    const onTutup = vi.fn();
    render(<FotoCetak onTutup={onTutup} />);
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onTutup).toHaveBeenCalledOnce();
  });
});

describe('PanelKamera + photobox', () => {
  function renderPanel(respons: Response) {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respons));
    render(
      <QueryClientProvider client={new QueryClient()}>
        <PanelKamera />
      </QueryClientProvider>,
    );
  }

  it('tombol Ambil Foto hanya muncul saat kamera aktif dan membuka dialog', async () => {
    mocks.ambilSnapshot.mockReturnValue(new Promise(() => {}));
    renderPanel(new Response(JSON.stringify({ bus_id: 'CV-1', frame_url: 'https://s.test/f.jpg', bboxes: [], updated_at: '2026-10-15T03:00:00+00:00' })));
    fireEvent.click(await screen.findByRole('button', { name: /Ambil Foto/ }));
    await waitFor(() => expect(screen.getByRole('dialog', { name: 'Cetak foto kamera' })).toBeTruthy());
  });

  it('tidak ada tombol saat kamera basi', async () => {
    renderPanel(new Response(JSON.stringify({ detail: 'x' }), { status: 410 }));
    await screen.findByText('BASI');
    expect(screen.queryByRole('button', { name: /Ambil Foto/ })).toBeNull();
  });
});
