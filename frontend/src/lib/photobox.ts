// Photobox operator: ambil frame kamera + bbox yang berpasangan, ubah ke gambar 1-bit
// untuk printer thermal 80 mm, dan siapkan datanya untuk struk (FotoCetak).

import { API_BASE, GalatApi } from '@/lib/api';
import { kirimKePrinter } from '@/lib/cetak';
import { skalaBbox, type Bbox } from '@/lib/kamera';

// Area cetak printer thermal 80 mm = 576 dot (72 mm x 8 dot/mm, 203 dpi). Gambar dibuat
// persis selebar ini agar tiap piksel gambar = satu dot, tanpa di-resample driver.
export const LEBAR_DOT_80MM = 576;

// Hasil GET /api/live/camera/snapshot: frame JPEG dan bbox dari baris yang sama.
export type SnapshotKamera = {
  bus_id: string;
  frame_b64: string;
  bboxes: Bbox[];
  updated_at: string;
};

export type FotoThermal = {
  dataUrl: string;
  lebar: number;
  tinggi: number;
  jumlahDeteksi: number;
  // Bitmap 1-bit (bit 1 = hitam, 8 dot per byte) dalam base64, untuk POST /api/print/foto.
  bitsB64: string;
};

type PikselRgba = { data: Uint8ClampedArray; width: number; height: number };

export function ukuranCetak(lebarAsli: number, tinggiAsli: number, lebarDot = LEBAR_DOT_80MM) {
  return { lebar: lebarDot, tinggi: Math.max(1, Math.round((tinggiAsli * lebarDot) / lebarAsli)) };
}

// Batas gelap/terang di persentil 2 dan 98, supaya bayangan pekat atau langit putih tidak
// menyempitkan rentang nada foto bus yang cenderung kusam.
function batasNada(luma: Float32Array): [number, number] {
  const hist = new Uint32Array(256);
  for (const v of luma) hist[Math.min(255, Math.max(0, Math.round(v)))]++;
  const target = luma.length * 0.02;
  let lo = 0;
  let hi = 255;
  for (let i = 0, acc = 0; i < 256; i++) {
    acc += hist[i];
    if (acc > target) {
      lo = i;
      break;
    }
  }
  for (let i = 255, acc = 0; i >= 0; i--) {
    acc += hist[i];
    if (acc > target) {
      hi = i;
      break;
    }
  }
  return [lo, hi];
}

// Ubah RGBA ke hitam-putih murni di tempat: grayscale, regangkan kontras, lalu dither
// Floyd-Steinberg. Printer thermal hanya punya titik hitam atau kosong; tanpa dither foto
// menjadi bercak hitam. Setelah ini setiap piksel bernilai 0 atau 255.
export function ditherThermal({ data, width, height }: PikselRgba): void {
  const n = width * height;
  const luma = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    luma[i] = 0.299 * data[i * 4] + 0.587 * data[i * 4 + 1] + 0.114 * data[i * 4 + 2];
  }

  const [lo, hi] = batasNada(luma);
  // Frame hampir rata (kamera tertutup/gelap total): jangan memperbesar derau jadi pola acak.
  const rentang = hi - lo;
  if (rentang >= 16) {
    for (let i = 0; i < n; i++) luma[i] = Math.min(255, Math.max(0, ((luma[i] - lo) * 255) / rentang));
  }

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = y * width + x;
      const lama = luma[i];
      const baru = lama < 128 ? 0 : 255;
      const galat = lama - baru;
      if (x + 1 < width) luma[i + 1] += (galat * 7) / 16;
      if (y + 1 < height) {
        if (x > 0) luma[i + width - 1] += (galat * 3) / 16;
        luma[i + width] += (galat * 5) / 16;
        if (x + 1 < width) luma[i + width + 1] += galat / 16;
      }
      data[i * 4] = data[i * 4 + 1] = data[i * 4 + 2] = baru;
      data[i * 4 + 3] = 255;
    }
  }
}

// Subset CanvasRenderingContext2D yang dipakai, supaya bisa dites tanpa canvas.
type KonteksKotak = Pick<CanvasRenderingContext2D, 'strokeRect' | 'lineWidth' | 'strokeStyle'>;

// Kotak deteksi digambar SETELAH dither: hitam tebal berbingkai putih, jadi tetap tegas di
// atas foto yang sudah menjadi titik-titik. Tanpa label; jumlahnya dicetak di bawah foto.
export function gambarKotak(ctx: KonteksKotak, bboxes: Bbox[], asli: { lebar: number; tinggi: number }, tujuan: { lebar: number; tinggi: number }) {
  for (const b of bboxes) {
    const k = skalaBbox(b, asli.lebar, asli.tinggi);
    const x = (k.left / 100) * tujuan.lebar;
    const y = (k.top / 100) * tujuan.tinggi;
    const w = (k.width / 100) * tujuan.lebar;
    const h = (k.height / 100) * tujuan.tinggi;
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 6;
    ctx.strokeRect(x, y, w, h);
    ctx.strokeStyle = '#000';
    ctx.lineWidth = 3;
    ctx.strokeRect(x, y, w, h);
  }
}

// Kemas piksel hitam-putih menjadi 1 bit per dot (1 = hitam). Lebar harus kelipatan 8.
export function kemasBit({ data, width, height }: PikselRgba): Uint8Array {
  const perBaris = width / 8;
  const out = new Uint8Array(perBaris * height);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      // Garis kotak yang di-antialias bisa abu-abu; ambang tengah memutuskannya.
      if (data[(y * width + x) * 4] < 128) out[y * perBaris + (x >> 3)] |= 0x80 >> (x & 7);
    }
  }
  return out;
}

function base64DariBytes(bytes: Uint8Array): string {
  let bin = '';
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}

// Kirim foto ke printer thermal yang terpasang di komputer backend.
export function kirimCetak(foto: FotoThermal, baris: string[]): Promise<void> {
  return kirimKePrinter('/api/print/foto', { lebar: foto.lebar, tinggi: foto.tinggi, bits_b64: foto.bitsB64, baris });
}

// Ambil frame + bbox yang pasti satu pasangan (di-unduh di server, tanpa CORS ke Storage).
export async function ambilSnapshot(): Promise<SnapshotKamera> {
  // no-store: respons 404/410 tanpa header cache dipakai ulang browser, sama seperti panel kamera.
  const r = await fetch(`${API_BASE}/api/live/camera/snapshot`, { cache: 'no-store' });
  if (!r.ok) {
    const body = await r.json().catch(() => null);
    throw new GalatApi(r.status, typeof body?.detail === 'string' ? body.detail : '');
  }
  return r.json();
}

// Pesan untuk operator; 410/404 bukan kerusakan, jadi dijelaskan terpisah dari galat jaringan.
export function pesanGalatFoto(err: unknown): string {
  if (err instanceof GalatApi && err.status === 410) return 'Frame kamera basi. Tunggu kamera mengirim frame baru, lalu ulangi.';
  if (err instanceof GalatApi && err.status === 404) return 'Kamera offline: belum ada frame dari bus.';
  if (err instanceof GalatApi && err.status === 503) return 'Layanan kamera tidak tersedia. Coba lagi sebentar lagi.';
  return 'Foto gagal diambil. Pastikan server backend berjalan, lalu ulangi.';
}

function bytesDariBase64(b64: string): Uint8Array<ArrayBuffer> {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

// Snapshot -> gambar 1-bit siap cetak. Hanya jalan di browser (butuh canvas).
export async function buatFotoThermal(snap: SnapshotKamera, lebarDot = LEBAR_DOT_80MM): Promise<FotoThermal> {
  const bitmap = await createImageBitmap(new Blob([bytesDariBase64(snap.frame_b64)], { type: 'image/jpeg' }));
  try {
    const asli = { lebar: bitmap.width, tinggi: bitmap.height };
    const tujuan = ukuranCetak(asli.lebar, asli.tinggi, lebarDot);

    const canvas = document.createElement('canvas');
    canvas.width = tujuan.lebar;
    canvas.height = tujuan.tinggi;
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    if (!ctx) throw new Error('Canvas 2D tidak tersedia');

    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(bitmap, 0, 0, tujuan.lebar, tujuan.tinggi);
    const piksel = ctx.getImageData(0, 0, tujuan.lebar, tujuan.tinggi);
    ditherThermal(piksel);
    ctx.putImageData(piksel, 0, 0);
    gambarKotak(ctx, snap.bboxes, asli, tujuan);

    const bitsB64 = base64DariBytes(kemasBit(ctx.getImageData(0, 0, tujuan.lebar, tujuan.tinggi)));
    return { dataUrl: canvas.toDataURL('image/png'), ...tujuan, jumlahDeteksi: snap.bboxes.length, bitsB64 };
  } finally {
    bitmap.close();
  }
}
