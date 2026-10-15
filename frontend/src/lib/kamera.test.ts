import { describe, expect, it } from 'vitest';

import { GalatApi } from './api';
import { skalaBbox, statusKamera, type FrameKameraResponse } from './kamera';

const bbox = (x: number, y: number, w: number, h: number) => ({ x, y, w, h, kelas: 'person', skor: 0.9 });

describe('skalaBbox', () => {
  it('mengubah piksel frame asli menjadi persen ukuran gambar', () => {
    expect(skalaBbox(bbox(160, 120, 320, 240), 640, 480)).toEqual({ left: 25, top: 25, width: 50, height: 50 });
  });

  it('hasilnya sama untuk frame beresolusi berbeda dengan posisi relatif sama', () => {
    expect(skalaBbox(bbox(480, 270, 960, 540), 1920, 1080)).toEqual(
      skalaBbox(bbox(160, 90, 320, 180), 640, 360),
    );
  });

  it('memotong kotak yang keluar dari tepi gambar', () => {
    expect(skalaBbox(bbox(-40, 400, 200, 200), 400, 500)).toEqual({ left: 0, top: 80, width: 40, height: 20 });
  });
});

describe('statusKamera', () => {
  const data: FrameKameraResponse = { bus_id: 'CV-1', frame_url: 'u', bboxes: [], updated_at: 't' };

  it('memetakan respons dan galat backend ke status panel', () => {
    expect(statusKamera(undefined, null)).toBe('memuat');
    expect(statusKamera(data, null)).toBe('aktif');
    expect(statusKamera(data, new GalatApi(410, 'basi'))).toBe('basi');
    expect(statusKamera(undefined, new GalatApi(404, 'x'))).toBe('offline');
    expect(statusKamera(undefined, new TypeError('Failed to fetch'))).toBe('galat');
  });
});
