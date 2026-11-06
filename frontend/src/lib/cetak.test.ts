import { afterEach, describe, expect, it, vi } from 'vitest';

import { GalatApi } from './api';
import { kirimKePrinter, pesanGalatCetak } from './cetak';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

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

describe('kirimKePrinter lewat antrean cetak', () => {
  const json = (isi: unknown, status = 200) => new Response(JSON.stringify(isi), { status });
  // POST menjawab "antre"; tiap GET status berikutnya mengambil satu jawaban dari `jawaban`.
  const siapkan = (jawaban: (Response | Error)[]) => {
    const fetchMock = vi.fn().mockResolvedValueOnce(json({ status: 'antre', id: 42 }, 202));
    for (const j of jawaban) {
      if (j instanceof Error) fetchMock.mockRejectedValueOnce(j);
      else fetchMock.mockResolvedValueOnce(j);
    }
    vi.useFakeTimers();
    vi.stubGlobal('fetch', fetchMock);
    return fetchMock;
  };

  it('menunggu sampai status selesai', async () => {
    const fetchMock = siapkan([json({ status: 'menunggu', galat: null }), json({ status: 'mencetak', galat: null }), json({ status: 'selesai', galat: null })]);
    const hasil = kirimKePrinter('/api/print/tiket', { baris: [] });
    await vi.advanceTimersByTimeAsync(3000);
    await expect(hasil).resolves.toBeUndefined();
    expect(String(fetchMock.mock.calls[1][0])).toMatch(/\/api\/print\/antrean\/42$/);
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it('status gagal menjadi GalatApi 503 dengan pesan agen', async () => {
    siapkan([json({ status: 'gagal', galat: 'Agen cetak tidak merespons' })]);
    const hasil = kirimKePrinter('/api/print/foto', {});
    const dicek = expect(hasil).rejects.toMatchObject({ status: 503, message: 'Agen cetak tidak merespons' });
    await vi.advanceTimersByTimeAsync(1000);
    await dicek;
  });

  it('galat jaringan atau 5xx sesaat tidak menggagalkan, polling lanjut', async () => {
    siapkan([new TypeError('putus'), json({ detail: 'x' }, 503), json({ status: 'selesai', galat: null })]);
    const hasil = kirimKePrinter('/api/print/tiket', { baris: [] });
    await vi.advanceTimersByTimeAsync(3000);
    await expect(hasil).resolves.toBeUndefined();
  });

  it('404 saat polling = gagal langsung', async () => {
    siapkan([json({ detail: 'Cetakan tidak ditemukan' }, 404)]);
    const hasil = kirimKePrinter('/api/print/tiket', { baris: [] });
    const dicek = expect(hasil).rejects.toMatchObject({ status: 404 });
    await vi.advanceTimersByTimeAsync(1000);
    await dicek;
  });

  it('berhenti menunggu setelah batas waktu (503 printer tidak merespons)', async () => {
    const fetchMock = siapkan([]);
    fetchMock.mockImplementation(() => Promise.resolve(json({ status: 'menunggu', galat: null })));
    const hasil = kirimKePrinter('/api/print/tiket', { baris: [] });
    const dicek = expect(hasil).rejects.toMatchObject({ status: 503 });
    await vi.advanceTimersByTimeAsync(41_000);
    await dicek;
  });
});

describe('pesanGalatCetak', () => {
  it('503 = printer tidak terjangkau; lainnya menyebut objek yang gagal dicetak', () => {
    expect(pesanGalatCetak(new GalatApi(503, ''), 'Tiket')).toMatch(/Printer tidak dapat dihubungi/);
    expect(pesanGalatCetak(new Error('x'), 'Tiket')).toMatch(/^Tiket gagal dicetak/);
    expect(pesanGalatCetak(new Error('x'), 'Foto')).toMatch(/^Foto gagal dicetak/);
  });
});
