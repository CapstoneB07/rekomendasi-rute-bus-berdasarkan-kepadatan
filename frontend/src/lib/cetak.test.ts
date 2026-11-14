import { afterEach, describe, expect, it, vi } from 'vitest';

import { GalatApi } from './api';
import { kirimKePrinter, pesanGalatCetak } from './cetak';

afterEach(() => vi.unstubAllGlobals());

describe('kirimKePrinter', () => {
  it('POST JSON ke jalur cetak', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{"status":"ok"}'));
    vi.stubGlobal('fetch', fetchMock);
    await kirimKePrinter('/api/print/tiket', { baris: [{ teks: 'x' }] });
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/api\/print\/tiket$/);
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ baris: [{ teks: 'x' }] });
  });

  it('respons gagal menjadi GalatApi dengan status-nya', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'mati' }), { status: 503 })));
    await expect(kirimKePrinter('/api/print/foto', {})).rejects.toMatchObject({ status: 503, message: expect.any(String) });
  });
});

describe('pesanGalatCetak', () => {
  it('503 = printer tidak terjangkau; lainnya menyebut objek yang gagal dicetak', () => {
    expect(pesanGalatCetak(new GalatApi(503, ''), 'Tiket')).toMatch(/Printer tidak dapat dihubungi/);
    expect(pesanGalatCetak(new Error('x'), 'Tiket')).toMatch(/^Tiket gagal dicetak/);
    expect(pesanGalatCetak(new Error('x'), 'Foto')).toMatch(/^Foto gagal dicetak/);
  });
});
