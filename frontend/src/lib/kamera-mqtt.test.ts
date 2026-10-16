// @vitest-environment jsdom
import { EventEmitter } from 'node:events';
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { KAMERA_TOPIK, payloadKeGambar, useKameraMqtt } from './kamera-mqtt';

class ClientPalsu extends EventEmitter {
  subscribe = vi.fn();
  end = vi.fn();
}
const mqttPalsu = vi.hoisted(() => ({ connect: vi.fn() }));
vi.mock('mqtt', () => ({ default: mqttPalsu }));

const JPEG = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 1, 2, 3]);
const teks = (s: string) => new TextEncoder().encode(s);
const base64 = btoa(String.fromCharCode(...JPEG));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  mqttPalsu.connect.mockReset();
});

describe('payloadKeGambar', () => {
  it('JPEG mentah diteruskan apa adanya', () => {
    expect(payloadKeGambar(JPEG)).toBe(JPEG);
  });

  it('base64 polos maupun data URL didekode', () => {
    expect(payloadKeGambar(teks(base64))).toEqual(JPEG);
    expect(payloadKeGambar(teks(`data:image/jpeg;base64,${base64}\n`))).toEqual(JPEG);
  });

  it('payload kosong atau bukan gambar diabaikan', () => {
    expect(payloadKeGambar(new Uint8Array())).toBeNull();
    expect(payloadKeGambar(teks('{"bukan":"gambar"}'))).toBeNull();
  });
});

describe('useKameraMqtt', () => {
  it('berlangganan topik kamera lalu menampilkan frame terbaru', async () => {
    const client = new ClientPalsu();
    mqttPalsu.connect.mockReturnValue(client);
    const buat = vi.fn().mockReturnValueOnce('blob:1').mockReturnValueOnce('blob:2');
    const cabut = vi.fn();
    vi.stubGlobal('URL', { createObjectURL: buat, revokeObjectURL: cabut });

    const { result, unmount } = renderHook(() => useKameraMqtt());
    expect(result.current.status).toBe('menyambung');
    await waitFor(() => expect(mqttPalsu.connect).toHaveBeenCalled());

    act(() => {
      client.emit('connect');
    });
    expect(client.subscribe).toHaveBeenCalledWith(KAMERA_TOPIK);
    expect(result.current.status).toBe('menunggu');

    act(() => {
      client.emit('message', KAMERA_TOPIK, JPEG);
      client.emit('message', KAMERA_TOPIK, teks(base64));
    });
    expect(result.current.status).toBe('aktif');
    expect(result.current.frame?.src).toBe('blob:2');
    expect(cabut).toHaveBeenCalledWith('blob:1');

    unmount();
    expect(client.end).toHaveBeenCalledWith(true);
    expect(cabut).toHaveBeenCalledWith('blob:2');
  });
});
