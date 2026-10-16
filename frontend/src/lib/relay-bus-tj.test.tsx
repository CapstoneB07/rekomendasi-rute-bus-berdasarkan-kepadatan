// @vitest-environment jsdom
import { EventEmitter } from 'node:events';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { pangkasPesan, statusDariGalat, topikLangganan, useRelayBusTj } from './relay-bus-tj';

class ClientPalsu extends EventEmitter {
  subscribe = vi.fn();
  end = vi.fn();
}
const mqttPalsu = vi.hoisted(() => ({ connect: vi.fn() }));
vi.mock('mqtt', () => ({ default: mqttPalsu }));

const pesan = (override: Record<string, unknown> = {}) =>
  JSON.stringify({
    route_code: '1',
    bus_body_no: 'TJ-826',
    trip_id: '1-R01',
    latitude: -6.2,
    longitude: 106.8,
    bearing: 28,
    eta: 2,
    passengers_status: '',
    route_color: '#ff0000',
    stops: [{ name: 'Transvision', stop_id: 'B05802P', parent_stop_id: 'P1', eta: 2, latitude: -6.2 }],
    ...override,
  });

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  mqttPalsu.connect.mockReset();
});

describe('pangkasPesan', () => {
  it('hanya menyimpan field yang dipakai backend', () => {
    expect(pangkasPesan(pesan())).toEqual({
      route_code: '1',
      bus_body_no: 'TJ-826',
      trip_id: '1-R01',
      latitude: -6.2,
      longitude: 106.8,
      bearing: 28,
      eta: 2,
      stops: [{ name: 'Transvision', stop_id: 'B05802P', parent_stop_id: 'P1', eta: 2 }],
    });
  });

  it('payload rusak atau tanpa nomor bus diabaikan', () => {
    expect(pangkasPesan('bukan json')).toBeNull();
    expect(pangkasPesan('null')).toBeNull();
    expect(pangkasPesan(pesan({ bus_body_no: undefined }))).toBeNull();
  });
});

describe('statusDariGalat', () => {
  it('penolakan broker = ditolak, galat lain = terputus', () => {
    expect(statusDariGalat(Object.assign(new Error('Connection refused: Not authorized'), { code: 5 }))).toBe('ditolak');
    expect(statusDariGalat(new Error('connack timeout'))).toBe('terputus');
  });
});

it('topik per route_code', () => {
  expect(topikLangganan(['1', 'JAK.01'])).toEqual(['/mobile_armada/+/1/#', '/mobile_armada/+/JAK.01/#']);
});

describe('useRelayBusTj', () => {
  function jalankan() {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fetchPalsu = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(async (url) =>
      url.endsWith('/api/live/koridor') ? Response.json({ route_codes: ['1', '9'] }) : Response.json({}),
    );
    vi.stubGlobal('fetch', fetchPalsu);
    const client = new ClientPalsu();
    mqttPalsu.connect.mockReturnValue(client);
    const qc = new QueryClient();
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const hook = renderHook(() => useRelayBusTj(), { wrapper });
    const kiriman = () =>
      fetchPalsu.mock.calls
        .filter(([url]) => url.endsWith('/api/live/buses'))
        .map(([, init]) => JSON.parse(init?.body as string));
    return { client, hook, kiriman };
  }

  it('berlangganan dengan client ID mqttjs_ lalu meneruskan bus terbaru tiap 5 detik', async () => {
    const { client, hook, kiriman } = jalankan();
    await waitFor(() => expect(mqttPalsu.connect).toHaveBeenCalled());
    expect(mqttPalsu.connect.mock.calls[0][1].clientId).toMatch(/^mqttjs_[0-9a-f]{8}$/);

    client.emit('connect');
    expect(client.subscribe).toHaveBeenCalledWith(['/mobile_armada/+/1/#', '/mobile_armada/+/9/#']);
    client.emit('message', 't', pesan({ latitude: -6.1 }));
    client.emit('message', 't', pesan({ latitude: -6.3 })); // menimpa pesan lama bus yang sama
    await act(() => vi.advanceTimersByTimeAsync(5_000));

    expect(kiriman()).toEqual([{ status: 'tersambung', buses: [expect.objectContaining({ latitude: -6.3 })] }]);

    hook.unmount();
    expect(client.end).toHaveBeenCalled();
  });

  it('tidak melapor sebelum ada kabar broker; penolakan dilaporkan sebagai ditolak', async () => {
    const { client, kiriman } = jalankan();
    await waitFor(() => expect(mqttPalsu.connect).toHaveBeenCalled());

    await act(() => vi.advanceTimersByTimeAsync(5_000));
    expect(kiriman()).toEqual([]);

    client.emit('error', Object.assign(new Error('Connection refused: Not authorized'), { code: 5 }));
    client.emit('close');
    await act(() => vi.advanceTimersByTimeAsync(5_000));
    expect(kiriman()).toEqual([{ status: 'ditolak', buses: [] }]);
  });
});
