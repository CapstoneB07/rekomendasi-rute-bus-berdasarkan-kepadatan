import { afterEach, describe, expect, it, vi } from 'vitest';

import { GalatApi } from './api';
import { ambilSnapshot, ditherThermal, gambarKotak, kemasBit, kirimCetak, pesanGalatCetak, pesanGalatFoto, ukuranCetak } from './photobox';

function rgba(lebar: number, tinggi: number, luma: (x: number, y: number) => number) {
  const data = new Uint8ClampedArray(lebar * tinggi * 4);
  for (let y = 0; y < tinggi; y++)
    for (let x = 0; x < lebar; x++) {
      const i = (y * lebar + x) * 4;
      data[i] = data[i + 1] = data[i + 2] = luma(x, y);
      data[i + 3] = 255;
    }
  return { data, width: lebar, height: tinggi };
}

const hitam = (img: { data: Uint8ClampedArray }) => {
  let n = 0;
  for (let i = 0; i < img.data.length; i += 4) if (img.data[i] === 0) n++;
  return n;
};

afterEach(() => vi.unstubAllGlobals());

describe('ukuranCetak', () => {
  it('menskalakan ke 576 dot dengan menjaga rasio', () => {
    expect(ukuranCetak(1280, 720)).toEqual({ lebar: 576, tinggi: 324 });
    expect(ukuranCetak(640, 480)).toEqual({ lebar: 576, tinggi: 432 });
  });
});

describe('ditherThermal', () => {
  it('hanya menghasilkan piksel 0 atau 255 dengan alpha penuh', () => {
    const img = rgba(40, 30, (x, y) => (x * 6 + y * 3) % 256);
    ditherThermal(img);
    for (let i = 0; i < img.data.length; i += 4) {
      expect([0, 255]).toContain(img.data[i]);
      expect(img.data[i + 1]).toBe(img.data[i]);
      expect(img.data[i + 2]).toBe(img.data[i]);
      expect(img.data[i + 3]).toBe(255);
    }
  });

  it('abu-abu menengah menjadi campuran hitam-putih kira-kira seimbang', () => {
    const img = rgba(64, 64, () => 128);
    ditherThermal(img);
    const rasio = hitam(img) / (64 * 64);
    expect(rasio).toBeGreaterThan(0.35);
    expect(rasio).toBeLessThan(0.65);
  });

  it('meregangkan kontras: foto kusam tidak menjadi putih/hitam rata', () => {
    // Nada sempit 100..140 tanpa regangan akan jatuh ke satu sisi ambang.
    const img = rgba(64, 64, (x) => 100 + (x % 40));
    ditherThermal(img);
    const rasio = hitam(img) / (64 * 64);
    expect(rasio).toBeGreaterThan(0.2);
    expect(rasio).toBeLessThan(0.8);
  });

  it('frame hampir rata tidak diperbesar jadi derau', () => {
    const img = rgba(32, 32, () => 20);
    ditherThermal(img);
    // Tetap gelap (bukan diregangkan jadi pola 50/50 acak).
    expect(hitam(img) / (32 * 32)).toBeGreaterThan(0.85);
  });
});

describe('gambarKotak', () => {
  it('menggambar bingkai putih lalu hitam di koordinat yang diskalakan', () => {
    const strokeRect = vi.fn();
    const ctx = { strokeRect, lineWidth: 0, strokeStyle: '' };
    gambarKotak(ctx, [{ x: 160, y: 120, w: 320, h: 240, kelas: 'person', skor: 0.9 }], { lebar: 640, tinggi: 480 }, { lebar: 576, tinggi: 432 });
    expect(strokeRect).toHaveBeenCalledTimes(2);
    expect(strokeRect).toHaveBeenNthCalledWith(1, 144, 108, 288, 216);
    expect(ctx.strokeStyle).toBe('#000');
    expect(ctx.lineWidth).toBe(3);
  });
});

describe('ambilSnapshot', () => {
  it('melempar GalatApi dengan status dan detail dari backend', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'Frame kamera basi' }), { status: 410 })));
    const err = await ambilSnapshot().catch((e) => e);
    expect(err).toBeInstanceOf(GalatApi);
    expect(err.status).toBe(410);
    expect(err.message).toBe('Frame kamera basi');
  });

  it('mengembalikan snapshot saat sukses dan tidak memakai cache', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ bus_id: 'CV-1', frame_b64: 'AAAA', bboxes: [], updated_at: 'x' })));
    vi.stubGlobal('fetch', fetchMock);
    expect((await ambilSnapshot()).bus_id).toBe('CV-1');
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/api\/live\/camera\/snapshot$/);
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ cache: 'no-store' });
  });
});

describe('pesanGalatFoto', () => {
  it('membedakan basi, offline, layanan mati, dan galat umum', () => {
    expect(pesanGalatFoto(new GalatApi(410, ''))).toMatch(/basi/);
    expect(pesanGalatFoto(new GalatApi(404, ''))).toMatch(/offline/);
    expect(pesanGalatFoto(new GalatApi(503, ''))).toMatch(/tidak tersedia/);
    expect(pesanGalatFoto(new TypeError('Failed to fetch'))).toMatch(/gagal diambil/);
  });
});

describe('kemasBit', () => {
  it('1 bit per dot, 1 = hitam, bit tertinggi = dot paling kiri', () => {
    // 16 dot x 2 baris: baris 0 hitam di x=0 dan x=15, baris 1 hitam di x=8..10.
    const img = rgba(16, 2, (x, y) => ((y === 0 && (x === 0 || x === 15)) || (y === 1 && x >= 8 && x <= 10) ? 0 : 255));
    expect(Array.from(kemasBit(img))).toEqual([0b10000000, 0b00000001, 0b00000000, 0b11100000]);
  });
});

describe('kirimCetak', () => {
  afterEach(() => vi.unstubAllGlobals());
  const foto = { dataUrl: '', lebar: 384, tinggi: 10, jumlahDeteksi: 1, bitsB64: 'AAAA' };

  it('POST bitmap dan baris teks ke /api/print/foto', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{"status":"ok"}'));
    vi.stubGlobal('fetch', fetchMock);
    await kirimCetak(foto, ['Bus: CV-1']);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/api\/print\/foto$/);
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ lebar: 384, tinggi: 10, bits_b64: 'AAAA', baris: ['Bus: CV-1'] });
  });

  it('respons gagal menjadi GalatApi dengan status-nya', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'mati' }), { status: 503 })));
    await expect(kirimCetak(foto, [])).rejects.toMatchObject({ status: 503 });
    expect(pesanGalatCetak(new GalatApi(503, ''))).toMatch(/Printer tidak dapat dihubungi/);
    expect(pesanGalatCetak(new Error('x'))).toMatch(/gagal dicetak/);
  });
});
