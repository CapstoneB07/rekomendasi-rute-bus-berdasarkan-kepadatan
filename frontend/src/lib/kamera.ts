// Tipe + helper untuk panel kamera bus (GET /api/live/camera).

import { GalatApi } from '@/lib/api';

// x, y, w, h dalam piksel frame asli (x, y = pojok kiri atas); skor 0..1.
export type Bbox = { x: number; y: number; w: number; h: number; kelas: string; skor: number };

export type FrameKameraResponse = {
  bus_id: string;
  frame_url: string;
  bboxes: Bbox[];
  updated_at: string;
};

export type KotakPersen = { left: number; top: number; width: number; height: number };

const batas = (v: number, maks: number) => Math.min(Math.max(v, 0), maks);

// Bbox piksel → persen ukuran gambar, dipotong ke tepi gambar. Persen membuat
// kotak ikut skala berapa pun lebar gambar ditampilkan.
export function skalaBbox(b: Bbox, lebar: number, tinggi: number): KotakPersen {
  const x0 = batas(b.x, lebar);
  const y0 = batas(b.y, tinggi);
  const x1 = batas(b.x + b.w, lebar);
  const y1 = batas(b.y + b.h, tinggi);
  return {
    left: (x0 / lebar) * 100,
    top: (y0 / tinggi) * 100,
    width: ((x1 - x0) / lebar) * 100,
    height: ((y1 - y0) / tinggi) * 100,
  };
}

export type StatusKamera = 'memuat' | 'aktif' | 'basi' | 'offline' | 'galat';

// 410 = frame terakhir melewati TTL, 404 = bus belum pernah mengirim frame / belum dikonfigurasi.
export function statusKamera(data: FrameKameraResponse | undefined, error: unknown): StatusKamera {
  if (error instanceof GalatApi && error.status === 410) return 'basi';
  if (error instanceof GalatApi && error.status === 404) return 'offline';
  if (error) return 'galat';
  return data ? 'aktif' : 'memuat';
}
