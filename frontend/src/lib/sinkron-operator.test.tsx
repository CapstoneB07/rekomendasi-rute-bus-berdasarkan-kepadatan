// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { HalteOpsi } from './route-utils';
import { halteLokasiDefault, useAturLokasi, useLokasiOperator } from './use-lokasi';
import { useWaktuOperator } from './use-waktu-simulasi';

// Operator adalah satu-satunya penulis jam dan lokasi; kiosk dan operator membaca dari backend.
// Tes ini memastikan membuka/me-reload operator tidak menimpa pilihan yang sudah ada di backend.

const bungkus = () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return { client, wrapper: ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider> };
};

type Panggilan = { url: string; method: string; body?: unknown };

// Backend palsu dengan keadaan jam dan lokasi yang bisa ditimpa lewat PUT, seperti backend asli.
function pasangBackend(awal: { waktu?: object; lokasi?: string | null }) {
  const panggilan: Panggilan[] = [];
  let waktu = awal.waktu ?? { is_live: true, is_playing: true, kecepatan: 1, sim_time: 18000, ts: 0 };
  let lokasi = awal.lokasi ?? null;
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET';
      const body = init?.body ? JSON.parse(init.body as string) : undefined;
      panggilan.push({ url, method, body });
      if (url.endsWith('/api/waktu')) {
        if (method === 'PUT') waktu = { ...body, ts: Date.now() };
        return Response.json({ keadaan: waktu, server_now: Date.now() });
      }
      if (url.endsWith('/api/lokasi')) {
        if (method === 'PUT') lokasi = body.halte_id;
        return Response.json({ lokasi: lokasi ? { halte_id: lokasi } : null });
      }
      throw new Error(`url tak terduga: ${url}`);
    }),
  );
  return panggilan;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('useWaktuOperator', () => {
  it('memulai dari jam simulasi yang ada di backend dan tidak menimpanya saat dibuka', async () => {
    const siang = { is_live: false, is_playing: false, kecepatan: 1, sim_time: 14 * 3600, ts: Date.now() };
    const panggilan = pasangBackend({ waktu: siang });
    const { client, wrapper } = bungkus();
    const { result } = renderHook(() => useWaktuOperator(), { wrapper });

    await waitFor(() => expect(result.current.isLive).toBe(false));
    await waitFor(() => expect(result.current.tersinkron).toBe(true));
    expect(result.current.simTime).toBe(14 * 3600);
    expect(panggilan.filter((p) => p.method === 'PUT')).toEqual([]);
    client.clear();
  });

  it('hanya mengirim ke backend setelah operator mengubah jam', async () => {
    const panggilan = pasangBackend({});
    const { wrapper } = bungkus();
    const { result } = renderHook(() => useWaktuOperator(), { wrapper });
    await waitFor(() => expect(result.current.tersinkron).toBe(true));
    expect(panggilan.filter((p) => p.method === 'PUT')).toEqual([]);

    act(() => result.current.aturJam(9 * 3600));

    await waitFor(() => expect(panggilan.filter((p) => p.method === 'PUT')).toHaveLength(1));
    expect(panggilan.find((p) => p.method === 'PUT')?.body).toMatchObject({ is_live: false, sim_time: 9 * 3600 });
  });

  it('pilihan operator yang lebih baru menang atas keadaan backend yang datang terlambat', async () => {
    const siang = { is_live: false, is_playing: false, kecepatan: 1, sim_time: 14 * 3600, ts: Date.now() };
    pasangBackend({ waktu: siang });
    const { wrapper } = bungkus();
    const { result } = renderHook(() => useWaktuOperator(), { wrapper });

    act(() => result.current.aturJam(6 * 3600)); // sebelum respons GET awal diproses
    await waitFor(() => expect(result.current.tersinkron).toBe(true));
    expect(result.current.simTime).toBe(6 * 3600);
  });

  it('menandai tidak tersinkron bila backend tidak terjangkau', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
    const { wrapper } = bungkus();
    const { result } = renderHook(() => useWaktuOperator(), { wrapper });
    await waitFor(() => expect(result.current.tersinkron).toBe(false));
  });
});

describe('lokasi bersama operator dan kiosk', () => {
  const halteList = [
    { halte_id: 'A', nama: 'Kota' },
    { halte_id: 'H', nama: 'Harmoni' },
  ] as HalteOpsi[];

  it('halte bawaan Harmoni; cadangan halte pertama', () => {
    expect(halteLokasiDefault(halteList)?.halte_id).toBe('H');
    expect(halteLokasiDefault([halteList[0]])?.halte_id).toBe('A');
    expect(halteLokasiDefault(undefined)).toBeUndefined();
  });

  it('operator yang dibuka ulang membaca halte yang sudah dipilih, bukan kosong', async () => {
    pasangBackend({ lokasi: 'G00670' });
    const { wrapper } = bungkus();
    const { result } = renderHook(() => useLokasiOperator(), { wrapper });
    await waitFor(() => expect(result.current).toBe('G00670'));
  });

  it('memilih halte menampilkannya langsung dan menulisnya ke backend untuk kiosk', async () => {
    const panggilan = pasangBackend({ lokasi: null });
    const { wrapper } = bungkus();
    const { result } = renderHook(() => ({ lokasi: useLokasiOperator(), atur: useAturLokasi() }), { wrapper });
    await waitFor(() => expect(panggilan.some((p) => p.method === 'GET')).toBe(true));

    await act(async () => result.current.atur('H'));

    await waitFor(() => expect(panggilan.find((p) => p.method === 'PUT')?.body).toEqual({ halte_id: 'H' }));
    await waitFor(() => expect(result.current.lokasi).toBe('H'));
  });

  it('bila kirim gagal, tampilan kembali ke halte di backend yang juga dilihat kiosk', async () => {
    const panggilan = pasangBackend({ lokasi: 'A' });
    const fetchAsli = globalThis.fetch as unknown as (u: string, i?: RequestInit) => Promise<Response>;
    vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => (init?.method === 'PUT' ? Promise.reject(new Error('putus')) : fetchAsli(url, init))));
    const { wrapper } = bungkus();
    const { result } = renderHook(() => ({ lokasi: useLokasiOperator(), atur: useAturLokasi() }), { wrapper });
    await waitFor(() => expect(result.current.lokasi).toBe('A'));

    await act(async () => result.current.atur('H'));

    await waitFor(() => expect(result.current.lokasi).toBe('A'));
    expect(panggilan.filter((p) => p.method === 'PUT')).toEqual([]);
  });
});
