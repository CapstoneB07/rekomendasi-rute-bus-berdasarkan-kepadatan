// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { FrameKamera, PanelKamera } from './PanelKamera';

const BBOXES = [
  { x: 160, y: 120, w: 320, h: 240, kelas: 'person', skor: 0.9 },
  { x: 0, y: 0, w: 64, h: 48, kelas: 'person', skor: 0.55 },
];

function muatGambar(lebar: number, tinggi: number) {
  const img = screen.getByAltText('Frame kamera bus');
  Object.defineProperty(img, 'naturalWidth', { value: lebar });
  Object.defineProperty(img, 'naturalHeight', { value: tinggi });
  fireEvent.load(img);
}

function renderPanel(respons: Response) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respons));
  const client = new QueryClient();
  render(
    <QueryClientProvider client={client}>
      <PanelKamera />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('FrameKamera', () => {
  it('menskalakan bbox ke persen ukuran asli gambar setelah gambar dimuat', () => {
    render(<FrameKamera src="https://storage.test/f.jpg" bboxes={BBOXES} />);
    expect(screen.queryAllByTestId('bbox')).toHaveLength(0);

    muatGambar(640, 480);
    const [besar, kecil] = screen.getAllByTestId('bbox');
    expect(besar.style.left).toBe('25%');
    expect(besar.style.top).toBe('25%');
    expect(besar.style.width).toBe('50%');
    expect(besar.style.height).toBe('50%');
    expect(kecil.style.width).toBe('10%');
    expect(kecil.style.height).toBe('10%');
    expect(screen.getByText('person 0.55')).toBeTruthy();
  });
});

describe('PanelKamera', () => {
  it('menampilkan frame dan jumlah deteksi saat data segar', async () => {
    renderPanel(
      new Response(
        JSON.stringify({
          bus_id: 'CV-1',
          frame_url: 'https://storage.test/f.jpg',
          bboxes: BBOXES,
          updated_at: '2026-10-15T03:00:00+00:00',
        }),
      ),
    );
    expect((await screen.findByText(/deteksi/)).textContent).toBe('2 deteksi · 10:00:00');
    expect(screen.getByText('AKTIF')).toBeTruthy();
    expect(screen.getByAltText('Frame kamera bus')).toBeTruthy();
  });

  it('menandai frame basi tanpa menampilkan gambar lama', async () => {
    renderPanel(new Response(JSON.stringify({ detail: 'Frame kamera basi' }), { status: 410 }));
    expect((await screen.findByText(/Frame kamera basi/)).getAttribute('role')).toBe('status');
    expect(screen.getByText('BASI')).toBeTruthy();
    expect(screen.queryByAltText('Frame kamera bus')).toBeNull();
  });

  it('menampilkan offline bila bus belum pernah mengirim frame', async () => {
    renderPanel(new Response(JSON.stringify({ detail: 'Bus tidak dikenal' }), { status: 404 }));
    expect(await screen.findByText(/Kamera offline/)).toBeTruthy();
    expect(screen.getByText('OFFLINE')).toBeTruthy();
  });
});
